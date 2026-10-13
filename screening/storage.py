"""Single-user SQLite persistence. Use a private, local data directory."""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3


def now():
    return datetime.now(timezone.utc).isoformat()


class ConflictError(ValueError):
    pass


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Create with private permissions rather than relying on the caller's umask.
        if not self.path.exists():
            self.path.touch(mode=0o600, exist_ok=False)
        with self.connect() as db:
            db.executescript("""
                PRAGMA secure_delete=ON;
                CREATE TABLE IF NOT EXISTS roles (
                    version TEXT PRIMARY KEY, document TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, document TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, status TEXT NOT NULL,
                    document TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS audit (
                    id INTEGER PRIMARY KEY, at TEXT NOT NULL, actor TEXT NOT NULL,
                    action TEXT NOT NULL, target TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS webhook_events (
                    id TEXT PRIMARY KEY, at REAL NOT NULL);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.execute("PRAGMA secure_delete=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def create_role(self, role):
        document = {**role, "approved_at": now()}
        try:
            with self.connect() as db:
                db.execute("INSERT INTO roles VALUES (?, ?)",
                           (role["role_version"], json.dumps(document)))
        except sqlite3.IntegrityError:
            raise ConflictError("Role version already exists; create a new version") from None
        return document

    def get_role(self, version):
        with self.connect() as db:
            row = db.execute("SELECT document FROM roles WHERE version = ?", (version,)).fetchone()
        if row is None:
            raise KeyError("Role not found")
        return json.loads(row[0])

    def start_run(self, run, fingerprint):
        with self.connect() as db:
            cursor = db.execute("INSERT OR IGNORE INTO runs VALUES (?, ?, ?)",
                                (run["run_id"], fingerprint, json.dumps(run)))
            if cursor.rowcount == 1:
                return run, True
            row = db.execute("SELECT fingerprint, document FROM runs WHERE id = ?",
                             (run["run_id"],)).fetchone()
        if row[0] != fingerprint:
            raise ConflictError("request_id was already used with different input or provider")
        return json.loads(row[1]), False

    def save_run(self, run):
        with self.connect() as db:
            db.execute("UPDATE runs SET document = ? WHERE id = ?",
                       (json.dumps(run), run["run_id"]))

    def list_roles(self):
        with self.connect() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT document FROM roles ORDER BY rowid DESC")]

    def list_runs(self):
        with self.connect() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT document FROM runs ORDER BY rowid DESC")]

    def audit(self, actor, action, target):
        with self.connect() as db:
            db.execute("INSERT INTO audit(at, actor, action, target) VALUES (?, ?, ?, ?)",
                       (now(), actor, action, target))

    def audits(self):
        with self.connect() as db:
            return [dict(zip(("id", "at", "actor", "action", "target"), row)) for row in
                    db.execute("SELECT id, at, actor, action, target FROM audit ORDER BY id DESC LIMIT 200")]

    def mutate_run(self, run_id, revision, actor, action, change):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT document FROM runs WHERE id = ?", (run_id,)).fetchone()
            if not row:
                raise KeyError("Run not found")
            run = json.loads(row[0])
            if type(revision) is not int or revision != run.get("revision", 0):
                raise ConflictError("The review changed; refresh before saving")
            if run["status"] not in ("awaiting_review", "completed"):
                raise ConflictError("Run is not ready for review")
            change(run)
            run["revision"] = revision + 1
            db.execute("UPDATE runs SET document = ? WHERE id = ?", (json.dumps(run), run_id))
            db.execute("INSERT INTO audit(at, actor, action, target) VALUES (?, ?, ?, ?)",
                       (now(), actor, action, run_id))
        return run

    def delete_run(self, run_id, actor):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT document FROM runs WHERE id = ?", (run_id,)).fetchone()
            job = db.execute("SELECT status FROM jobs WHERE id = ?", (run_id,)).fetchone()
            if not row and not job:
                raise KeyError("Run not found")
            if (row and json.loads(row[0])["status"] in ("received", "evaluating", "validating")) or (job and job[0] in ("queued", "processing")):
                raise ConflictError("Wait for processing to finish before deleting")
            db.execute("DELETE FROM runs WHERE id = ?", (run_id,))
            db.execute("DELETE FROM jobs WHERE id = ?", (run_id,))
            db.execute("DELETE FROM audit WHERE target = ?", (run_id,))
            db.execute("INSERT INTO audit(at, actor, action, target) VALUES (?, ?, ?, ?)",
                       (now(), actor, "record_deleted", "redacted"))

    def get_run(self, run_id):
        with self.connect() as db:
            row = db.execute("SELECT document FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise KeyError("Run not found")
        return json.loads(row[0])
