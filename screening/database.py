"""Small DB-API boundary for the app's fixed SQL; never accepts user SQL."""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import sqlite3
import threading
from urllib.parse import urlsplit, parse_qs


class DatabaseUnavailable(RuntimeError):
    pass


class Connection:
    def __init__(self, raw, postgres):
        self.raw, self.postgres = raw, postgres

    def execute(self, sql, args=()):
        if self.postgres:
            if sql == 'BEGIN IMMEDIATE':
                # Serialize read/modify/write transactions, including queue capacity checks.
                sql = 'SELECT pg_advisory_xact_lock(74628190)'
            if sql.startswith('INSERT OR IGNORE INTO '):
                sql = sql.replace('INSERT OR IGNORE INTO ', 'INSERT INTO ', 1) + ' ON CONFLICT DO NOTHING'
            sql = sql.replace('?', '%s')
        return self.raw.execute(sql, args)

    def executescript(self, sql):
        for statement in sql.split(';'):
            if statement.strip():
                self.execute(statement)


class InstanceLock:
    def __init__(self, database):
        self.database = database
        self.guard = threading.Lock()
        self.closed = False
        if database.postgres:
            self.raw = database.open_raw(autocommit=True)
            if not self.raw.execute('SELECT pg_try_advisory_lock(74628191)').fetchone()[0]:
                self.raw.close()
                raise ValueError('Another server already uses this database; stop it before deploying')
        else:
            self.raw = open(str(database.path) + '.lock', 'a')
            try:
                fcntl.flock(self.raw, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                self.raw.close()
                raise ValueError('Another server already uses this database') from None

    def check(self):
        with self.guard:
            if self.closed:
                raise DatabaseUnavailable('Database ownership lost; restart the service')
            if self.database.postgres:
                try:
                    self.raw.execute('SELECT 1')
                except Exception:
                    self.closed = True
                    self.raw.close()
                    raise DatabaseUnavailable('Database ownership lost; restart the service') from None

    def close(self):
        with self.guard:
            self.closed = True
            self.raw.close()


class Database:
    def __init__(self, location):
        self.postgres = str(location).startswith(('postgres://', 'postgresql://'))
        self.instance_lock = None
        if self.postgres:
            from psycopg.conninfo import conninfo_to_dict
            try:
                self.parameters = conninfo_to_dict(str(location))
                parts = urlsplit(str(location))
                host = self.parameters.get('host', '')
                if not host or ',' in host or '-pooler' in host or self.parameters.get('hostaddr'):
                    raise ValueError()
                if host not in ('localhost', '127.0.0.1', '::1'):
                    if self.parameters.get('sslmode') != 'verify-full':
                        raise ValueError()
                    self.parameters.setdefault('sslrootcert', '/etc/ssl/certs/ca-certificates.crt')
                self.parameters.update(connect_timeout='10', application_name='recruitment-screening',
                                       options='-c statement_timeout=15000 -c lock_timeout=10000')
            except Exception:
                raise ValueError('DATABASE_URL must be a direct PostgreSQL URL with sslmode=verify-full for remote hosts') from None
            self.path = None
        else:
            self.path = Path(location)
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            if not self.path.exists():
                self.path.touch(mode=0o600, exist_ok=False)

    def open_raw(self, autocommit=False):
        if self.postgres:
            import psycopg
            try:
                return psycopg.connect(**self.parameters, autocommit=autocommit)
            except psycopg.Error:
                raise DatabaseUnavailable('Database connection unavailable') from None
        raw = sqlite3.connect(self.path, timeout=10)
        raw.execute('PRAGMA secure_delete=ON')
        return raw

    @contextmanager
    def connect(self):
        if self.instance_lock and self.postgres:
            # Use the owning session itself: a lost lock can never write through a
            # separate surviving connection. No transparent reconnection/rebilling.
            lock = self.instance_lock
            with lock.guard:
                if lock.closed:
                    raise DatabaseUnavailable('Database ownership lost; restart the service')
                try:
                    with lock.raw.transaction():
                        yield Connection(lock.raw, True)
                except Exception as exc:
                    import psycopg
                    if isinstance(exc, psycopg.OperationalError):
                        lock.closed = True
                        lock.raw.close()
                        raise DatabaseUnavailable('Database ownership lost; restart the service') from None
                    raise
            return
        if self.instance_lock:
            self.instance_lock.check()
        raw = self.open_raw()
        try:
            with raw:
                yield Connection(raw, self.postgres)
        finally:
            raw.close()

    def acquire_instance(self):
        lock = InstanceLock(self)
        self.instance_lock = lock
        return lock
