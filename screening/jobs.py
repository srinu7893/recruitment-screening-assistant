"""Durable single-worker queue. Interrupted jobs require explicit retry."""
import hashlib
import json
from threading import Event, Thread
import time

from .contracts import text, MAX_PROFILE_CHARS
from .storage import ConflictError, now


class Queue:
    def __init__(self, service):
        self.service = service
        self.store = service.store
        self.stop = Event()
        self.thread = None

    def submit(self, request, metadata=None, actor="operator"):
        if not isinstance(request, dict) or set(request) != {"request_id", "role_version", "profile_text"}:
            raise ValueError("Invalid screening request")
        for field in ("request_id", "role_version"):
            text(request[field], field, 120)
        text(request["profile_text"], "profile_text", MAX_PROFILE_CHARS)
        self.store.get_role(request["role_version"])
        metadata = metadata or {}
        fingerprint = hashlib.sha256(json.dumps({"request": request, "metadata": metadata,
            "provider": self.service.provider.name, "model": self.service.provider.model}, sort_keys=True).encode()).hexdigest()
        job = {"id": request["request_id"], "status": "queued", "created_at": now(),
               "request": request, "metadata": metadata, "actor": actor, "error": None,
               "provider": self.service.provider.name, "model": self.service.provider.model}
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT fingerprint, document FROM jobs WHERE id = ?", (job["id"],)).fetchone()
            if existing:
                if existing[0] != fingerprint:
                    raise ConflictError("Job ID already used with other input")
                return self.public(json.loads(existing[1]))
            if db.execute("SELECT 1 FROM runs WHERE id = ?", (job["id"],)).fetchone():
                raise ConflictError("Run ID already exists")
            if db.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','processing')").fetchone()[0] >= 100:
                raise ConflictError("Queue is full; wait for processing")
            db.execute("INSERT INTO jobs VALUES (?, ?, ?, ?)", (job["id"], fingerprint, "queued", json.dumps(job)))
            db.execute("INSERT INTO audit(at, actor, action, target) VALUES (?, ?, ?, ?)",
                       (now(), actor, "profile_submitted", job["id"]))
        return self.public(job)

    @staticmethod
    def public(job):
        return {k: job[k] for k in ("id", "status", "created_at", "error")}

    def list(self):
        with self.store.connect() as db:
            return [self.public(json.loads(row[0])) for row in db.execute("SELECT document FROM jobs ORDER BY rowid DESC LIMIT 100")]

    def cancel(self, key, actor):
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT status, document FROM jobs WHERE id = ?", (key,)).fetchone()
            if not row:
                raise KeyError("Job not found")
            if row[0] not in ("queued", "failed"):
                raise ConflictError("Only queued or failed jobs can be cancelled")
            job = json.loads(row[1])
            job.pop("request", None)
            job.update(status="cancelled", error=None)
            db.execute("UPDATE jobs SET status = 'cancelled', document = ? WHERE id = ?", (json.dumps(job), key))
            db.execute("INSERT INTO audit(at, actor, action, target) VALUES (?, ?, ?, ?)",
                       (now(), actor, "job_cancelled", key))

    def start(self):
        # Never silently repeat a paid call after a process crash.
        with self.store.connect() as db:
            rows = db.execute("SELECT id, document FROM jobs WHERE status = 'processing'").fetchall()
            for key, document in rows:
                job = json.loads(document)
                job.update(status="failed", error="interrupted_retry_with_new_id")
                job.pop("request", None)
                db.execute("UPDATE jobs SET status = 'failed', document = ? WHERE id = ?", (json.dumps(job), key))
            for key, document in db.execute("SELECT id, document FROM runs").fetchall():
                run = json.loads(document)
                if run["status"] in ("received", "evaluating", "validating"):
                    run.update(status="failed", error="interrupted_retry_with_new_id", result=None)
                    db.execute("UPDATE runs SET document = ? WHERE id = ?", (json.dumps(run), key))
        self.thread = Thread(target=self.loop, daemon=True)
        self.thread.start()

    def process_one(self):
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT id, document FROM jobs WHERE status = 'queued' ORDER BY rowid LIMIT 1").fetchone()
            if not row:
                return False
            key, document = row
            job = json.loads(document)
            job["status"] = "processing"
            db.execute("UPDATE jobs SET status = 'processing', document = ? WHERE id = ?", (json.dumps(job), key))
        try:
            if (job["provider"], job["model"]) != (self.service.provider.name, self.service.provider.model):
                raise ValueError("Provider configuration changed")
            result = self.service.screen(job["request"], job["metadata"])
            job.update(status="failed" if result["status"] == "failed" else "completed", error=result["error"])
        except Exception:
            job.update(status="failed", error="job_failed")
        job.pop("request", None)  # Keep source only in run; no second profile copy.
        with self.store.connect() as db:
            db.execute("UPDATE jobs SET status = ?, document = ? WHERE id = ?", (job["status"], json.dumps(job), key))
        return True

    def loop(self):
        while not self.stop.is_set():
            try:
                processed = self.process_one()
            except Exception:
                processed = False
            if not processed:
                self.stop.wait(0.25)

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=50)
