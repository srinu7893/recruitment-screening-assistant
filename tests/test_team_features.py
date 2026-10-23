import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor

from screening.storage import Store,ConflictError
from screening.password_auth import PasswordAuth,hash_password
from screening.workflow import ScreeningService
from screening.rules import RulesProvider,preview
from screening.jobs import Queue
from screening.backup import write_backup,restore
from screening.monitoring import snapshot


class TeamFeatureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password='long-admin-password-for-team-tests'
        cls.admin={'username':'admin','name':'Admin','role':'admin','password_hash':hash_password(cls.password)}
        cls.user_password='long-individual-user-password'

    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=Store(Path(self.temp.name)/'app.sqlite3')
        self.auth=PasswordAuth(self.store,[self.admin],False)
        self.role={'role_version':'support:v1','title':'Support','approved_by':'Admin','criteria':[
            {'id':'python','description':'Support scripting','phrases':['Python'],'required':True,'question':'Describe your work.'}]}

    def test_phrase_preview_warning_approval_and_old_role_compatibility(self):
        missing=copy.deepcopy(self.role);missing['criteria'][0]['phrases']=[]
        self.assertTrue(preview(missing,'Used Python')['warnings'])
        service=ScreeningService(self.store,RulesProvider())
        with self.assertRaisesRegex(ValueError,'matching phrases'):service.create_role(missing)
        self.assertEqual(self.store.list_roles(),[])
        result=preview(self.role,'Used PYTHON to investigate a service.')
        self.assertEqual(result['result']['assessments'][0]['status'],'partial')
        self.assertFalse(result['saved'])
        old=copy.deepcopy(self.role);del old['criteria'][0]['phrases'];old['criteria'][0]['description']='Experience with "Python"'
        service.create_role(old)
        run=service.screen({'request_id':'old','role_version':'support:v1','profile_text':'Used Python for support.'})
        self.assertEqual(run['result']['assessments'][0]['status'],'partial')

    def create_user(self):
        return self.auth.manage('admin',{'action':'create','username':'reviewer','name':'Reviewer','role':'reviewer',
                                'password':self.user_password,'admin_password':self.password})

    def test_accounts_disable_revoke_recovery_once_and_last_admin_guard(self):
        user=self.create_user()
        other=PasswordAuth(self.store,[self.admin],False)
        (token,_),_=other.login('reviewer',self.user_password)
        cookie=other.cookie(token)
        self.assertIsNotNone(other.session(cookie))
        result=self.auth.manage('admin',{'action':'recovery','username':'reviewer','revision':user['revision'],'admin_password':self.password})
        recovered=self.auth.recover('reviewer',result['recovery_code'],'replacement-long-password-123')
        self.assertTrue(recovered['changed'])
        self.assertIsNone(other.session(cookie))
        with self.assertRaisesRegex(ValueError,'invalid or expired'):
            self.auth.recover('reviewer',result['recovery_code'],'another-long-password-123')
        rows={a['username']:a for a in self.auth.public_accounts()}
        self.auth.manage('admin',{'action':'update',**rows['reviewer'],'disabled':True,'admin_password':self.password})
        self.assertEqual(other.login('reviewer','replacement-long-password-123')[1],'invalid_credentials')
        with self.assertRaisesRegex(ConflictError,'at least one'):
            self.auth.manage('admin',{'action':'update',**rows['admin'],'disabled':True,'admin_password':self.password})
        with self.store.connect() as db:
            audit=' '.join(r[0] for r in db.execute('SELECT action FROM audit'))
            self.assertIn('password_recovered',audit)
            self.assertNotIn(result['recovery_code'],str(db.execute('SELECT * FROM audit').fetchall()))
        self.assertNotIn('password_hash',str(self.auth.public_accounts()))

    def test_expired_recovery_and_stale_account_updates(self):
        user=self.create_user()
        code=self.auth.manage('admin',{'action':'recovery','username':'reviewer','revision':0,'admin_password':self.password})['recovery_code']
        with patch('screening.accounts.time.time',return_value=time.time()+901):
            with self.assertRaises(ValueError):self.auth.recover('reviewer',code,'replacement-long-password-123')
        with self.assertRaises(ConflictError):
            self.auth.manage('admin',{'action':'update',**user,'revision':99,'disabled':False,'admin_password':self.password})

    def test_retry_before_run_saved_is_atomic_and_preserves_failure(self):
        service=ScreeningService(self.store,RulesProvider());service.create_role(self.role);q=Queue(service)
        q.submit({'request_id':'original','role_version':'support:v1','profile_text':'Used Python for support.'})
        with patch.object(service,'screen',side_effect=RuntimeError('private source must not appear')):
            q.process_one()
        self.assertEqual(q.list()[0]['status'],'failed')
        with ThreadPoolExecutor(max_workers=2) as pool:
            children=list(pool.map(lambda _:q.retry('original','Admin'),range(2)))
        self.assertEqual(len({j['id'] for j in children}),1)
        q.process_one()
        child=self.store.get_run(children[0]['id'])
        self.assertEqual(child['status'],'awaiting_review')
        original=next(j for j in q.list() if j['id']=='original')
        self.assertEqual(original['status'],'failed')
        self.assertNotIn('private source',str(q.list()))
        self.assertEqual(child['source']['metadata']['retry_of'],'original')

    def test_encrypted_restore_preserves_accounts_reviews_and_requires_empty_target(self):
        from cryptography.fernet import Fernet,InvalidToken
        self.create_user()
        service=ScreeningService(self.store,RulesProvider());service.create_role(self.role)
        run=service.screen({'request_id':'saved','role_version':'support:v1','profile_text':'Used Python for support.'})
        q=Queue(service);q.submit({'request_id':'pending','role_version':'support:v1','profile_text':'Used Python for support.'})
        key=Path(self.temp.name)/'key';key.write_bytes(Fernet.generate_key())
        archive=Path(self.temp.name)/'backup.encrypted'
        write_backup(self.store,archive,key)
        self.assertNotIn(b'Used Python',archive.read_bytes())
        target=Store(Path(self.temp.name)/'restored.sqlite3')
        counts=restore(target,archive,key)
        self.assertEqual(target.get_run('saved'),run)
        self.assertEqual(counts['workspace_accounts'],1)
        self.assertEqual(Queue(ScreeningService(target,RulesProvider())).list()[0]['status'],'failed')
        with self.assertRaisesRegex(ValueError,'empty'):restore(target,archive,key)
        archive.write_bytes(archive.read_bytes()[:-5]+b'wrong')
        with self.assertRaises(InvalidToken):restore(Store(Path(self.temp.name)/'bad.sqlite3'),archive,key)

    def test_monitoring_counts_and_stale_heartbeat_have_no_profile_data(self):
        q=Queue(ScreeningService(self.store,RulesProvider()))
        q.service.create_role(self.role)
        q.submit({'request_id':'secret-id','role_version':'support:v1','profile_text':'Private applicant text.'})
        self.store.backend='postgresql'
        result=snapshot(self.store)
        self.assertIn('screening_worker_heartbeat_missing_or_stale',result['warnings'])
        self.assertNotIn('secret-id',json.dumps(result));self.assertNotIn('Private applicant',json.dumps(result))
        q.heartbeat()
        self.assertNotIn('screening_worker_heartbeat_missing_or_stale',snapshot(self.store)['warnings'])


if __name__=='__main__':unittest.main()
