"""Real PostgreSQL integration tests; dedicated local CI database only."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import unittest
from urllib.parse import urlsplit
from screening.storage import Store, ConflictError
from screening.workflow import ScreeningService
from screening.providers import DemoProvider
from screening.jobs import Queue
from screening.showcase import seed
from screening import operations
from screening.database import DatabaseUnavailable


@unittest.skipUnless(os.getenv('TEST_DATABASE_URL'), 'PostgreSQL integration service not configured')
class PostgreSQLTests(unittest.TestCase):
    def setUp(self):
        self.url = os.environ['TEST_DATABASE_URL']
        parts = urlsplit(self.url)
        if parts.hostname not in ('127.0.0.1', 'localhost') or parts.path != '/screening_test':
            self.fail('Tests may reset only the dedicated localhost screening_test database')
        self.store = Store(self.url)
        with self.store.connect() as db:
            db.execute('TRUNCATE roles, runs, jobs, audit, webhook_events RESTART IDENTITY')

    def test_persistence_deduplication_review_and_delete(self):
        keys = seed(self.store)['run_ids']
        self.assertEqual(keys, seed(Store(self.url))['run_ids'])
        run = operations.note(self.store, keys[0], {'revision':0,'text':'Verify Linux example'}, 'reviewer')
        self.assertEqual(Store(self.url).get_run(keys[0])['notes'], run['notes'])
        self.assertEqual(len(operations.compare(self.store, keys[:2])['candidates']), 2)
        self.store.delete_run(keys[0], 'admin')
        self.assertEqual(len(Store(self.url).list_runs()), 5)

    def test_concurrent_updates_and_job_capacity_transactions(self):
        key = seed(self.store)['run_ids'][0]
        def change(_):
            try:
                operations.note(self.store, key, {'revision':0,'text':'Test'}, 'reviewer')
                return True
            except ConflictError:
                return False
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(sum(pool.map(change, range(4))), 1)
        role = self.store.list_roles()[0]
        queue = Queue(ScreeningService(self.store, DemoProvider()))
        request = {'request_id':'queued-test','profile_text':'Used Linux logs','role_version':role['role_version']}
        with ThreadPoolExecutor(max_workers=4) as pool:
            jobs = list(pool.map(lambda _: queue.submit(request), range(4)))
        self.assertEqual(len({j['id'] for j in jobs}), 1)
        self.assertTrue(queue.process_one())
        self.assertFalse(queue.process_one())
        self.assertEqual(Store(self.url).get_run('queued-test')['status'], 'awaiting_review')

    def test_sqlite_migration_preserves_records_and_refuses_nonempty_target(self):
        from tempfile import TemporaryDirectory
        from screening.migrate import migrate
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'old.sqlite3'
            source = Store(path)
            keys = seed(source)['run_ids']
            counts = migrate(path, self.url)
            self.assertEqual(counts['runs'], 6)
            self.assertEqual(Store(self.url).get_run(keys[0]), source.get_run(keys[0]))
            Store(self.url).audit('admin', 'post_migration', 'system')
            with self.assertRaisesRegex(ValueError, 'empty'):
                migrate(path, self.url)
            self.assertEqual(len(Store(self.url).list_runs()), 6)
            self.assertEqual(len(source.list_runs()), 6)

    def test_instance_ownership_and_connection_loss_fence_writes(self):
        lock = self.store.acquire_instance()
        try:
            self.assertTrue(self.store.ready())
            with self.assertRaisesRegex(ValueError, 'Another server'):
                Store(self.url).acquire_instance()
            seed(self.store)
            lock.raw.close()
            with self.assertRaises(DatabaseUnavailable):
                self.store.audit('admin','should_not_write','system')
        finally:
            lock.close()
        new_store = Store(self.url)
        replacement = new_store.acquire_instance()
        try:
            self.assertEqual(len(new_store.list_runs()), 6)
            self.assertNotIn('should_not_write', [a['action'] for a in new_store.audits()])
        finally:
            replacement.close()
