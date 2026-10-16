import hashlib
import hmac
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from screening.providers import DemoProvider
from screening.server import make_server
from screening.storage import Store
from screening.workflow import ScreeningService


class AccessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = TemporaryDirectory()
        cls.service = ScreeningService(Store(Path(cls.temp.name)/"access.sqlite3"), DemoProvider())
        cls.tokens = {name:name[0]*40 for name in ("admin", "reviewer", "viewer")}
        accounts = [{"name":name,"role":name,"token":token} for name,token in cls.tokens.items()]
        cls.server = make_server(cls.service, port=0, accounts=accounts,
                                 config={"allowed_hosts":set(),"webhook_secret":"synthetic-secret"})
        cls.thread = Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"
        folder = Path(__file__).resolve().parents[1]/"examples"
        cls.role = json.loads((folder/"role.json").read_text())
        cls.service.create_role(cls.role)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join();cls.temp.cleanup()

    def call(self,path,body=None,identity="admin",headers=None):
        heads = {"Authorization":"Bearer "+self.tokens[identity], **(headers or {})}
        raw = json.dumps(body).encode() if body is not None else None
        if raw is not None: heads["Content-Type"]="application/json"
        try:
            with urlopen(Request(self.base+path,data=raw,headers=heads),timeout=5) as response:
                return response.status, response.read(), response.headers
        except HTTPError as response:
            return response.code, response.read(), response.headers

    def test_showcase_requires_admin_and_demo_workspace(self):
        self.assertEqual(self.call('/showcase/load', {}, 'reviewer')[0], 403)
        self.assertEqual(self.call('/showcase/load', {}, 'viewer')[0], 403)
        self.assertEqual(self.call('/showcase/load', {})[0], 200)
        original = self.service.provider.name
        try:
            self.service.provider.name = 'live-test'
            self.assertEqual(self.call('/showcase/load', {})[0], 400)
        finally:
            self.service.provider.name = original

    def test_readiness_and_reviewer_directory(self):
        status, raw, _ = self.call('/readyz', headers={'Authorization':''})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw), {'status':'ready'})
        status, raw, _ = self.call('/reviewers')
        self.assertEqual(status, 200)
        self.assertEqual({a['name'] for a in json.loads(raw)}, {'admin','reviewer'})
        self.assertNotIn(b'hash', raw)
        self.assertEqual(self.call('/assignments', {}, 'viewer')[0], 403)

    def test_scorecard_and_ats_permissions(self):
        self.assertEqual(self.call('/scorecards',{},'viewer')[0],403)
        self.assertEqual(self.call('/integrations/greenhouse',{},'reviewer')[0],403)
        self.assertEqual(self.call('/integrations/greenhouse',{},'viewer')[0],403)

    def test_automation_controls_require_admin_and_do_not_leak_local_paths(self):
        for path in ['/automation/settings', '/automation/run', '/automation/retry']:
            for role in ['reviewer', 'viewer']:
                self.assertEqual(self.call(path, {}, role)[0], 403)
        self.assertEqual(self.call('/automation')[0], 200)
        self.assertIsNone(json.loads(self.call('/automation', identity='reviewer')[1])['inbox_path'])

    def test_viewer_cannot_submit(self):
        self.assertEqual(self.call('/jobs',{},'viewer')[0],403)

    def test_reviewer_cannot_delete_or_approve_roles(self):
        self.assertEqual(self.call('/delete',{'run_id':'missing'},'reviewer')[0],403)
        self.assertEqual(self.call('/roles',self.role,'reviewer')[0],403)

    def test_actual_identity_overrides_claimed_approver(self):
        role = {**self.role, "role_version":"api-approval:v1", "approved_by":"forged-person"}
        status, raw, _ = self.call('/roles',role)
        self.assertEqual(status,201)
        self.assertEqual(json.loads(raw)['approved_by'],'admin')

    def test_public_dashboard_has_csp_and_no_data(self):
        status, raw, headers = self.call('/')
        self.assertEqual(status,200)
        self.assertIn("script-src 'self'",headers['Content-Security-Policy'])
        self.assertIn(b'Shortlist',raw)
        self.assertNotIn(self.tokens['admin'].encode(),raw)

    def test_same_origin_browser_request_allowed(self):
        self.assertEqual(self.call('/health',headers={'Origin':self.base})[0],200)

    def test_host_rebinding_denied(self):
        self.assertEqual(self.call('/health',headers={'Host':'attacker.example'})[0],403)

    def test_second_server_cannot_own_database(self):
        with self.assertRaisesRegex(ValueError,'Another server'):
            make_server(self.service,self.tokens['admin'],port=0)

    def test_real_webhook_route_and_replay(self):
        body={"role_version":self.role['role_version'],"candidates":[{"external_id":"webhook-test","profile_text":"Built Python APIs"}]}
        raw=json.dumps(body).encode();stamp=str(int(time.time()));event='route-test'
        sig=hmac.new(b'synthetic-secret',stamp.encode()+b'.'+event.encode()+b'.'+raw,hashlib.sha256).hexdigest()
        heads={'X-Event-ID':event,'X-Timestamp':stamp,'X-Signature':sig,'Authorization':''}
        status,data,_=self.call('/webhooks/profiles',body,headers=heads)
        self.assertEqual(status,202)
        self.assertEqual(len(json.loads(data)['jobs']),1)
        self.assertEqual(self.call('/webhooks/profiles',body,headers=heads)[0],400)


if __name__=='__main__':unittest.main()
