"""Read-only Greenhouse Harvest v3 custom-integration resume import."""
import base64
import http.client
import json
import os
from urllib.parse import urlencode, urljoin
from .integrations import validate_url, PinnedHTTPS, MAX_DOWNLOAD, import_records
from .documents import extract_upload


def request(url, hosts, headers=None, body=None):
    parts, address = validate_url(url, hosts)
    conn = PinnedHTTPS(parts.hostname, address)
    try:
        conn.request('POST' if body is not None else 'GET',
                     parts.path + ('?' + parts.query if parts.query else ''), body=body, headers=headers or {})
        response = conn.getresponse()
        raw = response.read(MAX_DOWNLOAD + 1)
        if len(raw) > MAX_DOWNLOAD:
            raise ValueError('Greenhouse response exceeds 5 MB')
        return response.status, raw, dict((k.lower(), v) for k, v in response.getheaders())
    except (OSError, http.client.HTTPException):
        raise ValueError('Greenhouse connection unavailable') from None
    finally:
        conn.close()


def token():
    client = os.environ.get('GREENHOUSE_CLIENT_ID', '')
    secret = os.environ.get('GREENHOUSE_CLIENT_SECRET', '')
    if not client or not secret or ':' in client:
        raise ValueError('Configure Greenhouse OAuth credentials in server secrets')
    credentials = base64.b64encode((client + ':' + secret).encode()).decode()
    status, raw, _ = request('https://auth.greenhouse.io/token', ['auth.greenhouse.io'],
        {'Authorization': 'Basic ' + credentials, 'Content-Type': 'application/x-www-form-urlencoded'},
        'grant_type=client_credentials')
    if status != 200:
        raise ValueError('Greenhouse authentication failed; check credentials and permissions')
    try:
        document = json.loads(raw)
        value = document['access_token']
        if document.get('token_type', '').lower() != 'bearer' or not isinstance(value, str) or not value or '\r' in value or '\n' in value:
            raise ValueError()
        return value
    except (ValueError, KeyError, TypeError, AttributeError):
        raise ValueError('Invalid Greenhouse authentication response') from None


def download(url, hosts):
    # Never forward OAuth headers to attachment/CDN URLs. Validate every redirect.
    for _ in range(4):
        status, raw, headers = request(url, hosts)
        if status == 200:
            return raw
        if status not in (301, 302, 303, 307, 308) or not headers.get('location'):
            raise ValueError('Greenhouse resume download failed')
        url = urljoin(url, headers['location'])
    raise ValueError('Greenhouse resume has too many redirects')


def import_resume(queue, body, actor):
    attachment = body.get('attachment_id')
    candidate = body.get('candidate_id')
    if any(type(v) is not int or not 1 <= v <= 2**63-1 for v in (attachment, candidate)):
        raise ValueError('Provide positive numeric Greenhouse candidate and attachment IDs')
    role = body.get('role_version')
    queue.service.store.get_role(role)
    url = 'https://harvest.greenhouse.io/v3/attachments?' + urlencode({'ids': attachment, 'candidate_ids': candidate, 'type': 'resume'})
    for attempt in range(2):
        status, raw, headers = request(url, ['harvest.greenhouse.io'], {'Authorization': 'Bearer ' + token()})
        if status != 401:
            break
    if status != 200:
        raise ValueError('Greenhouse API request failed; check permissions or retry later')
    try:
        rows = json.loads(raw)
        if not isinstance(rows, list) or len(rows) != 1:
            raise ValueError()
        row = rows[0]
        if row['id'] != attachment or row['candidate_id'] != candidate or row['type'] != 'resume':
            raise ValueError()
        filename, link = row['filename'], row['url']
    except (ValueError, KeyError, TypeError):
        raise ValueError('No unique resume matched those Greenhouse IDs') from None
    hosts = [v.strip().lower() for v in os.environ.get('GREENHOUSE_ATTACHMENT_HOSTS', '').split(',') if v.strip()]
    raw = download(link, hosts)
    extracted = extract_upload(filename, base64.b64encode(raw).decode())
    result = import_records(queue, [{'external_id': f'{candidate}:{attachment}', 'profile_text': extracted['text']}],
                            role, actor, 'greenhouse-v3', source_metadata={'warnings': extracted.get('warnings', []),
                                'malware_scan': extracted.get('malware_scan')})
    result['warnings'] = extracted.get('warnings', [])
    result['malware_scan'] = extracted.get('malware_scan')
    return result
