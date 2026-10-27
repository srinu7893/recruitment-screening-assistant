"""Authenticated production smoke test using synthetic data only."""
import argparse
import base64
import getpass
import http.cookiejar
import json
import time
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener
from uuid import uuid4


class Session:
    def __init__(self, url):
        self.url = url.rstrip('/')
        self.jar = http.cookiejar.CookieJar()
        self.opener = build_opener(HTTPCookieProcessor(self.jar))
        self.csrf = ''

    def call(self, path, body=None, expected=200, use_csrf=True):
        headers = {'Content-Type': 'application/json'}
        if use_csrf:
            headers['X-CSRF-Token'] = self.csrf
        request = Request(self.url + path, headers=headers,
                          data=json.dumps(body).encode() if body is not None else None)
        try:
            response = self.opener.open(request, timeout=180)
        except HTTPError as error:
            response = error
        with response:
            if response.status != expected:
                raise RuntimeError(f'Smoke test failed: {path} returned HTTP {response.status}, expected {expected}')
            return json.load(response)

    def login(self, username, password):
        result = self.call('/auth/login', {'username': username, 'password': password})
        self.csrf = result['csrf']
        return result


def verify_team(admin, password):
    """Exercise access/recovery with a disposable viewer; always disable it afterward."""
    import secrets
    username = 'smoke-' + uuid4().hex[:16]
    initial, replacement = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    created = False
    viewer = Session(admin.url)
    try:
        admin.call('/accounts', {'action': 'create', 'username': username, 'name': username,
                                'role': 'viewer', 'password': initial, 'admin_password': password})
        created = True
        viewer.login(username, initial)
        viewer.call('/accounts', expected=403)
        viewer.call('/operations/status', expected=403)
        viewer.call('/roles', {}, expected=403)
        account = next(a for a in admin.call('/accounts')['accounts'] if a['username'] == username)
        recovery = admin.call('/accounts', {'action': 'recovery', 'username': username,
                                           'revision': account['revision'], 'admin_password': password})
        admin.call('/auth/recover', {'username': username, 'code': recovery['recovery_code'], 'password': replacement})
        viewer.call('/health', expected=401)
        viewer.call('/auth/login', {'username': username, 'password': initial}, expected=401)
        viewer.login(username, replacement)
        admin.call('/auth/recover', {'username': username, 'code': recovery['recovery_code'], 'password': initial}, expected=400)
    finally:
        if created:
            account = next(a for a in admin.call('/accounts')['accounts'] if a['username'] == username)
            admin.call('/accounts', {**account, 'action': 'update', 'disabled': True, 'admin_password': password})
            viewer.call('/health', expected=401)
            viewer.call('/auth/login', {'username': username, 'password': replacement}, expected=401)


def smoke(url, username, password):
    client = Session(url)
    call = client.call
    call('/health', expected=401)
    if call('/auth/config').get('mode') != 'password':
        raise RuntimeError('Password login is not enabled')
    client.login(username, password)
    run_id = None
    try:
        cookies = list(client.jar)
        if not cookies or not all(c.secure and c.has_nonstandard_attr('HttpOnly') for c in cookies):
            raise RuntimeError('Secure session cookie check failed')
        health = call('/health')
        if health.get('provider') != 'rules' or health.get('database') != 'postgresql' or health.get('demo'):
            raise RuntimeError('Expected rules screening and PostgreSQL')
        if health['identity']['role'] != 'admin':
            raise RuntimeError('Use the configured admin account for the smoke test')
        if call('/integrations').get('scan_mode') != 'clamd':
            raise RuntimeError('Production malware scanning is not enabled')
        call('/auth/session')
        verify_team(client, password)
        operations = call('/operations/check', {})
        if operations.get('scanner') != 'available_with_fresh_signatures':
            raise RuntimeError('Operations check did not confirm fresh scanner signatures')
        if 'screening_worker_heartbeat_missing_or_stale' in operations.get('warnings', []):
            raise RuntimeError('Operations check found a missing or stale worker heartbeat')
        call('/roles', {}, expected=403, use_csrf=False)
        role_version = 'deployment-smoke:'+uuid4().hex[:12]
        role = {'role_version':role_version,'title':'Synthetic deployment verification',
                'criteria':[{'id':'python','description':'Python service development','phrases':['Python'],
                             'required':True,'question':'Describe your Python work.'}]}
        preview = call('/roles/preview', {'role': role, 'profile_text': 'Built Python services.'})
        if preview.get('saved') is not False or preview['result']['assessments'][0]['status'] != 'partial':
            raise RuntimeError('Matching phrase preview failed')
        call('/roles', role, expected=201)
        run_id = 'deployment-smoke-'+uuid4().hex
        call('/uploads', {'request_id':run_id,'role_version':role_version,'filename':'synthetic-smoke.txt',
                          'content_base64':base64.b64encode(b'Built Python services for a fictional test project.').decode()}, expected=202)
        deadline = time.monotonic()+120
        run = None
        while time.monotonic() < deadline:
            jobs = call('/jobs')
            job = next((j for j in jobs if j['id'] == run_id), None)
            if job and job['status'] == 'failed':
                raise RuntimeError('Synthetic upload failed during background screening')
            if not job or job['status'] != 'completed':
                time.sleep(2)
                continue
            run = call('/runs?id='+run_id)
            if run['status'] in ('awaiting_review','failed'):
                break
            time.sleep(2)
        if not run or run['status'] != 'awaiting_review' or run['result']['assessments'][0]['status'] != 'partial':
            raise RuntimeError('Synthetic upload did not produce the expected evidence review')
        scan = run.get('source', {}).get('metadata', {}).get('malware_scan', {})
        if scan.get('status') != 'clean' or scan.get('engine') != 'clamd':
            raise RuntimeError('Synthetic upload has no clean ClamAV verdict')
        run = call('/notes', {'run_id':run_id,'revision':run.get('revision',0),'text':'Synthetic post-deployment verification.'})
        exported = call('/export?id='+run_id)
        if not exported.get('notes'):
            raise RuntimeError('Review note persistence failed')
        call('/delete', {'run_id':run_id})
        run_id = None
        call('/auth/logout', {})
        call('/health', expected=401)
        print('PASS: protected records, secure cookie, admin login, CSRF, team account creation, viewer isolation, one-use recovery, session revocation, operations, phrase preview, Neon, resume upload, scanner, background rules screening, notes, export, deletion and logout.')
        print('Only synthetic test data was used. The synthetic approved role and disabled test account remain in audit history.')
    finally:
        if run_id:
            print('A synthetic smoke record may remain; inspect the deployment-smoke records after resolving the failure.')
        # Revoke the session even when a check failed; never print credentials.
        try:
            call('/auth/logout', {}, expected=200)
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    args = parser.parse_args()
    from screening.deployment import public_origin
    if not public_origin(args.url):
        raise SystemExit('Use the HTTPS production service origin')
    username = input('Admin username: ').strip()
    password = getpass.getpass('Admin password (not displayed): ')
    try:
        smoke(args.url, username, password)
    except Exception as error:
        # Do not include raw remote error bodies or URLs with credentials.
        raise SystemExit(str(error) if isinstance(error, RuntimeError) else 'Smoke test failed; check service readiness and network access') from None


if __name__ == '__main__':
    main()
