"""Create an encrypted recruitment snapshot and upload it to a private GCS bucket."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory
from uuid import uuid4


def command(args):
    return subprocess.run(args, check=True, text=True, capture_output=True).stdout.strip()


def validate(config):
    if not isinstance(config, dict) or set(config) != {'project', 'schema', 'bucket', 'database_secret', 'key_secret'}:
        raise ValueError('Provide project, schema, bucket, database_secret and key_secret')
    patterns = {'project': r'[a-z][a-z0-9-]{4,61}[a-z0-9]',
                'schema': r'recruitment_[a-z0-9_]{1,49}',
                'bucket': r'[a-z0-9][a-z0-9-]{1,61}[a-z0-9]'}
    for field, pattern in patterns.items():
        if not isinstance(config[field], str) or not re.fullmatch(pattern, config[field]):
            raise ValueError('Invalid backup ' + field)
    for field in ('database_secret', 'key_secret'):
        ref = config[field]
        if (not isinstance(ref, dict) or set(ref) != {'name', 'version'}
                or not isinstance(ref['name'], str) or not re.fullmatch(r'recruitment-[A-Za-z0-9_-]+', ref['name'])
                or not isinstance(ref['version'], str) or not re.fullmatch(r'[1-9][0-9]*', ref['version'])):
            raise ValueError('Use a pinned recruitment secret version for ' + field)
    return config


def run_backup(config):
    from screening.backup import write_backup
    from screening.database import Database
    from types import SimpleNamespace
    from cryptography.fernet import Fernet
    from psycopg.conninfo import conninfo_to_dict
    config = validate(config)
    def secret(field):
        ref = config[field]
        return command(['gcloud', 'secrets', 'versions', 'access', ref['version'],
                        '--secret', ref['name'], '--project', config['project']])
    url = secret('database_secret')
    params = conninfo_to_dict(url)
    if params.get('sslmode') != 'verify-full' or '-pooler.' in params.get('host', ''):
        raise ValueError('Backup requires a direct PostgreSQL endpoint with verified TLS')
    key = secret('key_secret').encode('ascii')
    Fernet(key)  # Reject invalid key material before accessing application records.
    previous = os.environ.get('SCREENING_DB_SCHEMA')
    try:
        os.environ['SCREENING_DB_SCHEMA'] = config['schema']
        database = Database(url)
        # No application initialization/migrations or writes during a scheduled backup.
        database.parameters['options'] += ' -c default_transaction_read_only=on'
        store = SimpleNamespace(backend='postgresql', connect=database.connect)
        with TemporaryDirectory(prefix='recruitment-backup-') as temporary:
            folder = Path(temporary)
            key_file = folder / 'key'
            with key_file.open('xb') as output:
                key_file.chmod(0o600)
                output.write(key)
            name = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex + '.encrypted'
            archive = folder / name
            result = write_backup(store, archive, key_file)
            destination = 'gs://' + config['bucket'] + '/snapshots/' + name
            # objectCreator can write unique objects, but cannot read/delete prior backups.
            command(['gcloud', 'storage', 'cp', str(archive), destination,
                     '--project', config['project'], '--if-generation-match=0', '--quiet'])
            return {'object': destination, 'sha256': result['sha256'], 'schema': config['schema']}
    finally:
        if previous is None:
            os.environ.pop('SCREENING_DB_SCHEMA', None)
        else:
            os.environ['SCREENING_DB_SCHEMA'] = previous


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(run_backup(json.loads(args.config.read_text(encoding='utf-8')))))
    except Exception:
        raise SystemExit('Backup failed. Check pinned secrets, database TLS, schema and bucket permissions. No credential values were printed.') from None


if __name__ == '__main__':
    main()
