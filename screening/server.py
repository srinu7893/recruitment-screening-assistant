"""Local development JSON API. Not a production HTTP server."""

import argparse
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from urllib.parse import parse_qs, urlsplit

from .providers import DemoProvider, OpenAIProvider
from .storage import ConflictError, Store
from .workflow import ScreeningService

MAX_BODY = 250_000


def make_server(service, token, port=8000):
    if not isinstance(token, str) or len(token) < 32 or not token.isascii():
        raise ValueError("SCREENING_API_TOKEN must have at least 32 ASCII characters")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Do not log request paths, payloads or profile text.

        def setup(self):
            super().setup()
            self.connection.settimeout(60)

        def reply(self, status, value):
            body = json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def authorized(self):
            actual = self.headers.get("Authorization", "").encode()
            if not hmac.compare_digest(actual, f"Bearer {token}".encode()):
                self.reply(401, {"error": "unauthorized"})
                return False
            # No browser-origin clients until a deliberate same-origin UI is added.
            if self.headers.get("Origin"):
                self.reply(403, {"error": "browser_origin_not_supported"})
                return False
            return True

        def handle_api(self):
            if not self.authorized():
                return
            try:
                url = urlsplit(self.path)
                if self.command == "GET":
                    if url.path == "/health":
                        return self.reply(200, {"status": "ok", "provider": service.provider.name})
                    query = parse_qs(url.query)
                    if url.path == "/runs" and len(query.get("id", [])) == 1:
                        return self.reply(200, service.store.get_run(query["id"][0]))
                    if url.path == "/roles" and len(query.get("version", [])) == 1:
                        return self.reply(200, service.store.get_role(query["version"][0]))
                    return self.reply(404, {"error": "not_found"})
                if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                    return self.reply(415, {"error": "expected_application_json"})
                if self.headers.get("Transfer-Encoding"):
                    return self.reply(400, {"error": "transfer_encoding_not_supported"})
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_BODY:
                    return self.reply(413, {"error": "invalid_body_size"})
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise ValueError("Incomplete body")
                body = json.loads(raw)
                if url.path == "/roles":
                    return self.reply(201, service.create_role(body))
                if url.path == "/screenings":
                    result = service.screen(body)
                    return self.reply(200, result)
                self.reply(404, {"error": "not_found"})
            except ConflictError:
                self.reply(409, {"error": "conflicting_version_or_request_id"})
            except KeyError:
                self.reply(404, {"error": "not_found"})
            except (ValueError, UnicodeError, RecursionError):
                self.reply(400, {"error": "invalid_request"})
            except Exception:
                self.reply(500, {"error": "internal_error"})

        do_GET = handle_api
        do_POST = handle_api

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main():
    parser = argparse.ArgumentParser(description="Local single-user recruitment API")
    parser.add_argument("--provider", choices=["demo", "openai"], default="demo")
    parser.add_argument("--db", default="data/screening.sqlite3")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    try:
        provider = DemoProvider() if args.provider == "demo" else OpenAIProvider()
        token = os.environ.get("SCREENING_API_TOKEN")
        if not token:
            raise ValueError("Set SCREENING_API_TOKEN before starting the API")
        server = make_server(ScreeningService(Store(args.db), provider), token, args.port)
    except ValueError as exc:
        parser.exit(2, f"Configuration error: {exc}\n")
    print(f"Local API: http://127.0.0.1:{args.port} (provider={provider.name})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
