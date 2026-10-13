"""Explicitly allowlisted imports; no arbitrary internal-network requests."""
import base64
import csv
import hashlib
import hmac
from html.parser import HTMLParser
import http.client
import io
import ipaddress
import json
import socket
import ssl
import time
from urllib.parse import urlsplit

from .contracts import text
from .documents import extract_upload

MAX_DOWNLOAD = 5 * 1024 * 1024


def validate_url(url, allowed_hosts, resolver=socket.getaddrinfo):
    text(url, "URL", 4000)
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.username or parts.password or parts.fragment or parts.port not in (None, 443):
        raise ValueError("Only HTTPS URLs without credentials or fragments on port 443 are allowed")
    host = (parts.hostname or "").lower()
    if host not in allowed_hosts:
        raise ValueError("URL host is not in SCREENING_ALLOWED_HOSTS")
    addresses = {item[4][0] for item in resolver(host, 443, type=socket.SOCK_STREAM)}
    if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
        raise ValueError("URL resolves to a non-public address")
    return parts, sorted(addresses)[0]


class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, address):
        super().__init__(host, 443, timeout=20, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        sock = socket.create_connection((self.address, 443), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def fetch(url, allowed_hosts, bearer=None):
    parts, address = validate_url(url, allowed_hosts)
    connection = PinnedHTTPS(parts.hostname, address)
    headers = {"Accept": "application/json,text/plain,text/html,application/pdf", "User-Agent": "RecruitmentScreening/0.3"}
    if bearer:
        headers["Authorization"] = "Bearer " + bearer
    try:
        connection.request("GET", (parts.path or "/") + (("?" + parts.query) if parts.query else ""), headers=headers)
        response = connection.getresponse()
        if response.status != 200:
            raise ValueError("Source did not return HTTP 200; redirects are not followed")
        raw = response.read(MAX_DOWNLOAD + 1)
        if len(raw) > MAX_DOWNLOAD:
            raise ValueError("Remote source exceeds 5 MB")
        return raw, response.getheader("Content-Type", "").split(";")[0].lower()
    except (OSError, http.client.HTTPException):
        raise ValueError("Remote source unavailable") from None
    finally:
        connection.close()


class PlainHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden and data.strip():
            self.parts.append(data.strip())


def read_url(url, allowed_hosts):
    raw, mime = fetch(url, allowed_hosts)
    if mime == "application/pdf":
        return extract_upload("remote.pdf", base64.b64encode(raw).decode())
    if mime not in ("text/plain", "text/html"):
        raise ValueError("URL must return PDF, plain text or HTML")
    content = raw.decode("utf-8-sig")
    if mime == "text/html":
        parser = PlainHTML()
        parser.feed(content)
        content = "\n".join(parser.parts)
    text(content, "remote profile", 50_000)
    return {"text": content, "pages": 1, "warnings": ["Imported web text: verify relevance and completeness."]}


def csv_records(content):
    text(content, "CSV", 1_000_000)
    reader = csv.DictReader(io.StringIO(content.lstrip("\ufeff")))
    if not reader.fieldnames or not {"external_id", "profile_text"}.issubset(reader.fieldnames):
        raise ValueError("CSV requires external_id and profile_text columns")
    rows = []
    for row in reader:
        if len(rows) >= 100:
            raise ValueError("At most 100 CSV profiles per import")
        rows.append({"external_id": text(row.get("external_id"), "external_id", 120),
                     "profile_text": text(row.get("profile_text"), "profile_text", 50_000)})
    if not rows:
        raise ValueError("CSV contains no profiles")
    return rows


def import_records(queue, records, role_version, actor, source="ats-export"):
    if not isinstance(records, list) or not 1 <= len(records) <= 100:
        raise ValueError("Provide 1 to 100 profile records")
    # Validate the whole batch before scheduling any jobs.
    normalized = []
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("Invalid profile record")
        external = text(record.get("external_id"), "external_id", 120)
        profile = text(record.get("profile_text"), "profile_text", 50_000)
        identity = hashlib.sha256(json.dumps([source, external, role_version, profile]).encode()).hexdigest()
        normalized.append(({"request_id": "import-" + identity[:40], "role_version": role_version,
                            "profile_text": profile}, {"kind": source, "external_id": external}))
    jobs = []
    errors = []
    for request, metadata in normalized:
        try:
            jobs.append(queue.submit(request, metadata, actor))
        except (ValueError, KeyError) as exc:
            errors.append({"external_id": metadata["external_id"], "error": str(exc)[:200]})
    return {"jobs": jobs, "errors": errors}


def sync_feed(queue, config, actor):
    url = config.get("connector_url")
    if not url or not config.get("connector_role"):
        raise ValueError("Configure SCREENING_CONNECTOR_URL and SCREENING_CONNECTOR_ROLE")
    raw, mime = fetch(url, config["allowed_hosts"], config.get("connector_token"))
    if mime != "application/json":
        raise ValueError("Connector must return application/json")
    document = json.loads(raw)
    if not isinstance(document, dict) or set(document) != {"candidates"}:
        raise ValueError("Connector contract requires a candidates array")
    return import_records(queue, document["candidates"], config["connector_role"], actor, "connector")


def verify_webhook(store, raw, timestamp, signature, event_id, secret):
    if not secret:
        raise ValueError("Webhook is not configured")
    text(event_id, "event id", 120)
    try:
        issued = int(timestamp)
    except (TypeError, ValueError):
        raise ValueError("Invalid webhook timestamp") from None
    if abs(time.time() - issued) > 300:
        raise ValueError("Webhook timestamp expired")
    expected = hmac.new(secret.encode(), timestamp.encode() + b"." + event_id.encode() + b"." + raw, hashlib.sha256).hexdigest()
    if not isinstance(signature, str) or not hmac.compare_digest(signature, expected):
        raise ValueError("Invalid webhook signature")
    with store.connect() as db:
        db.execute("DELETE FROM webhook_events WHERE at < ?", (time.time() - 600,))
        claimed = db.execute("INSERT OR IGNORE INTO webhook_events VALUES (?, ?)", (event_id, time.time()))
        if claimed.rowcount != 1:
            raise ValueError("Webhook replay rejected")


def claim_webhook(store, event_id):
    with store.connect() as db:
        db.execute("DELETE FROM webhook_events WHERE at < ?", (time.time() - 600,))
        db.execute("INSERT OR IGNORE INTO webhook_events VALUES (?, ?)", (event_id, time.time()))
