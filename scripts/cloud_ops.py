"""Owner-run Cloud Shell backup, isolated restore drill and emergency recovery."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
from uuid import uuid4
from datetime import datetime, timezone
from tempfile import TemporaryDirectory


def command(args):
    return subprocess.run(args,check=True,text=True,capture_output=True).stdout.strip()


def configuration(project, region, service):
    document=json.loads(command(['gcloud','run','services','describe',service,'--project',project,'--region',region,'--format=json']))
    web=next(c for c in document['spec']['template']['spec']['containers'] if c.get('name')=='web')
    env={item['name']:item for item in web['env']}
    schema=env['SCREENING_DB_SCHEMA']['value']
    if not re.fullmatch(r'recruitment[a-z0-9_]*',schema):
        raise ValueError('Only a named recruitment schema is supported; public/payment schemas are excluded')
    def secret(name):
        ref=env[name]['valueFrom']['secretKeyRef']
        return command(['gcloud','secrets','versions','access',ref['key'],'--secret',ref['name'],'--project',project])
    return schema,secret('DATABASE_URL'),json.loads(secret('SCREENING_PASSWORD_ACCOUNTS'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['backup','restore-drill','recovery'])
    parser.add_argument('--project',default='project-c9bd3d0e-266f-47bf-852')
    parser.add_argument('--region',default='us-central1')
    parser.add_argument('--service',default='recruitment-screening')
    parser.add_argument('--username')
    parser.add_argument('--archive', help='Scheduled gs:// snapshot to verify in an isolated schema')
    parser.add_argument('--key-secret', default='recruitment-backup-key')
    parser.add_argument('--key-version', default='1')
    args=parser.parse_args()
    if args.archive and (args.action!='restore-drill' or not re.fullmatch(r'gs://[a-z0-9][a-z0-9-]{1,61}[a-z0-9]/snapshots/[A-Za-z0-9-]+\.encrypted',args.archive)):
        raise ValueError('Use a scheduled snapshots archive with restore-drill')
    if not re.fullmatch(r'recruitment-[A-Za-z0-9_-]+',args.key_secret) or not re.fullmatch(r'[1-9][0-9]*',args.key_version):
        raise ValueError('Use a pinned recruitment encryption-key secret')
    from screening.storage import Store
    schema,url,accounts=configuration(args.project,args.region,args.service)
    os.environ['SCREENING_DB_SCHEMA']=schema
    if args.action=='recovery':
        source=Store(url)
        if not args.username:
            raise ValueError('Provide --username for emergency recovery')
        from screening.password_auth import PasswordAuth
        auth=PasswordAuth(source,accounts,True)
        with source.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            account=auth.all_accounts(db).get(args.username)
            if not account:
                raise ValueError('Account not found')
            result=auth.issue_recovery(db,account,'cloud-operator')
        print('PRIVATE one-use recovery code (expires in 15 minutes). Do not paste into chat or logs:')
        print(result['recovery_code'])
        return
    if args.archive:
        with TemporaryDirectory(prefix='recruitment-restore-') as temporary:
            folder=Path(temporary)
            key=folder/'key'
            material=command(['gcloud','secrets','versions','access',args.key_version,
                              '--secret',args.key_secret,'--project',args.project])
            with key.open('xb') as output:
                key.chmod(0o600);output.write(material.encode('ascii'))
            file=folder/'archive.encrypted'
            command(['gcloud','storage','cp',args.archive,str(file),'--project',args.project,'--quiet'])
            restore_drill(url,schema,file,key,args.project)
        return
    source=Store(url)
    from cryptography.fernet import Fernet
    from screening.backup import write_backup
    folder=Path('data/cloud-backups');folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    key=Path('data/cloud-backup-key.txt')
    if not key.exists():
        with key.open('xb') as f:
            key.chmod(0o600);f.write(Fernet.generate_key())
    file=folder/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid4().hex[:8]+'.encrypted')
    report=write_backup(source,file,key)
    print('Encrypted recruitment-only backup created: '+report['file'])
    print('SHA256: '+report['sha256'])
    print('Store the encryption key separately and privately: '+str(key))
    if args.action=='backup':
        return
    restore_drill(url,schema,file,key,args.project)


def restore_drill(url,schema,file,key,project):
    from screening.storage import Store
    from screening.backup import restore,capture
    import psycopg
    from psycopg import sql
    from psycopg.conninfo import conninfo_to_dict
    parameters=conninfo_to_dict(url)
    app_user=parameters['user']
    parameters.setdefault('sslrootcert','/etc/ssl/certs/ca-certificates.crt')
    def owner_secret(name):
        return command(['gcloud','secrets','versions','access','1','--secret',name,'--project',project])
    parameters.update(user=owner_secret('neon-username'),password=owner_secret('neon-password'))
    isolated='recruitment_restorecheck_'+uuid4().hex[:16]
    with psycopg.connect(**parameters,autocommit=True) as owner:
        owner.execute(sql.SQL('CREATE SCHEMA {} AUTHORIZATION {}').format(sql.Identifier(isolated),sql.Identifier(app_user)))
        try:
            os.environ['SCREENING_DB_SCHEMA']=isolated
            target=Store(url)
            counts=restore(target,file,key)
            restored=capture(target)
            if any(len(restored['tables'][table]['rows'])!=count for table,count in counts.items()):
                raise ValueError('Restore row-count verification failed')
            print('PASS: encrypted backup restored into an isolated schema and all table counts verified.')
            print('Active jobs were converted to explicit-retry failures. Sessions and recovery codes were not restored.')
        finally:
            if not re.fullmatch(r'recruitment_restorecheck_[a-f0-9]{16}',isolated):
                raise ValueError('Unsafe drill cleanup target')
            owner.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(isolated)))
            os.environ['SCREENING_DB_SCHEMA']=schema


if __name__=='__main__':
    try:
        main()
    except Exception:
        raise SystemExit('Operation failed. Check Cloud Shell permissions, database availability and backup/key access. No credential values were printed.') from None
