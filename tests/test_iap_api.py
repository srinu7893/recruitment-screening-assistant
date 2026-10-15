import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import jwt
from cryptography.hazmat.primitives.asymmetric import ec
from screening.identity import IAPAuth, IAP_ISSUER
from screening.server import make_server
from screening.storage import Store
from screening.workflow import ScreeningService
from screening.providers import DemoProvider


class IAPAPITests(unittest.TestCase):
    def test_signed_proxy_identity_and_no_token_bypass(self):
        key=ec.generate_private_key(ec.SECP256R1())
        class Keys:
            def get_signing_key_from_jwt(self, assertion):
                return SimpleNamespace(key=key.public_key())
        audience='/projects/123/global/backendServices/456'
        auth=IAPAuth(audience,[{'name':'Observer','subject':'subject-1','role':'viewer'}],Keys())
        with TemporaryDirectory() as folder, patch('screening.server.configured_auth',return_value=auth):
            server=make_server(ScreeningService(Store(Path(folder)/'app.sqlite3'),DemoProvider()),port=0)
            thread=Thread(target=server.serve_forever,daemon=True);thread.start()
            def request(path,headers=None,body=None):
                req=Request(f'http://127.0.0.1:{server.server_port}'+path,headers=headers or {},
                            data=json.dumps(body).encode() if body is not None else None)
                try:
                    with urlopen(req,timeout=5) as response:return response.status,json.load(response)
                except HTTPError as response:return response.code,json.load(response)
            try:
                self.assertEqual(request('/auth/config')[1],{'mode':'iap'})
                self.assertEqual(request('/health',{'Authorization':'Bearer '+'x'*40,'X-Goog-Authenticated-User-Email':'admin@example.com'})[0],401)
                token=jwt.encode({'sub':'subject-1','iss':IAP_ISSUER,'aud':audience,'iat':int(time.time()),'exp':int(time.time())+300},key,algorithm='ES256')
                headers={'X-Goog-IAP-JWT-Assertion':token,'Content-Type':'application/json'}
                status,health=request('/health',headers)
                self.assertEqual(status,200)
                self.assertEqual(health['identity'],{'name':'Observer','role':'viewer'})
                self.assertEqual(request('/roles',headers,{})[0],403)
            finally:
                server.shutdown();server.server_close();thread.join()
