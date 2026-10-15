import json
import os
import unittest
from unittest.mock import patch, MagicMock
from screening.greenhouse import import_resume, download, token


class GreenhouseTests(unittest.TestCase):
    def test_id_scoped_import_and_no_signed_url_storage(self):
        queue=MagicMock(); queue.submit.return_value={'id':'queued'}
        attachment={'id':2,'candidate_id':1,'type':'resume','filename':'resume.txt','url':'https://cdn.example/resume?secret=signed'}
        with patch('screening.greenhouse.token',return_value='private-token'),patch('screening.greenhouse.request',return_value=(200,json.dumps([attachment]).encode(),{})) as request,patch('screening.greenhouse.download',return_value=b'Python API experience'),patch('screening.greenhouse.extract_upload',return_value={'text':'Python API experience','warnings':[],'malware_scan':{'status':'clean'}}):
            result=import_resume(queue,{'candidate_id':1,'attachment_id':2,'role_version':'role-v1'},'admin')
        self.assertEqual(len(result['jobs']),1)
        self.assertIn('candidate_ids=1',request.call_args.args[0])
        self.assertNotIn('secret',str(queue.submit.call_args))
        self.assertNotIn('private-token',str(queue.submit.call_args))

    def test_wrong_candidate_never_downloaded(self):
        with patch('screening.greenhouse.token',return_value='token'),patch('screening.greenhouse.request',return_value=(200,b'[{"id":2,"candidate_id":9,"type":"resume"}]',{})),patch('screening.greenhouse.download') as fetch:
            with self.assertRaises(ValueError):import_resume(MagicMock(),{'candidate_id':1,'attachment_id':2,'role_version':'v1'},'admin')
            fetch.assert_not_called()

    def test_download_redirect_has_no_credentials(self):
        with patch('screening.greenhouse.request',side_effect=[(302,b'',{'location':'https://other.example/file'}),(200,b'resume',{})]) as request:
            self.assertEqual(download('https://cdn.example/file',['cdn.example','other.example']),b'resume')
            self.assertTrue(all(len(c.args)==2 for c in request.call_args_list))

    def test_disallowed_redirect_is_revalidated(self):
        with patch('screening.greenhouse.request',side_effect=[(302,b'',{'location':'https://127.0.0.1/private'}),ValueError('blocked')]):
            with self.assertRaises(ValueError):download('https://cdn.example/file',['cdn.example'])

    def test_auth_failure_does_not_leak_response(self):
        with patch.dict(os.environ,{'GREENHOUSE_CLIENT_ID':'client','GREENHOUSE_CLIENT_SECRET':'private'}),patch('screening.greenhouse.request',return_value=(403,b'private upstream detail',{})):
            with self.assertRaisesRegex(ValueError,'authentication failed'):token()
