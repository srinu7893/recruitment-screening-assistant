"""Recruiter dashboard and local authenticated API; one organization per instance."""
import argparse
import base64
import fcntl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
from threading import BoundedSemaphore
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from .auth import Auth, RateLimit, config_from_env
from .contracts import text
from .documents import extract_upload
from .integrations import (read_url, csv_records, import_records, sync_feed,
                           verify_webhook, claim_webhook)
from .jobs import Queue
from . import operations
from .providers import DemoProvider, OpenAIProvider
from .storage import ConflictError, Store
from .workflow import ScreeningService

MAX_BODY = 7_100_000
STATIC = Path(__file__).with_name("static")


def make_server(service, token=None, port=8000, accounts=None, config=None, host="127.0.0.1"):
    auth = Auth(token, accounts)
    config = config or {"allowed_hosts": set()}
    limiter = RateLimit()
    parsing = BoundedSemaphore(2)
    queue = Queue(service)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def setup(self):
            super().setup()
            self.connection.settimeout(150)

        def send(self, status, body, mime="application/json; charset=utf-8"):
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(body)

        def reply(self, status, value):
            self.send(status, json.dumps(value).encode())

        def read_body(self):
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                raise ValueError("Content-Type must be application/json")
            if self.headers.get("Transfer-Encoding") or len(self.headers.get_all("Content-Length", [])) != 1:
                raise ValueError("Exactly one Content-Length is required")
            length = int(self.headers["Content-Length"])
            if not 0 < length <= MAX_BODY:
                raise ValueError("Body exceeds the request limit")
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError("Incomplete body")
            body = json.loads(raw)
            if not isinstance(body, dict):
                raise ValueError("JSON body must be an object")
            return raw, body

        def handle_api(self):
            try:
                authority = self.headers.get("Host", "")
                valid_hosts = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
                if authority not in valid_hosts:
                    return self.reply(403, {"error": "invalid_host"})
                origin = self.headers.get("Origin")
                if origin and origin != "http://" + authority:
                    return self.reply(403, {"error": "cross_origin_denied"})
                url = urlsplit(self.path)
                query = parse_qs(url.query)
                path = url.path
                if self.command == "GET" and path in ("/", "/app.js", "/style.css"):
                    filename, mime = {"/": ("index.html", "text/html; charset=utf-8"),
                                      "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                                      "/style.css": ("style.css", "text/css; charset=utf-8")}[path]
                    return self.send(200, (STATIC / filename).read_bytes(), mime)
                if path == "/webhooks/profiles" and self.command == "POST":
                    if not limiter.allow("webhook", 30):
                        return self.reply(429, {"error": "rate_limited"})
                    raw, body = self.read_body()
                    event_id = self.headers.get("X-Event-ID")
                    verify_webhook(service.store, raw, self.headers.get("X-Timestamp"),
                                   self.headers.get("X-Signature"), event_id, config.get("webhook_secret"))
                    result = import_records(queue, body.get("candidates"), body.get("role_version"), "webhook", "webhook")
                    if not result["errors"]:
                        claim_webhook(service.store, event_id)
                    return self.reply(202, result)
                identity = auth.identify(self.headers.get("Authorization", ""))
                if not identity:
                    return self.reply(401, {"error": "unauthorized"})
                actor = identity["name"]
                if not limiter.allow(actor + ":" + self.command, 600 if self.command == "GET" else 60):
                    return self.reply(429, {"error": "rate_limited"})
                if self.command == "GET":
                    if path == "/health":
                        return self.reply(200, {"status": "ok", "provider": service.provider.name,
                                               "identity": identity, "demo": service.provider.name == "demo"})
                    if path == "/roles":
                        return self.reply(200, service.store.get_role(query["version"][0]) if "version" in query else service.store.list_roles())
                    if path == "/runs":
                        return self.reply(200, service.store.get_run(query["id"][0]) if "id" in query else operations.overview(service.store))
                    if path == "/jobs":
                        return self.reply(200, queue.list())
                    if path == "/interview":
                        return self.reply(200, operations.interview_kit(service.store.get_run(query.get("id", [""])[0])))
                    if path == "/export":
                        result = service.store.get_run(query.get("id", [""])[0])
                        service.store.audit(actor, "record_exported", result["run_id"])
                        return self.reply(200, result)
                    if path == "/audit" and identity["role"] == "admin":
                        return self.reply(200, service.store.audits())
                    if path == "/integrations":
                        return self.reply(200, {"allowed_hosts": sorted(config["allowed_hosts"]),
                            "webhook_configured": bool(config.get("webhook_secret")),
                            "feed_configured": bool(config.get("connector_url")),
                            "sync_seconds": config.get("sync_seconds", 0),
                            "last_sync": getattr(self.server, "last_sync", None)})
                    return self.reply(404, {"error": "not_found"})
                if self.command != "POST":
                    return self.reply(405, {"error": "method_not_allowed"})
                if identity["role"] == "viewer":
                    return self.reply(403, {"error": "read_only_account"})
                admin_paths = {"/roles", "/delete", "/retention", "/integrations/sync", "/jobs/cancel"}
                if path in admin_paths and identity["role"] != "admin":
                    return self.reply(403, {"error": "admin_required"})
                _, body = self.read_body()
                if path == "/roles":
                    body["approved_by"] = actor
                    role = service.create_role(body)
                    service.store.audit(actor, "role_approved", role["role_version"])
                    return self.reply(201, role)
                if path == "/roles/draft":
                    return self.reply(200, operations.draft_criteria(body.get("description")))
                if path in ("/screenings", "/jobs"):
                    return self.reply(202, queue.submit(body, actor=actor))
                if path == "/uploads":
                    if not parsing.acquire(blocking=False):
                        return self.reply(429, {"error": "parser_busy_try_again"})
                    try:
                        extracted = extract_upload(body.get("filename"), body.get("content_base64"))
                    finally:
                        parsing.release()
                    request = {"request_id": body.get("request_id"), "role_version": body.get("role_version"), "profile_text": extracted["text"]}
                    metadata = {"kind": "upload", "filename": Path(body["filename"]).name,
                                "pages": extracted["pages"], "warnings": extracted["warnings"]}
                    return self.reply(202, queue.submit(request, metadata, actor))
                if path == "/imports/url":
                    extracted = read_url(body.get("url"), config["allowed_hosts"])
                    request = {"request_id": body.get("request_id"), "role_version": body.get("role_version"), "profile_text": extracted["text"]}
                    parts = urlsplit(body["url"])
                    return self.reply(202, queue.submit(request, {"kind": "url", "host": parts.hostname,
                                                                  "warnings": extracted["warnings"]}, actor))
                if path == "/imports/csv":
                    return self.reply(202, import_records(queue, csv_records(body.get("csv")), body.get("role_version"), actor))
                if path == "/integrations/sync":
                    result = sync_feed(queue, config, actor)
                    self.server.last_sync = {"at": operations.now(), "jobs": len(result["jobs"]), "errors": len(result["errors"])}
                    return self.reply(202, result)
                if path == "/rediscover":
                    ids = body.get("run_ids")
                    if not isinstance(ids, list) or not 1 <= len(ids) <= 20:
                        raise ValueError("Select 1 to 20 saved profiles")
                    role_version = text(body.get("role_version"), "role_version", 120)
                    service.store.get_role(role_version)
                    runs = [service.store.get_run(text(key, "run id", 120)) for key in ids]
                    jobs = []
                    for run in runs:
                        jobs.append(queue.submit({"request_id": "rediscovery-" + str(uuid4()),
                            "role_version": role_version, "profile_text": run["source"]["text"]},
                            {"kind": "rediscovery", "parent_run": run["run_id"]}, actor))
                    return self.reply(202, {"jobs": jobs})
                if path == "/compare":
                    return self.reply(200, operations.compare(service.store, body.get("run_ids")))
                if path == "/preview":
                    return self.reply(200, operations.preview(service.store.get_run(body.get("run_id")), body.get("required_ids")))
                if path in ("/decisions", "/notes", "/corrections"):
                    action = {"/decisions": operations.review, "/notes": operations.note, "/corrections": operations.correct}[path]
                    return self.reply(200, action(service.store, text(body.get("run_id"), "run_id", 120), body, actor))
                if path == "/delete":
                    service.store.delete_run(text(body.get("run_id"), "run_id", 120), actor)
                    return self.reply(200, {"deleted": True})
                if path == "/retention":
                    return self.reply(200, operations.expire(service.store, body.get("days"), actor))
                if path == "/jobs/cancel":
                    queue.cancel(text(body.get("id"), "job id", 120), actor)
                    return self.reply(200, {"cancelled": True})
                self.reply(404, {"error": "not_found"})
            except ConflictError as exc:
                self.reply(409, {"error": str(exc)})
            except KeyError:
                self.reply(404, {"error": "not_found"})
            except (ValueError, UnicodeError, RecursionError) as exc:
                # Validation messages contain no raw model output or credentials.
                self.reply(400, {"error": str(exc)[:200] if isinstance(exc, ValueError) else "invalid_request"})
            except Exception:
                self.reply(500, {"error": "internal_error"})

        do_GET = handle_api
        do_POST = handle_api

    class Server(ThreadingHTTPServer):
        def server_close(self):
            queue.close()
            super().server_close()
            self.instance_lock.close()

    instance_lock = open(str(service.store.path) + ".lock", "a")
    try:
        fcntl.flock(instance_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        instance_lock.close()
        raise ValueError("Another server already uses this database") from None
    try:
        server = Server((host, port), Handler, bind_and_activate=False)
        server.instance_lock = instance_lock
        server.server_bind()
        server.server_activate()
    except Exception:
        instance_lock.close()
        raise
    server.queue = queue
    queue.start()
    return server


def main():
    parser = argparse.ArgumentParser(description="Recruiter workspace")
    parser.add_argument("--provider", choices=["demo", "openai"], default="demo")
    parser.add_argument("--db", default="data/screening.sqlite3")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", choices=["127.0.0.1", "0.0.0.0"], default="127.0.0.1")
    args = parser.parse_args()
    from .maintenance import Maintenance
    try:
        provider = DemoProvider() if args.provider == "demo" else OpenAIProvider()
        accounts = json.loads(os.environ["SCREENING_ACCOUNTS"]) if os.getenv("SCREENING_ACCOUNTS") else None
        config = config_from_env()
        service = ScreeningService(Store(args.db), provider)
        server = make_server(service, os.getenv("SCREENING_API_TOKEN"), args.port, accounts, config, args.host)
        maintenance = Maintenance(server, config)
        maintenance.start()
    except ValueError as exc:
        parser.exit(2, f"Configuration error: {exc}\n")
    print(f"Recruiter workspace: http://127.0.0.1:{args.port} (provider={provider.name})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        maintenance.close()
        server.server_close()


if __name__ == "__main__":
    main()
