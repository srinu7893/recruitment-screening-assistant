import time
from types import SimpleNamespace
import unittest
import jwt
from cryptography.hazmat.primitives.asymmetric import ec
from screening.identity import IAPAuth, IAP_ISSUER


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.key = ec.generate_private_key(ec.SECP256R1())
        class Keys:
            def get_signing_key_from_jwt(inner, token):
                return SimpleNamespace(key=self.key.public_key())
        self.auth = IAPAuth('/projects/123/global/backendServices/456',
                            [{'subject':'accounts.google.com:123', 'name':'Recruiter', 'role':'reviewer'}], Keys())
        self.claims = {'sub':'accounts.google.com:123', 'iss':IAP_ISSUER, 'aud':self.auth.audience,
                       'iat':int(time.time()), 'exp':int(time.time())+300}

    def token(self, changes=None, key=None):
        return jwt.encode({**self.claims, **(changes or {})}, key or self.key, algorithm='ES256')

    def test_valid_signed_identity_is_mapped_by_subject(self):
        self.assertEqual(self.auth.identify_assertion(self.token()), {'name':'Recruiter','role':'reviewer'})

    def test_rejects_tampering_expiry_wrong_audience_and_unknown_subject(self):
        for changes in [{'aud':'other'}, {'iss':'https://attacker.example'}, {'exp':0}, {'sub':'unknown'}, {'iat':int(time.time())+300}]:
            self.assertIsNone(self.auth.identify_assertion(self.token(changes)))
        other = ec.generate_private_key(ec.SECP256R1())
        self.assertIsNone(self.auth.identify_assertion(self.token(key=other)))
        self.assertIsNone(self.auth.identify_assertion('forged-email@example.com'))
        self.assertIsNone(self.auth.identify_assertion(''))

    def test_missing_required_claim_is_rejected(self):
        del self.claims['exp']
        self.assertIsNone(self.auth.identify_assertion(self.token()))

    def test_duplicate_or_invalid_account_mapping_rejected(self):
        row = {'subject':'same','name':'Person','role':'admin'}
        with self.assertRaises(ValueError):
            IAPAuth(self.auth.audience, [row,row])
