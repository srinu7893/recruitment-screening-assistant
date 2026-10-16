"""Validated Cloud Run release manifest. Secret values never enter this script."""
import argparse
import hashlib
import json
import re
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit


def validate(c, require_scanner=True):
    for key in ('project','region','service','repository'):
        if not re.fullmatch(r'[a-z][a-z0-9-]{1,62}', c.get(key,'')) or 'replace' in c[key]:
            raise ValueError('Invalid or placeholder ' + key)
    if not re.fullmatch(r'[0-9]{6,20}', c.get('project_number','')):
        raise ValueError('Invalid project_number')
    if not re.fullmatch(r'[a-z][a-z0-9-]+@'+re.escape(c['project'])+r'\.iam\.gserviceaccount\.com',c.get('runtime_account','')):
        raise ValueError('Invalid runtime_account')
    from screening.deployment import public_origin
    if not public_origin(c.get('public_url')) or 'replace' in c['public_url']:
        raise ValueError('Set the canonical public HTTPS URL')
    expected_audience = f"/projects/{c['project_number']}/locations/{c['region']}/services/{c['service']}"
    if c.get('iap_audience') != expected_audience:
        raise ValueError('Set the exact direct Cloud Run IAP audience for this service and region')
    if c.get('provider') not in ('demo','openai'):
        raise ValueError('Provider must be demo or openai')
    schema = c.get('database_schema', 'public')
    if (not isinstance(schema, str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,62}', schema)
            or schema.startswith('pg_') or schema == 'information_schema'):
        raise ValueError('Invalid database_schema')
    if (require_scanner or c.get('scanner_image')) and not re.fullmatch(r'[a-z0-9][a-z0-9./:_-]+@sha256:[a-f0-9]{64}', c.get('scanner_image','')):
        raise ValueError('Provide an immutable scanner image digest')
    if not isinstance(c.get('greenhouse_attachment_hosts',''), str) or any(ch in c.get('greenhouse_attachment_hosts','') for ch in '\r\n'):
        raise ValueError('Greenhouse attachment hosts must be a comma-separated string')
    hosts = c.get('allowed_hosts', [])
    if (not isinstance(hosts, list) or len(hosts) > 50 or
            any(not isinstance(h, str) or not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?', h) for h in hosts)):
        raise ValueError('allowed_hosts must contain exact lowercase hostnames')
    url = c.get('connector_url', '')
    if url:
        if not isinstance(url, str) or len(url) > 4000:
            raise ValueError('Invalid connector URL')
        parsed = urlsplit(url)
        if (parsed.scheme != 'https' or parsed.hostname not in hosts or parsed.username or
                parsed.password or parsed.fragment or parsed.port not in (None, 443)):
            raise ValueError('Connector requires an allowlisted HTTPS host without credentials')
    for key, minimum, maximum in [('sync_seconds', 60, 86400), ('retention_days', 1, 3650)]:
        value = c.get(key, 0)
        if type(value) is not int or (value != 0 and not minimum <= value <= maximum):
            raise ValueError('Invalid ' + key)
    role = c.get('connector_role', '')
    if not isinstance(role, str) or len(role) > 120 or any(ch in role for ch in '\r\n'):
        raise ValueError('Invalid connector_role')
    if c.get('sync_seconds') and (not url or not role):
        raise ValueError('Scheduled feed sync requires connector_url and connector_role')
    required = {'DATABASE_URL','SCREENING_IAP_ACCOUNTS'}
    if c['provider']=='openai':
        required.add('OPENAI_API_KEY')
        if not isinstance(c.get('model'),str) or not c['model'].strip():
            raise ValueError('Live provider requires model')
    secrets = c.get('secrets',{})
    allowed = required | {'SCREENING_WEBHOOK_SECRET','SCREENING_CONNECTOR_TOKEN','GREENHOUSE_CLIENT_ID','GREENHOUSE_CLIENT_SECRET'}
    if not required.issubset(secrets) or set(secrets)-allowed:
        raise ValueError('Missing or unsupported secret references')
    for secret in secrets.values():
        if (not isinstance(secret,dict) or not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_-]{1,254}',secret.get('name',''))
                or not re.fullmatch(r'[1-9][0-9]*',secret.get('version',''))):
            raise ValueError('Secret references require a name and pinned numeric version')
    return c


def candidate_tag(revision):
    return 'verify-' + hashlib.sha256(revision.encode()).hexdigest()[:12]


def manifest(c, image, revision, current=None):
    validate(c)
    registry=f"{c['region']}-docker.pkg.dev/{c['project']}/{c['repository']}/recruitment"
    if not re.fullmatch(re.escape(registry)+r'@sha256:[a-f0-9]{64}', image):
        raise ValueError('Use an immutable recruitment image digest from the configured registry')
    if not re.fullmatch(re.escape(c['service'])+r'-[a-z0-9-]{1,40}',revision) or len(revision)>63:
        raise ValueError('Invalid revision name')
    env={'SCREENING_PUBLIC_URL':c['public_url'],'SCREENING_AUTH_MODE':'iap',
         'SCREENING_SCAN_MODE':'clamd','GREENHOUSE_ATTACHMENT_HOSTS':c.get('greenhouse_attachment_hosts',''),'SCREENING_IAP_AUDIENCE':c['iap_audience'],'SCREENING_PROVIDER':c['provider']}
    env.update(SCREENING_DB_SCHEMA=c.get('database_schema', 'public'),
               SCREENING_ALLOWED_HOSTS=','.join(c.get('allowed_hosts', [])),
               SCREENING_CONNECTOR_URL=c.get('connector_url', ''),
               SCREENING_CONNECTOR_ROLE=c.get('connector_role', ''),
               SCREENING_SYNC_SECONDS=str(c.get('sync_seconds', 0)),
               SCREENING_RETENTION_DAYS=str(c.get('retention_days', 0)))
    if c.get('model'):
        env['OPENAI_MODEL']=c['model']
    values=[{'name':k,'value':v} for k,v in env.items()]
    values += [{'name':k,'valueFrom':{'secretKeyRef':{'name':v['name'],'key':v['version']}}} for k,v in c['secrets'].items()]
    traffic=[]
    if current:
        for row in current.get('status',{}).get('traffic',[]):
            previous=row.get('revisionName') or current.get('status',{}).get('latestReadyRevisionName')
            if not previous or previous==revision:
                raise ValueError('Cannot preserve existing traffic allocation')
            item={'revisionName':previous,'percent':row.get('percent',0)}
            if row.get('tag'): item['tag']=row['tag']
            traffic.append(item)
        if not traffic or sum(x['percent'] for x in traffic)!=100:
            raise ValueError('Existing traffic must total 100 percent')
        traffic.append({'revisionName':revision, 'percent':0, 'tag':candidate_tag(revision)})
    else:
        traffic=[{'revisionName':revision,'percent':100}]
    probe={'httpGet':{'path':'/readyz','port':8080,'httpHeaders':[{'name':'Host','value':'127.0.0.1:8080'}]},
           'timeoutSeconds':20,'periodSeconds':30,'failureThreshold':5}
    return {'apiVersion':'serving.knative.dev/v1','kind':'Service',
        'metadata':{'name':c['service'],'namespace':c['project_number'],
                    'labels':{'cloud.googleapis.com/location':c['region']},
                    'annotations':{'run.googleapis.com/ingress':'all','run.googleapis.com/iap-enabled':'true',
                                   'run.googleapis.com/minScale':'1','run.googleapis.com/maxScale':'3'}},
        'spec':{'template':{'metadata':{'name':revision,'annotations':{'run.googleapis.com/cpu-throttling':'false',
                                      'autoscaling.knative.dev/minScale':'1',
                                      'run.googleapis.com/execution-environment':'gen2',
                                      'run.googleapis.com/container-dependencies':'{"web":["scanner"]}'}},
                            'spec':{'serviceAccountName':c['runtime_account'],'containerConcurrency':20,'timeoutSeconds':180,
                              'containers':[{'name':'web','image':image,'ports':[{'containerPort':8080}], 'env':values,
                                'resources':{'limits':{'cpu':'1','memory':'1Gi'}},'startupProbe':probe},
                                {'name':'scanner','image':c['scanner_image'],
                                 'resources':{'limits':{'cpu':'1','memory':'3Gi'}},
                                 'startupProbe':{'tcpSocket':{'port':3310},'periodSeconds':10,'failureThreshold':24}}]}},'traffic':traffic}}


def safe_detail(value):
    value = str(value)
    value = re.sub(r'(?:jdbc:)?postgres(?:ql)?://[^\s\"\'<>]+', '[REDACTED_DATABASE_URL]', value)
    value = re.sub(r'https?://[^\s\"\'<>]*[?][^\s\"\'<>]*', '[REDACTED_URL_QUERY]', value)
    value = re.sub(r'(?i)Bearer\s+[^\s\"\']+', 'Bearer [REDACTED]', value)
    value = re.sub(r'eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+', '[REDACTED_JWT]', value)
    value = re.sub(r'sk-[A-Za-z0-9_-]{10,}', '[REDACTED_API_KEY]', value)
    value = re.sub(r'(?i)((?:password|access_token|refresh_token|api_key)[\"\']?\s*[:=]\s*)[\"\']?[^\s,\"\']+', r'\1[REDACTED]', value)
    return value[-4000:]


class CloudCommandError(RuntimeError):
    pass


def command(args):
    try:
        return subprocess.run(args,check=True,text=True,capture_output=True).stdout
    except subprocess.CalledProcessError as error:
        operation = ' '.join(args[:4])
        raise CloudCommandError(operation + ': ' + safe_detail(error.stderr or 'Cloud command failed')) from None


def wait_for_revision(c, revision, directory, timeout=600):
    common=['--project',c['project'],'--region',c['region']]
    deadline = time.monotonic() + timeout
    print('Waiting for candidate containers and startup probes before promotion...', flush=True)
    while time.monotonic() < deadline:
        document = json.loads(command(['gcloud','run','revisions','describe',revision,*common,'--format=json']))
        conditions = document.get('status', {}).get('conditions', [])
        safe_conditions = [{key: safe_detail(row[key]) for key in ('type','status','reason','message') if key in row} for row in conditions]
        (directory / 'candidate-status.json').write_text(json.dumps({'revision':revision, 'conditions':safe_conditions},indent=2))
        ready = next((row for row in conditions if row.get('type') == 'Ready'), {})
        retired = any(row.get('reason') == 'Retired' for row in conditions)
        if ready.get('status') == 'True' and not retired:
            return document
        if ready.get('status') == 'False' and not retired:
            raise ValueError('Candidate startup failed: ' + safe_detail(ready.get('message') or ready.get('reason') or 'Inspect candidate-status.json'))
        time.sleep(3)
    raise ValueError('Timed out waiting for an active, ready candidate; inspect candidate-status.json')


def deploy(c,image,revision,directory):
    validate(c)
    common=['--project',c['project'],'--region',c['region']]
    # List first: auth/network failures must never be mistaken for a new service.
    services=json.loads(command(['gcloud','run','services','list',*common,'--format=json']))
    exists=any(x.get('metadata',{}).get('name')==c['service'] for x in services)
    current=json.loads(command(['gcloud','run','services','describe',c['service'],*common,'--format=json'])) if exists else None
    if current and current.get('status',{}).get('url') != c['public_url']:
        raise ValueError('public_url must match the existing canonical Cloud Run URL')
    document=manifest(c,image,revision,current)
    directory.mkdir(parents=True,exist_ok=True)
    path=directory/'service.json'; path.write_text(json.dumps(document,indent=2))
    if current:
        previous = [row for row in document['spec']['traffic'] if row['revisionName'] != revision]
        (directory/'previous-traffic.json').write_text(json.dumps(previous,indent=2))
    try:
        command(['gcloud','run','services','replace',str(path),*common,'--quiet'])
        # Replacing a service can return while its zero-traffic revision still
        # imports images. The temporary tag and revision minimum keep it active.
        wait_for_revision(c, revision, directory)
        if current:
            command(['gcloud','run','services','update-traffic',c['service'],*common,
                     '--to-revisions',revision+'=100','--remove-tags',candidate_tag(revision),'--quiet'])
    except Exception as error:
        detail = safe_detail(error) if isinstance(error, (CloudCommandError, ValueError)) else type(error).__name__
        (directory/'error.json').write_text(json.dumps({'revision':revision, 'error':detail},indent=2))
        if current:
            try:
                command(['gcloud','run','services','update-traffic',c['service'],*common,
                         '--remove-tags',candidate_tag(revision),'--quiet'])
            except CloudCommandError:
                print('Could not remove candidate tag; inspect its minimum-instance allocation.', flush=True)
        raise
    (directory/'result.json').write_text(json.dumps({'revision':revision,'url':c['public_url'],'ready':True,
        'note':'Complete authenticated IAP and resume upload smoke test after deployment.'},indent=2))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['validate','deploy'])
    parser.add_argument('--config',required=True);parser.add_argument('--image');parser.add_argument('--revision')
    args=parser.parse_args()
    try:
        c=validate(json.loads(Path(args.config).read_text()))
        if args.action=='deploy':
            deploy(c,args.image,args.revision,Path('artifacts/cloud-release'))
        print('Cloud configuration validated' if args.action=='validate' else 'Cloud revision ready and promoted')
    except (CloudCommandError, ValueError) as error:
        parser.exit(2, 'Cloud release failed: ' + safe_detail(error) + '\n')
    except Exception as error:
        parser.exit(2,'Cloud release failed ('+type(error).__name__+'). Inspect release artifacts and revision health.\n')


if __name__=='__main__':main()
