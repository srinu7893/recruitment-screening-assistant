from datetime import datetime, timezone, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from screening.database import Database
from screening.deployment import public_origin, allowed_request
from screening import operations
from screening.showcase import seed
from screening.storage import Store, ConflictError


class CloudTests(unittest.TestCase):
    def test_remote_database_requires_verified_tls_and_direct_url(self):
        for url in ['postgresql://x:secret@ep-example.neon.tech/app',
                    'postgresql://x:secret@ep-example-pooler.neon.tech/app?sslmode=verify-full']:
            with self.assertRaises(ValueError) as caught:
                Database(url)
            self.assertNotIn('secret', str(caught.exception))
        db = Database('postgresql://x:secret@ep-example.neon.tech/app?sslmode=verify-full')
        self.assertTrue(db.postgres)
        self.assertEqual(db.parameters['sslmode'], 'verify-full')

    def test_public_origin_preserves_host_and_origin_checks(self):
        origin = public_origin('https://recruit.example.com/')
        self.assertTrue(allowed_request('recruit.example.com', origin, 8000, origin))
        self.assertFalse(allowed_request('attacker.example', origin, 8000, origin))
        self.assertFalse(allowed_request('recruit.example.com', 'https://attacker.example', 8000, origin))
        self.assertFalse(allowed_request('recruit.example.com', 'http://recruit.example.com', 8000, origin))
        for value in ['http://example.com', 'https://example.com/path', 'https://user:secret@example.com', 'https://example.com?x=1']:
            with self.assertRaises(ValueError):
                public_origin(value)

    def test_assignments_revision_validation_and_overdue_workload(self):
        with TemporaryDirectory() as folder:
            store = Store(Path(folder) / 'app.sqlite3')
            key = seed(store)['run_ids'][0]
            past = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
            body = {'revision': 0, 'assignee': 'recruiter', 'priority': 'urgent', 'due_date': past}
            run = operations.assign(store, key, body, 'admin', {'recruiter'})
            self.assertEqual(run['assignment']['assignee'], 'recruiter')
            self.assertTrue(run['demo'])
            self.assertEqual(len(run['assignment_history']), 1)
            with self.assertRaises(ConflictError):
                operations.assign(store, key, body, 'admin', {'recruiter'})
            for change in [{'assignee':'unknown'}, {'due_date':'2026-02-30'}, {'priority':'best candidate'}]:
                with self.assertRaises(ValueError):
                    operations.assign(store, key, {**body, **change, 'revision':1}, 'admin', {'recruiter'})
            metrics = operations.overview(store)['metrics']['workload']
            self.assertEqual((metrics['unassigned'], metrics['overdue']), (5, 1))
            self.assertIn('review_assigned', [a['action'] for a in store.audits()])
