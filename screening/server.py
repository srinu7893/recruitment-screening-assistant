"""Recruiter dashboard and local authenticated API; one organization per instance."""
import argparse
import base64
import signal
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
from threading import BoundedSemaphore
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from .greenhouse import import_resume
from .auth import RateLimit, config_from_env
from .identity import configured_auth
from .contracts import text
from .documents import extract_upload
from .integrations import (read_url, csv_records, import_records, sync_feed,
                           verify_webhook, claim_webhook)
from .jobs import Queue
from . import operations
from .providers import DemoProvider, OpenAIProvider
from .rules import RulesProvider
import hmac
from .storage import ConflictError, Store
from .database import DatabaseUnavailable
from .deployment import public_origin, allowed_request
from .workflow import ScreeningService

MAX_BODY = 7_100_000
STATIC = Path(__file__).with_name("static")


def make_server(service, token=None, port=8000, accounts=None, config=None, host="127.0.0.1"):
    config = config or {"allowed_hosts": set()}
    external = public_origin(config.get("public_url"))
    if os.getenv('K_SERVICE') and os.getenv('SCREENING_AUTH_MODE') == 'password' and not external:
        raise ValueError('Password login on Cloud Run requires SCREENING_PUBLIC_URL')
    auth = configured_auth(token, accounts, service.store, bool(external))
    limiter = RateLimit()
    parsing = BoundedSemaphore(2)
    queue = Queue(service)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def setup(self):
            super().setup()
            self.connection.settimeout(150)

        def send(self, status, body, mime="application/json; charset=utf-8", cookie=None):
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            if cookie:
                self.send_header('Set-Cookie', cookie)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(body)

        def reply(self, status, value, cookie=None):
            # On Windows, closing a socket with unread POST data can reset the
            # connection before a 401/403 response reaches the client. Drain only
            # bounded bodies, with a short total deadline, without parsing them.
            if status in (401, 403, 429) and self.command == 'POST' and not getattr(self, 'body_consumed', False):
                try:
                    remaining = int(self.headers.get('Content-Length', '0'))
                    deadline = time.monotonic() + 1
                    if 0 < remaining <= MAX_BODY and not self.headers.get('Transfer-Encoding'):
                        while remaining and time.monotonic() < deadline:
                            self.connection.settimeout(min(0.2, max(0.001, deadline - time.monotonic())))
                            chunk = self.rfile.read(min(remaining, 65536))
                            if not chunk:
                                break
                            remaining -= len(chunk)
                except (OSError, ValueError):
                    pass
                finally:
                    self.connection.settimeout(150)
            self.send(status, json.dumps(value).encode(), cookie=cookie)

        def read_body(self):
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                raise ValueError("Content-Type must be application/json")
            if self.headers.get("Transfer-Encoding") or len(self.headers.get_all("Content-Length", [])) != 1:
                raise ValueError("Exactly one Content-Length is required")
            length = int(self.headers["Content-Length"])
            if not 0 < length <= MAX_BODY:
                raise ValueError("Body exceeds the request limit")
            raw = self.rfile.read(length)
            self.body_consumed = True
            if len(raw) != length:
                raise ValueError("Incomplete body")
            body = json.loads(raw)
            if not isinstance(body, dict):
                raise ValueError("JSON body must be an object")
            return raw, body

        def handle_api(self):
            try:
                authority = self.headers.get("Host", "")
                origin = self.headers.get("Origin")
                if not allowed_request(authority, origin, self.server.server_port, external):
                    return self.reply(403, {"error": "invalid_host_or_origin"})
                url = urlsplit(self.path)
                query = parse_qs(url.query)
                path = url.path
                if self.command == "GET" and path == "/auth/config":
                    return self.reply(200, {"mode": auth.mode})
                if self.command == "GET" and path == "/readyz":
                    try:
                        ready = service.store.ready() and queue.thread is not None and queue.thread.is_alive() and not queue.stop.is_set()
                    except Exception:
                        ready = False
                    return self.reply(200 if ready else 503, {"status": "ready" if ready else "unavailable"})
                if self.command == "GET" and path in ("/", "/app.js", "/style.css"):
                    filename, mime = {"/": ("index.html", "text/html; charset=utf-8"),
                                      "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                                      "/style.css": ("style.css", "text/css; charset=utf-8")}[path]
                    return self.send(200, (STATIC / filename).read_bytes(), mime)
                if auth.mode == 'password' and path == '/auth/login' and self.command == 'POST':
                    if int(self.headers.get('Content-Length', '0')) > 4096:
                        raise ValueError('Login request too large')
                    _, body = self.read_body()
                    result, error = auth.login(body.get('username'), body.get('password'))
                    if error:
                        return self.reply(429 if error == 'rate_limited' else 401, {'error': error})
                    token, session = result
                    auth.logout(self.headers.get('Cookie'))
                    return self.reply(200, {'identity': session['identity'], 'csrf': session['csrf']}, auth.cookie(token))
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
                session = auth.session(self.headers.get('Cookie')) if auth.mode == 'password' else None
                identity = (session['identity'] if session else None) if auth.mode == 'password' else (auth.identify_assertion(self.headers.get("X-Goog-IAP-JWT-Assertion", ""))
                            if auth.mode == 'iap' else auth.identify(self.headers.get("Authorization", "")))
                if not identity:
                    return self.reply(401, {"error": "unauthorized"})
                if auth.mode == 'password':
                    if self.command == 'GET' and path == '/auth/session':
                        return self.reply(200, {'identity': identity, 'csrf': session['csrf']})
                    if self.command == 'POST' and not hmac.compare_digest(self.headers.get('X-CSRF-Token', ''), session['csrf']):
                        return self.reply(403, {'error': 'invalid_csrf_token'})
                    if self.command == 'POST' and path == '/auth/logout':
                        auth.logout(self.headers.get('Cookie'))
                        service.store.audit(identity['name'], 'signed_out', 'workspace')
                        return self.reply(200, {'signed_out': True}, auth.cookie('', clear=True))
                actor = identity["name"]
                if not limiter.allow(actor + ":" + self.command, 600 if self.command == "GET" else 60):
                    return self.reply(429, {"error": "rate_limited"})
                if self.command == "GET":
                    if path == "/health":
                        return self.reply(200, {"status": "ok", "provider": service.provider.name,
                                               "identity": identity, "auth_mode": auth.mode, "demo": service.provider.name == "demo",
                                               "database": service.store.backend, "worker": "leader" if queue.leader else "standby",
                                               "worker_error": queue.last_error})
                    if path == "/reviewers":
                        return self.reply(200, [{"name": a["name"], "role": a["role"]} for a in auth.accounts if a["role"] != "viewer"])
                    if path == "/roles":
                        return self.reply(200, service.store.get_role(query["version"][0]) if "version" in query else service.store.list_roles())
                    if path == "/runs":
                        return self.reply(200, service.store.get_run(query["id"][0]) if "id" in query else operations.overview(service.store))
                    if path == "/jobs":
                        return self.reply(200, queue.list())
                    if path == "/automation":
                        value = self.server.automation.snapshot()
                        value['worker'] = 'leader' if queue.leader else 'standby'
                        value['worker_error'] = queue.last_error or getattr(self.server, 'last_automation_error', None)
                        if identity['role'] != 'admin':
                            value['inbox_path'] = None
                        return self.reply(200, value)
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
                            "greenhouse_configured": bool(os.environ.get("GREENHOUSE_CLIENT_ID") and os.environ.get("GREENHOUSE_CLIENT_SECRET")),
                            "scan_mode": os.environ.get("SCREENING_SCAN_MODE", "clamd" if os.environ.get("K_SERVICE") else "off"),
                            "webhook_configured": bool(config.get("webhook_secret")),
                            "feed_configured": bool(config.get("connector_url")),
                            "sync_seconds": config.get("sync_seconds", 0),
                            "last_sync": getattr(self.server, "last_sync", None)})
                    return self.reply(404, {"error": "not_found"})
                if self.command != "POST":
                    return self.reply(405, {"error": "method_not_allowed"})
                if identity["role"] == "viewer":
                    return self.reply(403, {"error": "read_only_account"})
                admin_paths = {"/automation/retry", "/automation/settings", "/automation/run", "/integrations/greenhouse", "/roles", "/delete", "/retention", "/integrations/sync", "/jobs/cancel", "/showcase/load"}
                if path in admin_paths and identity["role"] != "admin":
                    return self.reply(403, {"error": "admin_required"})
                _, body = self.read_body()
                if path == '/automation/settings':
                    return self.reply(200, self.server.automation.update(body, actor))
                if path == '/automation/retry':
                    return self.reply(200, self.server.automation.retry(body.get('id'), actor))
                if path == '/automation/run':
                    worker = queue.worker if service.store.backend == 'postgresql' else queue
                    if not worker or not queue.leader:
                        raise ConflictError('This instance has no active intake worker; try the leader')
                    return self.reply(200, self.server.automation.tick(worker, manual=True, actor=actor))
                if path == "/showcase/load":
                    if service.provider.name != "demo":
                        raise ValueError("Load showcase data only in a demo-mode workspace")
                    from .showcase import seed
                    return self.reply(200, seed(service.store, actor))
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
                                "display_name": Path(body["filename"]).name,
                                "pages": extracted["pages"], "warnings": extracted["warnings"], "malware_scan": extracted.get("malware_scan")}
                    return self.reply(202, queue.submit(request, metadata, actor))
                if path == "/imports/url":
                    if not parsing.acquire(blocking=False):
                        return self.reply(429, {"error": "parser_busy_try_again"})
                    try:
                        extracted = read_url(body.get("url"), config["allowed_hosts"])
                    finally:
                        parsing.release()
                    request = {"request_id": body.get("request_id"), "role_version": body.get("role_version"), "profile_text": extracted["text"]}
                    parts = urlsplit(body["url"])
                    return self.reply(202, queue.submit(request, {"kind": "url", "host": parts.hostname,
                                                                  "warnings": extracted["warnings"]}, actor))
                if path == "/imports/csv":
                    return self.reply(202, import_records(queue, csv_records(body.get("csv")), body.get("role_version"), actor))
                if path == "/integrations/greenhouse":
                    if not parsing.acquire(blocking=False):
                        return self.reply(429, {"error": "parser_busy_try_again"})
                    try:
                        return self.reply(202, import_resume(queue, body, actor))
                    finally:
                        parsing.release()
                if path == "/integrations/sync":
                    settings = self.server.automation.settings()
                    result = sync_feed(queue, {**config, 'connector_role': settings['role_version'] or config.get('connector_role')}, actor)
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
                if path == "/assignments":
                    reviewers = {a["name"] for a in auth.accounts if a["role"] != "viewer"}
                    return self.reply(200, operations.assign(service.store, text(body.get("run_id"), "run_id", 120), body, actor, reviewers))
                if path in ("/decisions", "/notes", "/corrections", "/scorecards"):
                    action = {"/scorecards": operations.scorecard, "/decisions": operations.review, "/notes": operations.note, "/corrections": operations.correct}[path]
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
            except DatabaseUnavailable:
                self.reply(503, {"error": "database_unavailable"})
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
            if hasattr(self, 'automation'):
                self.automation.stop.set()
            queue.close()
            super().server_close()
            if self.instance_lock:
                self.instance_lock.close()

    instance_lock = service.store.acquire_instance() if service.store.backend == "sqlite" else None
    try:
        server = Server((host, port), Handler, bind_and_activate=False)
        server.instance_lock = instance_lock
        server.server_bind()
        server.server_activate()
    except Exception:
        if instance_lock:
            instance_lock.close()
        raise
    server.queue = queue
    server.parsing = parsing
    try:
        from .automation import Automation
        server.automation = Automation(server, config)
        queue.start()
    except Exception:
        server.server_close()
        raise
    return server


def main():
    parser = argparse.ArgumentParser(description="Recruiter workspace")
    parser.add_argument("--provider", choices=["demo", "rules", "openai"], default=os.getenv("SCREENING_PROVIDER", "demo"))
    parser.add_argument("--db", default="data/screening.sqlite3")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")))
    parser.add_argument("--host", choices=["127.0.0.1", "0.0.0.0"], default="127.0.0.1")
    args = parser.parse_args()
    from .maintenance import Maintenance
    try:
        provider = {'demo': DemoProvider, 'rules': RulesProvider, 'openai': OpenAIProvider}[args.provider]()
        accounts = json.loads(os.environ["SCREENING_ACCOUNTS"]) if os.getenv("SCREENING_ACCOUNTS") else None
        config = config_from_env()
        config["public_url"] = os.getenv("SCREENING_PUBLIC_URL")
        database_url = os.getenv("DATABASE_URL")
        if os.getenv("K_SERVICE") and (not database_url or not database_url.startswith(("postgres://", "postgresql://"))):
            raise ValueError("Cloud Run requires a PostgreSQL DATABASE_URL; ephemeral SQLite is disabled")
        service = ScreeningService(Store(database_url or args.db), provider)
        config['inbox_dir'] = os.getenv('SCREENING_INBOX_DIR')
        if os.getenv('K_SERVICE') and config['inbox_dir']:
            raise ValueError('Cloud Run intake uses uploads or configured feeds; local folder watching is disabled')
        if not config['inbox_dir'] and service.store.backend == 'sqlite':
            config['inbox_dir'] = str(service.store.path.parent / 'inbox')
        server = make_server(service, os.getenv("SCREENING_API_TOKEN"), args.port, accounts, config, args.host)
        maintenance = Maintenance(server, config)
        maintenance.start()
    except (ValueError, DatabaseUnavailable) as exc:
        parser.exit(2, f"Configuration error: {exc}\n")
    def stop_signal(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop_signal)
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
