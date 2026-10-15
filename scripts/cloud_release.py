"""Validated Cloud Run release manifest. Secret values never enter this script."""
import argparse
import json
import re
import subprocess
from pathlib import Path


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
    if not c.get('iap_audience','').startswith('/projects/'+c['project_number']+'/'):
        raise ValueError('Set the exact IAP audience for this project')
    if c.get('provider') not in ('demo','openai'):
        raise ValueError('Provider must be demo or openai')
    if (require_scanner or c.get('scanner_image')) and not re.fullmatch(r'[a-z0-9][a-z0-9./:_-]+@sha256:[a-f0-9]{64}', c.get('scanner_image','')):
        raise ValueError('Provide an immutable scanner image digest')
    if not isinstance(c.get('greenhouse_attachment_hosts',''), str) or any(ch in c.get('greenhouse_attachment_hosts','') for ch in '\r\n'):
        raise ValueError('Greenhouse attachment hosts must be a comma-separated string')
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


def manifest(c, image, revision, current=None):
    validate(c)
    registry=f"{c['region']}-docker.pkg.dev/{c['project']}/{c['repository']}/recruitment"
    if not re.fullmatch(re.escape(registry)+r'@sha256:[a-f0-9]{64}', image):
        raise ValueError('Use an immutable recruitment image digest from the configured registry')
    if not re.fullmatch(re.escape(c['service'])+r'-[a-z0-9-]{1,40}',revision) or len(revision)>63:
        raise ValueError('Invalid revision name')
    env={'SCREENING_PUBLIC_URL':c['public_url'],'SCREENING_AUTH_MODE':'iap',
         'SCREENING_SCAN_MODE':'clamd','GREENHOUSE_ATTACHMENT_HOSTS':c.get('greenhouse_attachment_hosts',''),'SCREENING_IAP_AUDIENCE':c['iap_audience'],'SCREENING_PROVIDER':c['provider']}
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
                                      'run.googleapis.com/execution-environment':'gen2',
                                      'run.googleapis.com/container-dependencies':'{"web":["scanner"]}'}},
                            'spec':{'serviceAccountName':c['runtime_account'],'containerConcurrency':20,'timeoutSeconds':180,
                              'containers':[{'name':'web','image':image,'ports':[{'containerPort':8080}], 'env':values,
                                'resources':{'limits':{'cpu':'1','memory':'1Gi'}},'startupProbe':probe},
                                {'name':'scanner','image':c['scanner_image'],
                                 'resources':{'limits':{'cpu':'1','memory':'3Gi'}},
                                 'startupProbe':{'tcpSocket':{'port':3310},'periodSeconds':10,'failureThreshold':24}}]}},'traffic':traffic}}


def command(args):
    return subprocess.run(args,check=True,text=True,capture_output=True).stdout


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
    command(['gcloud','run','services','replace',str(path),*common,'--quiet'])
    # Replace waits for the startup probe. Existing production traffic was pinned.
    checked=json.loads(command(['gcloud','run','revisions','describe',revision,*common,'--format=json']))
    if not any(x.get('type')=='Ready' and x.get('status')=='True' for x in checked.get('status',{}).get('conditions',[])):
        raise ValueError('Candidate revision did not become ready; existing traffic preserved')
    if current:
        (directory/'previous-traffic.json').write_text(json.dumps(document['spec']['traffic'],indent=2))
        command(['gcloud','run','services','update-traffic',c['service'],*common,'--to-revisions',revision+'=100','--quiet'])
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
    except Exception:
        parser.exit(2,'Cloud release failed. Check configuration, permissions and Cloud Run revision health. No secret values are printed.\n')


if __name__=='__main__':main()
