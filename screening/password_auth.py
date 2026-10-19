"""Password accounts and opaque, database-backed browser sessions."""
import hashlib
import hmac
import json
import re
import secrets
import time
from http.cookies import SimpleCookie, CookieError


def hash_password(password):
    if not isinstance(password, str) or not 15 <= len(password) <= 256:
        raise ValueError('Use a password between 15 and 256 characters')
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 600000).hex()
    return f'pbkdf2_sha256$600000${salt}${digest}'


def verify(password, encoded):
    if not isinstance(password, str) or len(password) > 256:
        return False
    _, count, salt, expected = encoded.split('$')
    actual = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), int(count)).hex()
    return hmac.compare_digest(actual, expected)


class PasswordAuth:
    mode = 'password'

    def __init__(self, store, accounts, secure):
        if not isinstance(accounts, list) or not accounts:
            raise ValueError('Configure SCREENING_PASSWORD_ACCOUNTS')
        self.accounts = accounts
        self.store = store
        self.cookie_name = '__Host-screening_session' if secure else 'screening_session'
        self.secure = secure
        names, users = set(), set()
        for account in accounts:
            if (not isinstance(account, dict) or not re.fullmatch(r'[a-z0-9][a-z0-9_.@-]{0,79}', account.get('username', ''))
                    or account.get('role') not in ('admin', 'reviewer', 'viewer')
                    or not isinstance(account.get('name'), str) or not 1 <= len(account['name']) <= 120
                    or not re.fullmatch(r'pbkdf2_sha256\$600000\$[a-f0-9]{32}\$[a-f0-9]{64}', account.get('password_hash', ''))
                    or account['username'] in users or account['name'] in names):
                raise ValueError('Invalid or duplicate password account')
            users.add(account['username']); names.add(account['name'])
        self.version = hashlib.sha256(json.dumps(accounts, sort_keys=True).encode()).hexdigest()

    def cookie(self, token, clear=False):
        return f'{self.cookie_name}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={0 if clear else 28800}' + ('; Secure' if self.secure else '')

    def token(self, header):
        try:
            cookies = SimpleCookie(); cookies.load(header or '')
            value = cookies[self.cookie_name].value
            return value if re.fullmatch(r'[A-Za-z0-9_-]{43}', value) else ''
        except (CookieError, KeyError):
            return ''

    def session(self, header):
        key = hashlib.sha256(self.token(header).encode()).hexdigest()
        with self.store.connect() as db:
            row = db.execute('SELECT document FROM login_sessions WHERE id = ? AND expires > ?', (key, time.time())).fetchone()
        value = json.loads(row[0]) if row else None
        return value if value and value['version'] == self.version else None

    def login(self, username, password):
        username = username.strip().lower() if isinstance(username, str) else ''
        if len(username) > 80:
            return None, 'invalid_credentials'
        now = time.time()
        keys = [('global', 30), (hashlib.sha256(username.encode()).hexdigest(), 5)]
        limited = False
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM login_attempts WHERE expires <= ?', (now,))
            db.execute('DELETE FROM login_sessions WHERE expires <= ?', (now,))
            for key, limit in keys:
                row = db.execute('SELECT attempts FROM login_attempts WHERE id = ?', (key,)).fetchone()
                count = row[0] if row else 0
                limited |= count >= limit
                if row:
                    db.execute('UPDATE login_attempts SET attempts = attempts + 1 WHERE id = ?', (key,))
                else:
                    db.execute('INSERT INTO login_attempts(id, attempts, expires) VALUES (?, ?, ?)', (key, 1, now+60))
        if limited:
            return None, 'rate_limited'
        account = next((a for a in self.accounts if a['username'] == username), None)
        valid = verify(password, (account or self.accounts[0])['password_hash'])
        if not account or not valid:
            return None, 'invalid_credentials'
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        value = {'identity': {k: account[k] for k in ('name', 'role')}, 'csrf': csrf, 'version': self.version}
        with self.store.connect() as db:
            db.execute('INSERT INTO login_sessions(id, expires, document) VALUES (?, ?, ?)',
                       (hashlib.sha256(token.encode()).hexdigest(), now+28800, json.dumps(value)))
        self.store.audit(account['name'], 'signed_in', 'workspace')
        return (token, value), None

    def logout(self, header):
        with self.store.connect() as db:
            db.execute('DELETE FROM login_sessions WHERE id = ?', (hashlib.sha256(self.token(header).encode()).hexdigest(),))
