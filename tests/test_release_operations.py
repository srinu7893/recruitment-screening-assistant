import copy
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
import sys
from unittest.mock import patch

from cryptography.fernet import Fernet
from screening.storage import Store
from scripts.scheduled_backup import run_backup, validate
from scripts.cloud_smoke import Session, verify_team


class BackupReleaseTests(unittest.TestCase):
    def setUp(self):
        self.config = {'project': 'example-project', 'schema': 'recruitment_production',
                       'bucket': 'recruitment-backups-example',
                       'database_secret': {'name': 'recruitment-database', 'version': '1'},
                       'key_secret': {'name': 'recruitment-backup-key', 'version': '1'}}

    def test_backup_configuration_excludes_unscoped_schema_secrets_and_unpinned_versions(self):
        self.assertEqual(validate(self.config), self.config)
        for field, value in [('schema', 'public'), ('schema', 'payment'), ('bucket', '../private'),
                             ('database_secret', {'name': 'neon-password', 'version': '1'}),
                             ('key_secret', {'name': 'recruitment-key', 'version': 'latest'})]:
            config = copy.deepcopy(self.config); config[field] = value
            with self.assertRaises(ValueError):
                validate(config)

    def test_failed_upload_cleans_up_plaintext_key_and_restores_environment(self):
        key = Fernet.generate_key()
        seen = []
        def command(args):
            if args[1:4] == ['secrets', 'versions', 'access']:
                return key.decode() if 'recruitment-backup-key' in args else 'postgresql://user:private@db.example/db?sslmode=verify-full'
            archive = Path(args[3]); seen.append(archive)
            payload = json.loads(Fernet(key).decrypt(archive.read_bytes()))
            self.assertEqual(payload['format'], 'screening-backup-v1')
            self.assertEqual(args[-2:], ['--if-generation-match=0', '--quiet'])
            self.assertNotIn(b'private', archive.read_bytes())
            raise RuntimeError('simulated upload failure')
        with TemporaryDirectory() as directory:
            store = Store(Path(directory) / 'snapshot.sqlite3')
            # Exercise real snapshot encryption; the DB factory is replaced only to avoid a network dependency.
            class Database:
                parameters = {'options': ''}
                connect = store.connect
            with patch.dict(os.environ, {'SCREENING_DB_SCHEMA': 'original'}), \
                    patch('scripts.scheduled_backup.command', side_effect=command), \
                    patch('screening.database.Database', return_value=Database()), \
                    patch('screening.backup.capture', return_value={'format': 'screening-backup-v1', 'tables': {}}):
                with self.assertRaises(RuntimeError):
                    run_backup(self.config)
                self.assertEqual(os.environ['SCREENING_DB_SCHEMA'], 'original')
            self.assertEqual(len(seen), 1)
            self.assertFalse(seen[0].parent.exists())

    def test_insecure_database_fails_before_reading_key_or_uploading(self):
        for url in ['postgresql://u:p@db.example/db?sslmode=require',
                    'postgresql://u:p@host-pooler.example/db?sslmode=verify-full']:
            with patch('scripts.scheduled_backup.command', return_value=url) as command:
                with self.assertRaises(ValueError):
                    run_backup(self.config)
                self.assertEqual(command.call_count, 1)

    def test_downloaded_restore_drill_cleans_temporary_key_on_failure_without_initializing_production(self):
        from scripts import cloud_ops
        captured = []
        key = Fernet.generate_key().decode()
        def command(args):
            if 'secrets' in args:
                return key
            Path(args[4]).write_bytes(b'encrypted archive')
            return ''
        def fail(url, schema, archive, key_file, project):
            captured.append(Path(key_file))
            self.assertEqual(Path(key_file).read_text(), key)
            self.assertEqual(Path(archive).read_bytes(), b'encrypted archive')
            raise RuntimeError('simulated drill failure')
        with patch.object(sys, 'argv', ['cloud_ops', 'restore-drill', '--archive',
                                      'gs://recruitment-backups-example/snapshots/test.encrypted']), \
                patch('scripts.cloud_ops.configuration', return_value=('recruitment_production', 'private-url', [])), \
                patch('scripts.cloud_ops.command', side_effect=command), \
                patch('scripts.cloud_ops.restore_drill', side_effect=fail), \
                patch('screening.storage.Store') as store, \
                patch.dict(os.environ):
            with self.assertRaises(RuntimeError):
                cloud_ops.main()
            store.assert_not_called()
        self.assertEqual(len(captured), 1)
        self.assertFalse(captured[0].parent.exists())


class LiveTeamCheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from screening.password_auth import hash_password
        cls.password = 'synthetic-long-admin-password'
        cls.account = {'username': 'admin', 'name': 'Admin', 'role': 'admin', 'password_hash': hash_password(cls.password)}

    def test_post_deployment_account_check_uses_real_http_and_disables_test_account(self):
        from screening.server import make_server
        from screening.workflow import ScreeningService
        from screening.rules import RulesProvider
        with TemporaryDirectory() as directory:
            store = Store(Path(directory) / 'application.sqlite3')
            with patch.dict(os.environ, {'SCREENING_AUTH_MODE': 'password',
                                         'SCREENING_PASSWORD_ACCOUNTS': json.dumps([self.account])}):
                server = make_server(ScreeningService(store, RulesProvider()), port=0)
            thread = Thread(target=server.serve_forever, daemon=True); thread.start()
            try:
                client = Session(f'http://127.0.0.1:{server.server_port}')
                client.login('admin', self.password)
                verify_team(client, self.password)
                accounts = client.call('/accounts')['accounts']
                synthetic = [a for a in accounts if a['username'].startswith('smoke-')]
                self.assertEqual(len(synthetic), 1)
                self.assertTrue(synthetic[0]['disabled'])
                self.assertNotIn('password_hash', str(accounts))
            finally:
                server.shutdown(); server.server_close(); thread.join()


if __name__ == '__main__':
    unittest.main()
