"""Optional scheduled feed synchronization and retention, disabled by default."""
from threading import Event, Thread
import time
import os
import json

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
        last_report = time.monotonic()
        while not self.stop.is_set():
            queue = self.server.queue
            current = time.monotonic()
            if os.getenv('K_SERVICE') and current-last_report>=60:
                from .monitoring import snapshot
                try:
                    report=snapshot(queue.store,queue)
                    if os.getenv('SCREENING_SCAN_MODE','clamd')=='clamd':
                        from .scanning import check_signatures
                        try:
                            check_signatures()
                        except ValueError:
                            report['warnings'].append('scanner_unavailable_or_stale')
                            report['severity']='WARNING'
                except Exception:
                    report={'event':'screening_operations','severity':'WARNING','warnings':['operations_database_unavailable']}
                print(json.dumps(report),flush=True)
                last_report=current
            if queue.store.backend == 'postgresql':
                if not queue.leader or not queue.worker:
                    self.stop.wait(1)
                    continue
                queue = queue.worker
            if hasattr(self.server, 'automation'):
                try:
                    self.server.automation.tick(queue)
                    self.server.last_automation_error = None
                except Exception:
                    self.server.last_automation_error = 'intake_cycle_failed'
            interval = self.config.get("sync_seconds", 0)
            if hasattr(self.server, 'automation'):
                try:
                    settings = self.server.automation.settings()
                    if settings.get('revision',0)>0 or (settings['enabled'] and settings['feed_enabled']):
                        interval = 0  # UI-managed schedules, including pause, own polling.
                except Exception:
                    interval = 0
            if interval and current - last_sync >= interval:
                last_sync = current
                try:
                    result = sync_feed(queue, self.config, "scheduled-sync")
                    self.server.last_sync = {"at": now(), "jobs": len(result["jobs"]), "errors": len(result["errors"])}
                except Exception:
                    self.server.last_sync = {"at": now(), "error": "sync_failed"}
            if self.config.get("retention_days") and current - last_retention >= 3600:
                last_retention = current
                try:
                    expire(queue.store, self.config["retention_days"], "retention-policy")
                except Exception:
                    # Database failures must not kill the scheduler thread.
                    self.server.last_retention_error = "retention_failed"
            self.stop.wait(1)

    def close(self):
        self.stop.set()
        if hasattr(self.server, 'automation'):
            self.server.automation.stop.set()
        if self.thread:
            self.thread.join(timeout=1)
