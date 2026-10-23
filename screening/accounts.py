"""Database account overrides and one-use, admin-assisted password recovery."""
import hashlib
import hmac
import json
import re
import secrets
import time
from .storage import ConflictError, now


def account_version(account):
    return hashlib.sha256(json.dumps(account, sort_keys=True).encode()).hexdigest()


class AccountManagement:
    def throttle(self, scope, limit=10):
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            current=time.time()
            db.execute('DELETE FROM login_attempts WHERE expires <= ?', (current,))
            row=db.execute('SELECT attempts FROM login_attempts WHERE id = ?', (scope,)).fetchone()
            if row and row[0]>=limit:
                raise ValueError('Too many attempts. Wait one minute and try again')
            if row:
                db.execute('UPDATE login_attempts SET attempts = attempts + 1 WHERE id = ?', (scope,))
            else:
                db.execute('INSERT INTO login_attempts VALUES (?, ?, ?)',(scope,1,current+60))

    def all_accounts(self, db=None):
        if db is None:
            with self.store.connect() as connection:
                return self.all_accounts(connection)
        rows = {a['username']: {**a, 'disabled':False, 'revision':0} for a in self.bootstrap}
        rows.update({key: json.loads(document) for key, document in db.execute('SELECT username, document FROM workspace_accounts')})
        return rows

    @property
    def accounts(self):
        return [a for a in self.all_accounts().values() if not a['disabled']]

    def public_accounts(self):
        return [{k:a[k] for k in ('username','name','role','disabled','revision')} for a in self.all_accounts().values()]

    def save_account(self, db, account, actor, action):
        rows = self.all_accounts(db)
        if any(a['username'] != account['username'] and a['name'] == account['name'] for a in rows.values()):
            raise ConflictError('Choose a unique display name')
        rows[account['username']] = account
        if not any(a['role']=='admin' and not a['disabled'] for a in rows.values()):
            raise ConflictError('Keep at least one enabled administrator')
        db.execute('INSERT OR IGNORE INTO workspace_accounts(username, document) VALUES (?, ?)', (account['username'],json.dumps(account)))
        db.execute('UPDATE workspace_accounts SET document = ? WHERE username = ?', (json.dumps(account),account['username']))
        db.execute('DELETE FROM account_recovery WHERE username = ?', (account['username'],))
        db.execute('INSERT INTO audit(at, actor, action, target) VALUES (?, ?, ?, ?)',(now(),actor,action,account['username']))

    def reauthenticate(self, username, password):
        self.throttle('reauth:'+username,10)
        from .password_auth import verify
        account = self.all_accounts().get(username)
        if not account or account['disabled'] or not verify(password, account['password_hash']):
            raise ValueError('Current password is incorrect')
        return account

    def manage(self, actor_username, body):
        actor = self.reauthenticate(actor_username, body.get('admin_password'))
        if actor['role'] != 'admin':
            raise ValueError('Administrator required')
        from .password_auth import hash_password
        username, action = body.get('username'), body.get('action')
        if not isinstance(username,str) or not re.fullmatch(r'[a-z0-9][a-z0-9_.@-]{0,79}',username):
            raise ValueError('Use a lowercase username with letters, numbers, dot, underscore, @ or hyphen')
        if action not in ('create','update','recovery'):
            raise ValueError('Choose create, update or recovery')
        password_hash = hash_password(body.get('password')) if action == 'create' else None
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            rows = self.all_accounts(db)
            current_actor = rows.get(actor_username)
            if not current_actor or account_version(current_actor) != account_version(actor):
                raise ConflictError('Account changed; sign in again')
            account = rows.get(username)
            if action == 'create':
                if account:
                    raise ConflictError('Username already exists')
                account = {'username':username,'name':body.get('name'),'role':body.get('role'),
                           'disabled':False,'password_hash':password_hash,'revision':0}
            else:
                if not account:
                    raise ValueError('Account not found')
                if type(body.get('revision')) is not int or body['revision'] != account['revision']:
                    raise ConflictError('Account changed; refresh before saving')
                if action == 'recovery':
                    return self.issue_recovery(db, account, actor['name'])
                if type(body.get('disabled')) is not bool:
                    raise ValueError('Set disabled to true or false')
                account = {**account,'name':body.get('name'),'role':body.get('role'),
                           'disabled':body['disabled'],'revision':account['revision']+1}
            if not isinstance(account['name'],str) or not account['name'].strip() or len(account['name'])>120 or account['name'] != account['name'].strip():
                raise ValueError('Use a display name from 1 to 120 characters without surrounding spaces')
            if account['role'] not in ('admin','reviewer','viewer'):
                raise ValueError('Choose admin, reviewer or viewer')
            self.save_account(db,account,actor['name'],'account_'+action)
        return {k:account[k] for k in ('username','name','role','disabled','revision')}

    def issue_recovery(self, db, account, actor):
        if account['disabled']:
            raise ValueError('Enable the account before issuing a recovery code')
        token = secrets.token_urlsafe(32)
        db.execute('DELETE FROM account_recovery WHERE username = ? OR expires <= ?', (account['username'],time.time()))
        db.execute('INSERT INTO account_recovery VALUES (?, ?, ?, ?)',
                   (hashlib.sha256(token.encode()).hexdigest(),account['username'],time.time()+900,account_version(account)))
        db.execute('INSERT INTO audit(at,actor,action,target) VALUES (?, ?, ?, ?)',(now(),actor,'recovery_issued',account['username']))
        return {'username':account['username'],'recovery_code':token,'expires_in_seconds':900}

    def recover(self, username, token, password):
        from .password_auth import hash_password
        if not isinstance(username,str) or not isinstance(token,str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}',token):
            raise ValueError('Recovery code is invalid or expired')
        password_hash = hash_password(password)
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            digest=hashlib.sha256(token.encode()).hexdigest()
            recovery=db.execute('SELECT username, expires, version FROM account_recovery WHERE id = ?', (digest,)).fetchone()
            account=self.all_accounts(db).get(username)
            if (not recovery or recovery[0]!=username or recovery[1]<=time.time() or not account or account['disabled']
                    or not hmac.compare_digest(recovery[2],account_version(account))):
                raise ValueError('Recovery code is invalid or expired')
            account={**account,'password_hash':password_hash,'revision':account['revision']+1}
            self.save_account(db,account,account['name'],'password_recovered')
        return {'changed':True,'message':'Password updated. Sign in with your new password.'}

    def change_password(self, username, current, new):
        from .password_auth import hash_password
        account=self.reauthenticate(username,current)
        password_hash=hash_password(new)
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            latest=self.all_accounts(db).get(username)
            if account_version(account)!=account_version(latest):
                raise ConflictError('Account changed; sign in again')
            account={**account,'password_hash':password_hash,'revision':account['revision']+1}
            self.save_account(db,account,account['name'],'password_changed')
        return {'changed':True}
