import json
import unittest
from unittest.mock import patch, MagicMock
from scripts import production_setup as setup


class ProductionSetupTests(unittest.TestCase):
    def test_refuses_publication_of_bootstrap_or_misconfigured_revision(self):
        service = {'metadata':{},'status':{'url':'https://example.run.app','latestReadyRevisionName':'ready',
                                          'latestCreatedRevisionName':'ready','traffic':[{'revisionName':'ready','percent':100}]}}
        with patch('sys.argv',['production_setup','publish']), patch.object(setup,'describe',return_value=service), patch.object(setup,'run',return_value=json.dumps({'spec':{'containers':[{'image':'hello'}]}})) as command:
            with self.assertRaisesRegex(SystemExit,'Refusing publication'):
                setup.main()
            self.assertFalse(any('add-iam-policy-binding' in call.args[0] for call in command.call_args_list))

    def test_production_schema_owner_checked_without_logging_credentials(self):
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.execute.return_value.fetchone.return_value = ('recruitment_app',)
        with patch.object(setup,'run',side_effect=['postgresql://recruitment_app:private@direct.neon.tech/neondb?sslmode=verify-full','owner','private']), patch('psycopg.connect',return_value=connection) as connect, patch('builtins.print') as output:
            setup.provision_schema()
            self.assertEqual(connect.call_args.kwargs['sslmode'],'verify-full')
            self.assertEqual(connect.call_args.kwargs['sslrootcert'],'/etc/ssl/certs/ca-certificates.crt')
            self.assertNotIn('private',str(output.call_args_list))
            self.assertIn('recruitment_production',str(connection.execute.call_args_list))


if __name__ == '__main__':
    unittest.main()
