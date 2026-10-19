"""Cloud Shell preparation and guarded publication for the production service."""
import argparse
import json
import subprocess
from .cloud_release import validate, safe_detail

PROJECT = 'project-c9bd3d0e-266f-47bf-852'
NUMBER = '52916499838'
REGION = 'us-central1'
SERVICE = 'recruitment-screening'
REPO = 'srinu7893/recruitment-screening-assistant'
RUNTIME = f'recruitment-runtime@{PROJECT}.iam.gserviceaccount.com'
SECRET = 'recruitment-password-accounts'
SCHEMA = 'recruitment_production'


def run(args, data=None):
    return subprocess.run(args, input=data, text=True, capture_output=True, check=True).stdout


def describe():
    return json.loads(run(['gcloud','run','services','describe',SERVICE,'--project',PROJECT,'--region',REGION,'--format=json']))


def provision_schema():
    """Use existing owner secrets privately; isolate production records/workers."""
    import psycopg
    from psycopg import sql
    from psycopg.conninfo import conninfo_to_dict
    def secret(name):
        return run(['gcloud','secrets','versions','access','1','--secret',name,'--project',PROJECT]).strip()
    # The application URL already contains a verified direct endpoint; never log it.
    parameters = conninfo_to_dict(secret('recruitment-demo-database-url'))
    parameters.setdefault('sslrootcert', '/etc/ssl/certs/ca-certificates.crt')
    application_user = parameters['user']
    parameters.update(user=secret('neon-username'), password=secret('neon-password'), connect_timeout=15)
    with psycopg.connect(**parameters) as connection:
        connection.execute(sql.SQL('CREATE SCHEMA IF NOT EXISTS {} AUTHORIZATION {}').format(
            sql.Identifier(SCHEMA), sql.Identifier(application_user)))
        owner = connection.execute('SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname = %s', (SCHEMA,)).fetchone()
        if not owner or owner[0] != application_user:
            raise SystemExit('Production schema has an unexpected owner; no ownership was changed')
    print('Production schema verified. Existing demonstration records stay in their original schema.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare','publish'])
    args = parser.parse_args()
    common = ['--project',PROJECT,'--region',REGION]
    if args.action == 'prepare':
        run(['gh','auth','status'])
        provision_schema()
        # All changes are isolated to the recruitment application resources.
        from .create_admin import main as create_admin
        import sys
        original = sys.argv
        try:
            sys.argv = ['create_admin', '--project',PROJECT,'--secret',SECRET]
            create_admin()
        finally:
            sys.argv = original
        run(['gcloud','secrets','add-iam-policy-binding',SECRET,'--project',PROJECT,
             '--member=serviceAccount:'+RUNTIME,'--role=roles/secretmanager.secretAccessor','--quiet'])
        services = json.loads(run(['gcloud','run','services','list',*common,'--format=json']))
        if not any(s['metadata']['name'] == SERVICE for s in services):
            print('Creating a private bootstrap service to reserve the production URL...', flush=True)
            run(['gcloud','run','deploy',SERVICE,*common,'--image=us-docker.pkg.dev/cloudrun/container/hello',
                 '--service-account='+RUNTIME,'--no-allow-unauthenticated','--no-iap','--quiet'])
        url = describe()['status']['url']
        versions = json.loads(run(['gcloud','secrets','versions','list',SECRET,'--project',PROJECT,'--format=json']))
        enabled = [v['name'].split('/')[-1] for v in versions if v['state'].upper() == 'ENABLED']
        version = str(max(map(int, enabled)))
        config = {'project':PROJECT,'project_number':NUMBER,'region':REGION,'service':SERVICE,
                  'repository':'recruitment','runtime_account':RUNTIME,'public_url':url,
                  'database_schema':SCHEMA,'auth_mode':'password','provider':'rules','tier':'production',
                  'secrets':{'DATABASE_URL':{'name':'recruitment-demo-database-url','version':'1'},
                             'SCREENING_PASSWORD_ACCOUNTS':{'name':SECRET,'version':version}}}
        validate(config, require_scanner=False)
        run(['gh','variable','set','CLOUD_RUN_CONFIG_JSON','--repo',REPO,'--env','recruitment-cloud'],json.dumps(config))
        print('Production configuration saved. Service remains protected by Cloud Run IAM until publication.')
        print('Run the Deploy recruitment cloud workflow on main after Tests passes:')
        print(f'gh workflow run deploy-cloud.yml --repo {REPO} --ref main')
        print('After the deployment succeeds, run: python3 -m scripts.production_setup publish')
    else:
        service = describe()
        status = service['status']
        revision = status.get('latestReadyRevisionName')
        if not revision or revision != status.get('latestCreatedRevisionName'):
            raise SystemExit('Newest production revision is not ready; finish deployment first')
        ready = json.loads(run(['gcloud','run','revisions','describe',revision,*common,'--format=json']))
        containers = ready['spec']['containers']
        web = next((c for c in containers if c.get('name') == 'web'), None)
        env = {v['name']:v.get('value') for v in (web or {}).get('env',[])}
        annotations = service['metadata'].get('annotations',{})
        if (not web or env.get('SCREENING_AUTH_MODE') != 'password' or env.get('SCREENING_PROVIDER') != 'rules'
                or env.get('SCREENING_PUBLIC_URL') != status['url'] or annotations.get('run.googleapis.com/iap-enabled') == 'true'
                or not all(t.get('revisionName') == revision for t in status.get('traffic',[]) if t.get('percent',0))):
            raise SystemExit('Refusing publication: ready production revision, password login, rules mode and matching URL are required')
        print('Verified deployed configuration. Enabling access to the application login page...',flush=True)
        run(['gcloud','run','services','add-iam-policy-binding',SERVICE,*common,'--member=allUsers','--role=roles/run.invoker','--quiet'])
        from .cloud_smoke import smoke
        import getpass
        try:
            smoke(status['url'],input('Admin username: ').strip(),getpass.getpass('Admin password (not displayed): '))
        except Exception:
            print('Post-deployment test failed. Inspect deployment and rerun python3 -m scripts.cloud_smoke --url '+status['url'])
            raise SystemExit(1) from None
        print('Production application: '+status['url'])


if __name__ == '__main__':
    try:
        main()
    except subprocess.CalledProcessError as error:
        raise SystemExit('Cloud/GitHub command failed: '+safe_detail(error.stderr or 'Check CLI authentication and permissions')) from None
    except Exception:
        raise SystemExit('Setup failed. Check database connectivity and Cloud Shell dependencies; credential values were not printed.') from None
