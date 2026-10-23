"""Upload fictional manager-demo resumes through the real authenticated API."""
import argparse
import base64
import getpass
import http.cookiejar
import json
from pathlib import Path
import time
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import HTTPCookieProcessor, Request, build_opener

FIXTURE = Path(__file__).resolve().parents[1] / 'screening/fixtures/manager_demo.json'


def seed(url, username, password):
    data = json.loads(FIXTURE.read_text(encoding='utf-8'))
    opener = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
    csrf = ''
    def call(path, body=None, expected=(200,)):
        request = Request(url+path, data=json.dumps(body).encode() if body is not None else None,
                          headers={'Content-Type':'application/json','X-CSRF-Token':csrf})
        try:
            response = opener.open(request, timeout=180)
        except HTTPError as error:
            response = error
        with response:
            if response.status not in expected:
                raise RuntimeError(f'{path.split("?")[0]} returned HTTP {response.status}; check login, permissions or service readiness')
            return response.status, json.load(response)
    _, session = call('/auth/login', {'username':username,'password':password})
    csrf = session['csrf']
    try:
        _, health = call('/health')
        if health.get('provider') != 'rules' or health['identity']['role'] != 'admin':
            raise RuntimeError('Use an admin account in the rules-screening workspace')
        role = data['role']
        status, existing = call('/roles?version='+quote(role['role_version']), expected=(200,404))
        if status == 404:
            call('/roles', role, expected=(201,))
        elif any(existing[k] != role[k] for k in ('role_version','title','criteria')):
            raise RuntimeError('Demo role already exists with different criteria; no records were replaced')
        keys = {}
        for profile in data['profiles']:
            key = 'manager-demo-v1-'+profile['id'].lower()
            status,saved=call('/runs?id='+quote(key),expected=(200,404))
            if status==200:
                if saved['role_version']!=role['role_version'] or saved['source']['text']!=profile['text']:
                    raise RuntimeError('An existing demo ID contains different data; no record was replaced')
                if saved['status'] not in ('awaiting_review','completed'):
                    raise RuntimeError('An existing demo run needs attention. Retry it from processing jobs before loading again.')
                if sum(a['status']=='partial' for a in saved['result']['assessments'])!=profile['expected_mentions']:
                    raise RuntimeError('Existing demo evidence differs from the fixture; inspect it before loading again')
                print(profile['id']+': existing saved review retained')
                continue
            keys[key] = profile
            call('/uploads', {'request_id':key,'role_version':role['role_version'],
                 'filename':profile['id']+'-FICTIONAL-'+profile['name'].replace(' ','-')+'.txt',
                 'content_base64':base64.b64encode(profile['text'].encode()).decode()}, expected=(202,))
        deadline = time.monotonic()+180
        pending = set(keys)
        while pending and time.monotonic() < deadline:
            _, jobs = call('/jobs')
            for job in jobs:
                if job['id'] not in pending:
                    continue
                if job['status'] in ('failed','cancelled'):
                    raise RuntimeError('A fictional screening job failed: '+job['id'])
                if job['status'] != 'completed':
                    continue
                profile = keys[job['id']]
                _, run = call('/runs?id='+quote(job['id']))
                rows = run['result']['assessments']
                if sum(a['status']=='partial' for a in rows) != profile['expected_mentions']:
                    raise RuntimeError('Unexpected demo evidence result for '+profile['id'])
                marker = 'FICTIONAL MANAGER DEMO: '+profile['scenario']+'. Not a real candidate. Human review is required.'
                if not any(n['text'] == marker for n in run.get('notes',[])):
                    call('/notes', {'run_id':job['id'],'revision':run.get('revision',0),'text':marker})
                pending.remove(job['id'])
                print(profile['id']+': ready - '+profile['scenario'])
            if pending:
                time.sleep(2)
        if pending:
            raise RuntimeError('Some jobs are still processing. Rerun this command to check and finish; IDs are stable.')
        print('PASS: five fictional resumes uploaded, screened and verified. Filter by role: '+role['role_version'])
        print('No real records were changed. No decisions were recorded. Repeating the command reuses the same jobs.')
    finally:
        try:
            call('/auth/logout', {})
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='https://recruitment-screening-fddyka6g2a-uc.a.run.app')
    args = parser.parse_args()
    from screening.deployment import public_origin
    origin = public_origin(args.url)
    if not origin:
        raise SystemExit('Use the application HTTPS origin')
    username = input('Admin username: ').strip()
    password = getpass.getpass('Admin password (not displayed): ')
    try:
        seed(origin, username, password)
    except Exception as error:
        raise SystemExit(str(error) if isinstance(error, RuntimeError) else 'Demo loading failed; check service availability. Credentials were not printed.') from None


if __name__ == '__main__':
    main()
