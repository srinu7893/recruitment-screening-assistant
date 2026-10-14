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

    def wait_for(self, predicate, timeout=12):
        import time
        deadline = time.monotonic()+timeout
        while time.monotonic()<deadline:
            if predicate():
                return
            time.sleep(.05)
        self.fail('Timed out waiting for cloud worker state')

    def test_overlapping_revisions_and_worker_handoff(self):
        seed(self.store)
        q1 = Queue(ScreeningService(self.store, DemoProvider()))
        q2 = Queue(ScreeningService(Store(self.url), DemoProvider()))
        q1.start(); q2.start()
        try:
            self.wait_for(lambda: q1.leader != q2.leader)
            leader, standby = (q1,q2) if q1.leader else (q2,q1)
            self.assertTrue(standby.store.ready())
            role = self.store.list_roles()[0]['role_version']
            standby.submit({'request_id':'overlap-job','role_version':role,'profile_text':'Used Linux logs'})
            self.wait_for(lambda: any(j['id']=='overlap-job' and j['status']=='completed' for j in standby.list()))
            leader.close()
            self.wait_for(lambda: standby.leader)
            standby.submit({'request_id':'after-handoff','role_version':role,'profile_text':'Used SQL queries'})
            self.wait_for(lambda: any(j['id']=='after-handoff' and j['status']=='completed' for j in standby.list()))
        finally:
            q1.close(); q2.close()

    def test_lost_leader_does_not_repeat_or_overwrite_inflight_model_call(self):
        from threading import Event
        started, finish = Event(), Event()
        class SlowProvider(DemoProvider):
            calls = 0
            def analyze(inner, *args):
                inner.calls += 1
                started.set()
                finish.wait(15)
                return super().analyze(*args)
        seed(self.store)
        provider = SlowProvider()
        q1 = Queue(ScreeningService(self.store, provider)); q1.start()
        q2 = Queue(ScreeningService(Store(self.url), provider))
        try:
            self.wait_for(lambda:q1.leader)
            role = self.store.list_roles()[0]['role_version']
            q1.submit({'request_id':'interrupted','role_version':role,'profile_text':'Used Linux logs'})
            self.assertTrue(started.wait(5))
            q1.stop.set()
            q1.worker.store.database.instance_lock.close()
            q2.start()
            self.wait_for(lambda:q2.leader)
            self.wait_for(lambda:self.store.get_run('interrupted')['status']=='failed')
            finish.set()
            q1.thread.join(timeout=5)
            self.assertEqual(provider.calls,1)
            self.assertEqual(self.store.get_run('interrupted')['error'],'interrupted_retry_with_new_id')
        finally:
            finish.set(); q1.close(); q2.close()

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
