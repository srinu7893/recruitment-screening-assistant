"""Persistent settings, deduplication and a bounded background intake agent."""
import base64
import hashlib
import json
from pathlib import Path
from threading import Event, Lock
import time
from uuid import uuid4

from .documents import extract_upload, MAX_FILE
from .integrations import sync_feed
from .storage import ConflictError, now


class Automation:
    def __init__(self, server, config):
        self.server, self.config = server, config
        self.lock = Lock()
        self.stop = Event()
        self.last_tick = 0
        self.folder = Path(config['inbox_dir']).resolve() if config.get('inbox_dir') else None
        if self.folder:
            self.folder.mkdir(parents=True, exist_ok=True)
        defaults = {'enabled': False, 'role_version': '', 'inbox_enabled': bool(self.folder),
                    'feed_enabled': False, 'interval_seconds': 60, 'revision': 0}
        with self.store.connect() as db:
            db.execute('INSERT OR IGNORE INTO automation_settings VALUES (?, ?)', ('intake', json.dumps(defaults)))

    @property
    def store(self):
        return self.server.queue.store

    def settings(self):
        with self.store.connect() as db:
            return json.loads(db.execute('SELECT document FROM automation_settings WHERE id = ?', ('intake',)).fetchone()[0])

    def update(self, body, actor):
        fields = {'enabled', 'role_version', 'inbox_enabled', 'feed_enabled', 'interval_seconds', 'revision'}
        if not isinstance(body, dict) or set(body) != fields:
            raise ValueError('Provide all automation settings and current revision')
        if any(type(body[k]) is not bool for k in ('enabled', 'inbox_enabled', 'feed_enabled')):
            raise ValueError('Automation switches must be boolean')
        if type(body['interval_seconds']) is not int or not 60 <= body['interval_seconds'] <= 86400:
            raise ValueError('Choose an interval from 60 to 86400 seconds')
        if not isinstance(body['role_version'], str):
            raise ValueError('Select an approved role')
        if body['role_version']:
            self.store.get_role(body['role_version'])
        if body['enabled']:
            if not body['role_version'] or not (body['inbox_enabled'] or body['feed_enabled']):
                raise ValueError('Select an approved role and at least one source')
            if body['inbox_enabled'] and not self.folder:
                raise ValueError('A local inbox is not configured on this server')
            if body['feed_enabled'] and not self.config.get('connector_url'):
                raise ValueError('Configure a JSON feed on the server first')
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            previous = json.loads(db.execute('SELECT document FROM automation_settings WHERE id = ?', ('intake',)).fetchone()[0])
            if type(body['revision']) is not int or body['revision'] != previous['revision']:
                raise ConflictError('Automation settings changed; refresh before saving')
            settings = {**body, 'revision': body['revision'] + 1}
            db.execute('UPDATE automation_settings SET document = ? WHERE id = ?', (json.dumps(settings), 'intake'))
            db.execute('INSERT INTO audit(at, actor, action, target) VALUES (?, ?, ?, ?)',
                       (now(), actor, 'automation_configured', 'intake'))
        self.last_tick = 0
        return settings

    def snapshot(self):
        with self.store.connect() as db:
            events = [json.loads(row[0]) for row in db.execute('SELECT document FROM automation_events ORDER BY at DESC LIMIT 50')]
            records = [json.loads(row[0]) for row in db.execute('SELECT document FROM intake_records')]
        records.sort(key=lambda r: r['at'], reverse=True)
        return {'settings': self.settings(), 'inbox_path': str(self.folder) if self.folder else None,
                'feed_configured': bool(self.config.get('connector_url')),
                'running': self.lock.locked(), 'events': events, 'records': records[:100],
                'record_counts': {'total': len(records), 'queued': sum(r['status'] == 'queued' for r in records),
                                  'failed': sum(r['status'] == 'failed' for r in records)}}

    def event(self, value, store):
        document = {'id': str(uuid4()), 'at': now(), **value}
        with store.connect() as db:
            db.execute('INSERT INTO automation_events VALUES (?, ?, ?)', (document['id'], document['at'], json.dumps(document)))
            for row in db.execute('SELECT id FROM automation_events ORDER BY at DESC LIMIT 10000 OFFSET 200').fetchall():
                db.execute('DELETE FROM automation_events WHERE id = ?', (row[0],))
        return document

    def tick(self, queue, manual=False, actor='intake-agent'):
        if self.stop.is_set():
            return None
        settings = self.settings()
        if not manual and (not settings['enabled'] or time.monotonic() - self.last_tick < settings['interval_seconds']):
            return None
        if not settings['role_version']:
            if manual:
                raise ValueError('Save an approved automation role first')
            return None
        if manual and not (settings['inbox_enabled'] or settings['feed_enabled']):
            raise ValueError('Enable at least one source and save your settings')
        if not self.lock.acquire(blocking=False):
            if manual:
                raise ConflictError('An intake cycle is already running')
            return None
        try:
            self.last_tick = time.monotonic()
            result = {'actor': actor, 'queued': 0, 'failed': 0, 'sources': [], 'status': 'completed'}
            if settings['inbox_enabled'] and self.folder:
                result['sources'].append('resume-inbox')
                self.scan_inbox(queue, settings['role_version'], actor, result)
            if settings['inbox_enabled'] and not self.folder:
                result['failed'] += 1
                result['error'] = 'local_inbox_unavailable_on_this_server'
            if settings['feed_enabled'] and not self.config.get('connector_url'):
                result['failed'] += 1
                result['error'] = 'feed_not_configured_on_this_server'
            if settings['feed_enabled'] and self.config.get('connector_url') and not self.stop.is_set():
                result['sources'].append('configured-feed')
                try:
                    imported = sync_feed(queue, {**self.config, 'connector_role': settings['role_version']}, actor)
                    result['queued'] += len(imported['jobs'])
                    result['failed'] += len(imported['errors'])
                except Exception:
                    result['failed'] += 1
                    result['error'] = 'feed_sync_failed_check_connection'
            if result['failed']:
                result['status'] = 'needs_attention'
            return None if self.stop.is_set() else self.event(result, queue.store)
        finally:
            self.lock.release()

    def scan_inbox(self, queue, role, actor, result):
        processed = 0
        for path in sorted(self.folder.iterdir()):
            if processed >= 20 or self.stop.is_set():
                break
            if path.is_symlink() or not path.is_file() or path.suffix.lower() not in ('.txt', '.pdf', '.docx'):
                continue
            if path.resolve().parent != self.folder:
                continue
            before = path.stat()
            if time.time() - before.st_mtime < 2:
                continue
            if before.st_size <= MAX_FILE:
                with path.open('rb') as source:
                    raw = source.read(MAX_FILE + 1)
            else:
                raw = b''
            after = path.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                continue
            digest = hashlib.sha256(raw).hexdigest() if raw else f'oversize-{before.st_size}-{before.st_mtime_ns}'
            key = hashlib.sha256(json.dumps([path.name, digest, role]).encode()).hexdigest()
            with queue.store.connect() as db:
                receipt = db.execute('SELECT document FROM intake_records WHERE id = ?', (key,)).fetchone()
                if receipt and json.loads(receipt[0])['status'] != 'retry_requested':
                    continue
            processed += 1
            record = {'id': key, 'filename': path.name, 'role_version': role, 'at': now(),
                      'job_id': 'inbox-' + key[:40], 'status': 'queued', 'error': None}
            try:
                if before.st_size > MAX_FILE or len(raw) > MAX_FILE:
                    raise ValueError('File exceeds 5 MB')
                if not self.server.parsing.acquire(blocking=False):
                    result['failed'] += 1
                    continue
                try:
                    extracted = extract_upload(path.name, base64.b64encode(raw).decode())
                finally:
                    self.server.parsing.release()
                if self.stop.is_set():
                    return
                queue.submit({'request_id': record['job_id'], 'role_version': role, 'profile_text': extracted['text']},
                             {'kind': 'resume-inbox', 'filename': path.name, 'display_name': path.name, 'warnings': extracted['warnings'],
                              'malware_scan': extracted.get('malware_scan')}, actor)
                result['queued'] += 1
            except ConflictError:
                result['failed'] += 1
                continue
            except ValueError as exc:
                record.update(status='failed', error=str(exc)[:200])
                result['failed'] += 1
            if not self.stop.is_set():
                with queue.store.connect() as db:
                    if receipt:
                        db.execute('UPDATE intake_records SET document = ? WHERE id = ?', (json.dumps(record), key))
                    else:
                        db.execute('INSERT OR IGNORE INTO intake_records VALUES (?, ?)', (key, json.dumps(record)))

    def retry(self, key, actor):
        if not isinstance(key, str):
            raise ValueError('Select a failed intake record')
        if not self.lock.acquire(blocking=False):
            raise ConflictError('Wait for the current intake cycle before retrying')
        try:
            with self.store.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                row = db.execute('SELECT document FROM intake_records WHERE id = ?', (key,)).fetchone()
                if not row:
                    raise KeyError('Intake record not found')
                record = json.loads(row[0])
                if record['status'] != 'failed':
                    raise ConflictError('Only failed imports can be retried')
                record.update(status='retry_requested', error=None)
                db.execute('UPDATE intake_records SET document = ? WHERE id = ?', (json.dumps(record), key))
                db.execute('INSERT INTO audit(at, actor, action, target) VALUES (?, ?, ?, ?)',
                           (now(), actor, 'intake_retry_requested', key))
            self.last_tick = 0
            return record
        finally:
            self.lock.release()
