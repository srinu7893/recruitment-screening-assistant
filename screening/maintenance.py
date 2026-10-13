"""Optional scheduled feed synchronization and retention, disabled by default."""
from threading import Event, Thread
import time

from .integrations import sync_feed
from .operations import expire
from .storage import now


class Maintenance:
    def __init__(self, server, config):
        self.server = server
        self.config = config
        self.stop = Event()
        self.thread = None
        interval = config.get("sync_seconds", 0)
        if interval and interval < 60:
            raise ValueError("Sync interval must be zero or at least 60 seconds")
        days = config.get("retention_days", 0)
        if days and not 1 <= days <= 3650:
            raise ValueError("Retention days must be zero or 1 to 3650")

    def start(self):
        self.thread = Thread(target=self.loop, daemon=True)
        self.thread.start()

    def loop(self):
        last_sync = 0
        last_retention = 0
        while not self.stop.is_set():
            current = time.monotonic()
            interval = self.config.get("sync_seconds", 0)
            if interval and current - last_sync >= interval:
                last_sync = current
                try:
                    result = sync_feed(self.server.queue, self.config, "scheduled-sync")
                    self.server.last_sync = {"at": now(), "jobs": len(result["jobs"]), "errors": len(result["errors"])}
                except Exception:
                    self.server.last_sync = {"at": now(), "error": "sync_failed"}
            if self.config.get("retention_days") and current - last_retention >= 3600:
                last_retention = current
                try:
                    expire(self.server.queue.store, self.config["retention_days"], "retention-policy")
                except Exception:
                    self.server.queue.store.audit("retention-policy", "retention_failed", "system")
            self.stop.wait(1)

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=25)
