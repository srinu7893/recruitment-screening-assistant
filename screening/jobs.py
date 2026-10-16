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
        self.last_error = None
        self.leader = False
        self.worker = None

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
               "provider": self.service.provider.name, "model": self.service.provider.model,
               "role_version": request['role_version']}
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
            db.execute("INSERT INTO jobs(id, fingerprint, status, document) VALUES (?, ?, ?, ?)", (job["id"], fingerprint, "queued", json.dumps(job)))
            db.execute("INSERT INTO audit(at, actor, action, target) VALUES (?, ?, ?, ?)",
                       (now(), actor, "profile_submitted", job["id"]))
        return self.public(job)

    @staticmethod
    def public(job):
        return {**{k: job[k] for k in ("id", "status", "created_at", "error")},
                'source': job.get('metadata', {}).get('kind', 'paste'),
                'filename': job.get('metadata', {}).get('filename'),
                'role_version': job.get('role_version') or job.get('request', {}).get('role_version'),
                'finished_at': job.get('finished_at')}

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

    def recover(self):
        # Never silently repeat a paid call after a process crash.
        with self.store.connect() as db:
            rows = db.execute("SELECT id, document FROM jobs WHERE status = 'processing'").fetchall()
            for key, document in rows:
                job = json.loads(document)
                saved = db.execute("SELECT document FROM runs WHERE id = ?", (key,)).fetchone()
                run = json.loads(saved[0]) if saved else None
                # The assessment may have committed just before the process lost
                # ownership, while the job completion write was still pending.
                if run and run['status'] in ('awaiting_review', 'completed') and run.get('result'):
                    job.update(status='completed', error=None)
                else:
                    error = run.get('error') if run and run['status'] == 'failed' else 'interrupted_retry_with_new_id'
                    job.update(status='failed', error=error or 'job_failed')
                    if run and run['status'] in ('received', 'evaluating', 'validating'):
                        run.update(status='failed', error='interrupted_retry_with_new_id', result=None)
                        db.execute("UPDATE runs SET document = ? WHERE id = ?", (json.dumps(run), key))
                job.pop('request', None)
                db.execute("UPDATE jobs SET status = ?, document = ? WHERE id = ?", (job['status'], json.dumps(job), key))

    def start(self):
        if self.store.backend != 'postgresql':
            self.recover()
            self.leader = True
        self.thread = Thread(target=self.cloud_loop if self.store.backend == 'postgresql' else self.loop, daemon=True)
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
        job['role_version'] = job.get('role_version') or job.get('request', {}).get('role_version')
        job.pop("request", None)  # Keep source only in run; no second profile copy.
        job['finished_at'] = now()
        with self.store.connect() as db:
            db.execute("UPDATE jobs SET status = ?, document = ? WHERE id = ?", (job["status"], json.dumps(job), key))
        return True

    def loop(self):
        while not self.stop.is_set():
            try:
                processed = self.process_one()
                self.last_error = None
            except Exception:
                self.last_error = "queue_database_unavailable"
                processed = False
            if not processed:
                self.stop.wait(2 if self.store.backend == "postgresql" else 0.25)

    def cloud_loop(self):
        from .workflow import ScreeningService
        while not self.stop.is_set():
            worker_store = self.store.worker_copy()
            lock = None
            try:
                try:
                    lock = worker_store.acquire_instance()
                except ValueError:
                    # Another revision owns the worker. HTTP remains available.
                    self.last_error = None
                    self.stop.wait(2)
                    continue
                worker = Queue(ScreeningService(worker_store, self.service.provider))
                self.worker = worker
                if self.stop.is_set():
                    break
                worker.recover()
                self.leader = True
                self.last_error = None
                while not self.stop.is_set():
                    processed = worker.process_one()
                    if not processed:
                        self.stop.wait(2)
            except Exception:
                self.last_error = 'worker_connection_unavailable'
                self.stop.wait(2)
            finally:
                self.leader = False
                if lock:
                    lock.close()
                self.worker = None

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=5 if self.store.backend == 'postgresql' else 50)
        # Cloud Run may terminate after ten seconds. Fence any outstanding model
        # call now; its result cannot write after a successor takes ownership.
        if self.worker and self.worker.store.database.instance_lock:
            self.worker.store.database.instance_lock.close()
