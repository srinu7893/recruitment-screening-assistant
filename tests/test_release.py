import copy
import unittest
from scripts.cloud_release import validate, manifest


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
        self.assertEqual(doc['spec']['traffic'],[{'revisionName':'recruitment-old','percent':100}])

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
