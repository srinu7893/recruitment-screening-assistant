import copy
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from scripts.cloud_release import validate, manifest, candidate_tag, wait_for_revision, deploy, command, CloudCommandError


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.config={'project':'screening-project','project_number':'123456789012','region':'asia-south1',
                     'service':'recruitment','repository':'recruitment','runtime_account':'runtime@screening-project.iam.gserviceaccount.com',
                     'public_url':'https://recruitment.example.run.app','iap_audience':'/projects/123456789012/locations/asia-south1/services/recruitment',
                     'provider':'demo','scanner_image':'registry.example/scanner@sha256:'+'b'*64,'secrets':{'DATABASE_URL':{'name':'neon-url','version':'1'},'SCREENING_IAP_ACCOUNTS':{'name':'iap-accounts','version':'1'}}}
        self.image='asia-south1-docker.pkg.dev/screening-project/recruitment/recruitment@sha256:'+'a'*64

    def test_cloud_manifest_enforces_identity_cpu_and_secrets(self):
        doc=manifest(self.config,self.image,'recruitment-gh-123')
        self.assertEqual(doc['metadata']['annotations']['run.googleapis.com/iap-enabled'],'true')
        self.assertEqual(doc['spec']['template']['metadata']['annotations']['run.googleapis.com/cpu-throttling'],'false')
        env=doc['spec']['template']['spec']['containers'][0]['env']
        database=next(e for e in env if e['name']=='DATABASE_URL')
        self.assertNotIn('value',database)
        self.assertEqual(database['valueFrom']['secretKeyRef']['key'],'1')

    def test_existing_traffic_is_pinned_before_candidate_startup(self):
        current={'status':{'latestReadyRevisionName':'recruitment-old','traffic':[{'latestRevision':True,'percent':100}]}}
        doc=manifest(self.config,self.image,'recruitment-new',current)
        self.assertEqual(doc['spec']['traffic'],[
            {'revisionName':'recruitment-old','percent':100},
            {'revisionName':'recruitment-new','percent':0,'tag':candidate_tag('recruitment-new')}])
        self.assertEqual(doc['spec']['template']['metadata']['annotations']['autoscaling.knative.dev/minScale'], '1')

    def test_waits_for_image_import_and_does_not_accept_retired_ready_revision(self):
        states = [
            {'status': {'conditions': [{'type':'Ready','status':'Unknown','reason':'Deploying'}]}},
            {'status': {'conditions': [{'type':'Ready','status':'True','reason':'Retired'}]}},
            {'status': {'conditions': [{'type':'Ready','status':'True'}, {'type':'Active','status':'True'}]}},
        ]
        with TemporaryDirectory() as folder, patch('scripts.cloud_release.command', side_effect=[json.dumps(s) for s in states]) as run, patch('scripts.cloud_release.time.sleep') as sleep:
            result = wait_for_revision(self.config, 'recruitment-new', Path(folder))
            self.assertEqual(result, states[-1])
            self.assertEqual(run.call_count, 3)
            self.assertEqual(sleep.call_count, 2)
            self.assertTrue((Path(folder) / 'candidate-status.json').exists())

    def test_startup_failure_keeps_old_traffic_and_removes_only_candidate_tag(self):
        current = {'status': {'url': self.config['public_url'], 'traffic': [{'revisionName':'recruitment-old','percent':100}]}}
        replies = [json.dumps([{'metadata':{'name':'recruitment'}}]), json.dumps(current), '', '']
        with TemporaryDirectory() as folder, patch('scripts.cloud_release.command', side_effect=replies) as run, patch('scripts.cloud_release.wait_for_revision', side_effect=ValueError('Scanner startup failed')):
            with self.assertRaisesRegex(ValueError, 'Scanner startup failed'):
                deploy(self.config, self.image, 'recruitment-new', Path(folder))
            commands = [call.args[0] for call in run.call_args_list]
            self.assertFalse(any('--to-revisions' in args for args in commands))
            self.assertIn('--remove-tags', commands[-1])
            saved = json.loads((Path(folder) / 'previous-traffic.json').read_text())
            self.assertEqual(saved, [{'revisionName':'recruitment-old','percent':100}])
            self.assertIn('Scanner startup failed', (Path(folder) / 'error.json').read_text())

    def test_promotes_only_after_readiness_and_removes_temporary_tag(self):
        current = {'status': {'url': self.config['public_url'], 'traffic': [{'revisionName':'recruitment-old','percent':100}]}}
        with TemporaryDirectory() as folder, patch('scripts.cloud_release.command', side_effect=[json.dumps([{'metadata':{'name':'recruitment'}}]),json.dumps(current),'','']) as run, patch('scripts.cloud_release.wait_for_revision') as ready:
            deploy(self.config, self.image, 'recruitment-new', Path(folder))
            ready.assert_called_once()
            promotion = run.call_args_list[-1].args[0]
            self.assertIn('--to-revisions', promotion)
            self.assertIn('recruitment-new=100', promotion)
            self.assertIn(candidate_tag('recruitment-new'), promotion)

    def test_failed_cloud_command_reports_reason_without_credentials(self):
        failure = subprocess.CalledProcessError(1, ['gcloud'], stderr='PERMISSION_DENIED: run.services.update failed; postgresql://user:private@host/db Bearer private-token password=private-password')
        with patch('scripts.cloud_release.subprocess.run', side_effect=failure):
            with self.assertRaises(CloudCommandError) as caught:
                command(['gcloud','run','services','replace','service.json'])
        message = str(caught.exception)
        self.assertIn('run.services.update', message)
        self.assertNotIn('private', message)

    def test_startup_probe_failure_is_reported_immediately(self):
        state = {'status': {'conditions': [{'type':'Ready','status':'False','message':'Scanner failed its startup probe'}]}}
        with TemporaryDirectory() as folder, patch('scripts.cloud_release.command', return_value=json.dumps(state)), patch('scripts.cloud_release.time.sleep') as sleep:
            with self.assertRaisesRegex(ValueError, 'Scanner failed its startup probe'):
                wait_for_revision(self.config, 'recruitment-new', Path(folder))
            sleep.assert_not_called()

    def test_wait_has_a_bounded_deadline(self):
        state = {'status': {'conditions': [{'type':'Ready','status':'Unknown'}]}}
        with TemporaryDirectory() as folder, patch('scripts.cloud_release.command', return_value=json.dumps(state)), patch('scripts.cloud_release.time.monotonic', side_effect=[0,0,601]), patch('scripts.cloud_release.time.sleep'):
            with self.assertRaisesRegex(ValueError, 'Timed out'):
                wait_for_revision(self.config, 'recruitment-new', Path(folder))

    def test_rejects_mutable_image_unpinned_secret_and_placeholders(self):
        with self.assertRaises(ValueError):manifest(self.config,self.image.split('@')[0]+':latest','recruitment-new')
        c=copy.deepcopy(self.config);c['secrets']['DATABASE_URL']['version']='latest'
        with self.assertRaises(ValueError):validate(c)

    def test_cloud_feed_configuration_is_wired_and_rejects_unsafe_sources(self):
        c = {**self.config, 'allowed_hosts': ['ats.example.com'],
             'connector_url': 'https://ats.example.com/resumes', 'connector_role': 'support:v1',
             'sync_seconds': 300, 'retention_days': 90, 'database_schema': 'recruitment'}
        env = {row['name']: row.get('value') for row in manifest(c, self.image, 'recruitment-new')['spec']['template']['spec']['containers'][0]['env']}
        self.assertEqual(env['SCREENING_ALLOWED_HOSTS'], 'ats.example.com')
        self.assertEqual(env['SCREENING_CONNECTOR_URL'], c['connector_url'])
        self.assertEqual(env['SCREENING_SYNC_SECONDS'], '300')
        self.assertEqual(env['SCREENING_RETENTION_DAYS'], '90')
        self.assertEqual(env['SCREENING_DB_SCHEMA'], 'recruitment')
        for changes in [{'connector_url': 'http://ats.example.com/resumes'},
                        {'connector_url': 'https://other.example.com/resumes'},
                        {'connector_url': 'https://user:secret@ats.example.com/resumes'},
                        {'allowed_hosts': ['*.example.com']}, {'sync_seconds': 1},
                        {'retention_days': -1}, {'connector_role': ''},
                        {'iap_audience': '/projects/123456789012/locations/other/services/other'}]:
            with self.assertRaises(ValueError):
                validate({**c, **changes})
        for schema in ['public,recruitment', 'pg_catalog', 'bad;sql']:
            with self.assertRaises(ValueError):
                validate({**c, 'database_schema': schema})
        c=copy.deepcopy(self.config);c['project']='replace-project'
        with self.assertRaises(ValueError):validate(c)
