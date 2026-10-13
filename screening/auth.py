"""Role-scoped API tokens; token values are never persisted by the app."""
import hashlib
import hmac
import json
import os
from threading import Lock
import time


class Auth:
    def __init__(self, token=None, accounts=None):
        self.accounts = []
        rows = accounts or [{"name": "operator", "role": "admin", "token": token}]
        for item in rows:
            value = item.get("token")
            if not isinstance(value, str) or len(value) < 32 or not value.isascii() or any(c.isspace() for c in value):
                raise ValueError("Each API token must have at least 32 non-whitespace ASCII characters")
            if item.get("role") not in ("admin", "reviewer", "viewer") or not isinstance(item.get("name"), str) or not item["name"].strip():
                raise ValueError("Each account requires a name and admin/reviewer/viewer role")
            self.accounts.append({"name": item["name"], "role": item["role"], "hash": hashlib.sha256(value.encode()).digest()})
        if len({a["hash"] for a in self.accounts}) != len(self.accounts):
            raise ValueError("Account tokens must be unique")
        if len({a["name"] for a in self.accounts}) != len(self.accounts):
            raise ValueError("Account names must be unique")

    def identify(self, header):
        if not header.startswith("Bearer "):
            return None
        digest = hashlib.sha256(header[7:].encode()).digest()
        for account in self.accounts:
            if hmac.compare_digest(digest, account["hash"]):
                return {"name": account["name"], "role": account["role"]}
        return None


class RateLimit:
    def __init__(self):
        self.windows = {}
        self.lock = Lock()

    def allow(self, key, limit):
        with self.lock:
            current = time.monotonic()
            count, start = self.windows.get(key, (0, current))
            if current - start > 60:
                count, start = 0, current
            self.windows[key] = (count + 1, start)
            return count < limit


def config_from_env():
    return {"allowed_hosts": {x.strip().lower() for x in os.getenv("SCREENING_ALLOWED_HOSTS", "").split(",") if x.strip()},
            "webhook_secret": os.getenv("SCREENING_WEBHOOK_SECRET"),
            "connector_url": os.getenv("SCREENING_CONNECTOR_URL"),
            "connector_token": os.getenv("SCREENING_CONNECTOR_TOKEN"),
            "connector_role": os.getenv("SCREENING_CONNECTOR_ROLE"),
            "sync_seconds": int(os.getenv("SCREENING_SYNC_SECONDS", "0")),
            "retention_days": int(os.getenv("SCREENING_RETENTION_DAYS", "0"))}
