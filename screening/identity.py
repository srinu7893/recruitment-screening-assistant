"""Google IAP SSO: verify signed assertions, never trust unsigned identity headers."""
import json
import os

IAP_ISSUER = 'https://cloud.google.com/iap'
IAP_KEYS = 'https://www.gstatic.com/iap/verify/public_key-jwk'


class IAPAuth:
    mode = 'iap'

    def __init__(self, audience, accounts, key_client=None):
        import jwt
        if not isinstance(audience, str) or not audience.startswith('/projects/'):
            raise ValueError('Set SCREENING_IAP_AUDIENCE to the exact IAP resource audience')
        if not isinstance(accounts, list) or not accounts:
            raise ValueError('Configure SCREENING_IAP_ACCOUNTS with approved subject-to-role mappings')
        self.accounts = []
        for row in accounts:
            if (not isinstance(row, dict) or row.get('role') not in ('admin', 'reviewer', 'viewer')
                    or not isinstance(row.get('name'), str) or not row['name'].strip()
                    or not isinstance(row.get('subject'), str) or not row['subject'].strip()):
                raise ValueError('Every IAP account needs subject, name and role')
            self.accounts.append({k: row[k] for k in ('subject', 'name', 'role')})
        if len({a['subject'] for a in self.accounts}) != len(self.accounts) or len({a['name'] for a in self.accounts}) != len(self.accounts):
            raise ValueError('IAP subjects and names must be unique')
        self.audience = audience
        self.keys = key_client or jwt.PyJWKClient(IAP_KEYS, cache_jwk_set=True, lifespan=300, timeout=5)

    def identify_assertion(self, assertion):
        import jwt
        if not isinstance(assertion, str) or not assertion or len(assertion) > 16_384:
            return None
        try:
            signing_key = self.keys.get_signing_key_from_jwt(assertion).key
            claims = jwt.decode(assertion, signing_key, algorithms=['ES256'], audience=self.audience,
                                issuer=IAP_ISSUER, options={'require':['exp','iat','sub','aud','iss']}, leeway=30)
            account = next((a for a in self.accounts if a['subject'] == claims['sub']), None)
            return {k: account[k] for k in ('name','role')} if account else None
        except Exception:
            # Key lookup failures and invalid assertions fail closed; no token logging.
            return None


def configured_auth(token, accounts):
    from .auth import Auth
    mode = os.getenv('SCREENING_AUTH_MODE', 'token')
    if mode == 'token':
        auth = Auth(token, accounts)
        auth.mode = 'token'
        return auth
    if mode != 'iap':
        raise ValueError('SCREENING_AUTH_MODE must be token or iap')
    try:
        mapping = json.loads(os.getenv('SCREENING_IAP_ACCOUNTS', '[]'))
    except ValueError:
        raise ValueError('SCREENING_IAP_ACCOUNTS must be a JSON array') from None
    return IAPAuth(os.getenv('SCREENING_IAP_AUDIENCE'), mapping)
