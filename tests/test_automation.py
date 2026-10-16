"""Real local intake, persistence, safe recovery and access boundaries."""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import BoundedSemaphore
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from screening.automation import Automation
from screening.jobs import Queue
from screening.providers import DemoProvider
from screening.showcase import dataset
from screening.storage import Store, ConflictError
from screening.workflow import ScreeningService


class AutomationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.store = Store(self.folder / 'app.sqlite3')
        self.service = ScreeningService(self.store, DemoProvider())
        self.role = dataset()['role']
        self.service.create_role(self.role)
        self.queue = Queue(self.service)
        self.server = SimpleNamespace(queue=self.queue, parsing=BoundedSemaphore(2))
        self.agent = Automation(self.server, {'inbox_dir': str(self.folder / 'inbox')})
        self.settings = {**self.agent.settings(), 'enabled': True, 'role_version': self.role['role_version']}
        self.agent.update(self.settings, 'admin')

    def resume(self, content='Built Python APIs. Maintained Linux production services.', name='resume.txt'):
        path = self.agent.folder / name
        path.write_text(content, encoding='utf-8')
        os.utime(path, (1, 1))
        return path

    def test_real_extraction_queue_review_and_restart_deduplication(self):
        self.resume()
        event = self.agent.tick(self.queue, manual=True)
        self.assertEqual((event['queued'], event['failed']), (1, 0))
        receipt = self.agent.snapshot()['records'][0]
        self.assertTrue(self.queue.process_one())
        run = self.store.get_run(receipt['job_id'])
        self.assertEqual(run['status'], 'awaiting_review')
        self.assertEqual(run['source']['kind'], 'resume-inbox')
        self.assertNotIn('profile_text', json.dumps(self.agent.snapshot()))
        restarted = Automation(self.server, self.agent.config)
        self.assertTrue(restarted.settings()['enabled'])
        self.assertEqual(restarted.tick(self.queue, manual=True)['queued'], 0)
        self.assertEqual(len(self.queue.list()), 1)

    def test_changed_file_and_new_role_are_new_screenings(self):
        self.resume()
        self.agent.tick(self.queue, manual=True)
        self.resume('Changed profile with PostgreSQL experience.')
        self.assertEqual(self.agent.tick(self.queue, manual=True)['queued'], 1)
        self.service.create_role({**self.role, 'role_version': 'support:v2'})
        self.agent.update({**self.agent.settings(), 'role_version': 'support:v2'}, 'admin')
        self.assertEqual(self.agent.tick(self.queue, manual=True)['queued'], 1)
        self.assertEqual(len(self.queue.list()), 3)

    def test_failed_scan_explicit_retry_preserves_failure_until_requested(self):
        self.resume()
        with patch('screening.automation.extract_upload', side_effect=ValueError('Scanner unavailable; upload blocked')):
            self.assertEqual(self.agent.tick(self.queue, manual=True)['failed'], 1)
        receipt = self.agent.snapshot()['records'][0]
        self.assertEqual(receipt['status'], 'failed')
        self.assertEqual(self.agent.tick(self.queue, manual=True)['queued'], 0)
        self.agent.retry(receipt['id'], 'admin')
        self.assertEqual(self.agent.tick(self.queue, manual=True)['queued'], 1)
        self.assertEqual(self.agent.snapshot()['records'][0]['status'], 'queued')
        self.assertIn('intake_retry_requested', [e['action'] for e in self.store.audits()])

    def test_deleted_record_leaves_redacted_tombstone_and_is_not_reimported(self):
        self.resume()
        self.agent.tick(self.queue, manual=True)
        self.queue.process_one()
        receipt = self.agent.snapshot()['records'][0]
        self.store.delete_run(receipt['job_id'], 'admin')
        self.assertEqual(self.agent.tick(self.queue, manual=True)['queued'], 0)
        redacted = self.agent.snapshot()['records'][0]
        self.assertEqual(redacted['filename'], '[deleted]')
        self.assertEqual(redacted['job_id'], '')
        self.assertEqual(len(self.queue.list()), 0)

    def test_validation_pause_conflicts_and_source_availability(self):
        settings = self.agent.settings()
        for changes in [{'interval_seconds': 1}, {'enabled': 'true'}, {'role_version': ''}, {'feed_enabled': True}]:
            with self.assertRaises((ValueError, KeyError)):
                self.agent.update({**settings, **changes}, 'admin')
        with self.assertRaises(ConflictError):
            self.agent.update(self.settings, 'admin')
        self.agent.update({**settings, 'enabled': False}, 'admin')
        self.resume()
        self.assertIsNone(self.agent.tick(self.queue))
        self.assertEqual(self.agent.tick(self.queue, manual=True)['queued'], 1)

    def test_queue_capacity_retries_next_cycle_and_busy_parser_does_not_mark_failed(self):
        self.resume()
        with patch.object(self.queue, 'submit', side_effect=ConflictError('Queue is full')):
            self.assertEqual(self.agent.tick(self.queue, manual=True)['failed'], 1)
        self.assertEqual(self.agent.snapshot()['records'], [])
        self.server.parsing.acquire(); self.server.parsing.acquire()
        try:
            self.assertEqual(self.agent.tick(self.queue, manual=True)['queued'], 0)
            self.assertEqual(self.agent.snapshot()['records'], [])
        finally:
            self.server.parsing.release(); self.server.parsing.release()
        self.assertEqual(self.agent.tick(self.queue, manual=True)['queued'], 1)

    def test_feed_error_has_durable_activity_and_no_response_or_secret_leak(self):
        self.agent.config['connector_url'] = 'https://example.invalid/feed'
        self.agent.update({**self.agent.settings(), 'feed_enabled': True, 'inbox_enabled': False}, 'admin')
        with patch('screening.automation.sync_feed', side_effect=RuntimeError('private remote body')):
            event = self.agent.tick(self.queue, manual=True)
        self.assertEqual(event['status'], 'needs_attention')
        self.assertNotIn('private remote body', json.dumps(self.agent.snapshot()))
        self.assertEqual(len(self.agent.snapshot()['events']), 1)

    def test_stop_prevents_imports_and_unsupported_files_are_ignored(self):
        self.resume(name='not-a-resume.exe')
        self.assertEqual(self.agent.tick(self.queue, manual=True)['queued'], 0)
        self.resume()
        self.agent.stop.set()
        self.assertIsNone(self.agent.tick(self.queue, manual=True))
        self.assertEqual(self.queue.list(), [])
