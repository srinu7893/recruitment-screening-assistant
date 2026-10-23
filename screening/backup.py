"""Encrypted, schema-scoped logical snapshots; restore only into empty stores."""
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone
from .migrate import TABLES


def capture(store):
    tables={}
    with store.connect() as db:
        if store.backend=='postgresql':
            db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        else:
            db.execute('BEGIN')
        for table,columns in TABLES.items():
            order='id' if table in ('audit','webhook_events','automation_settings','intake_records','automation_events') else 'username' if table=='workspace_accounts' else 'rowid'
            rows=db.execute('SELECT '+','.join(columns)+' FROM '+table+' ORDER BY '+order).fetchall()
            tables[table]={'columns':list(columns),'rows':[list(row) for row in rows]}
    return {'format':'screening-backup-v1','created_at':datetime.now(timezone.utc).isoformat(),'tables':tables}


def write_backup(store, destination, key_file):
    from cryptography.fernet import Fernet
    cipher=Fernet(Path(key_file).read_bytes().strip())
    payload=json.dumps(capture(store),sort_keys=True,separators=(',',':')).encode()
    path=Path(destination)
    with path.open('xb') as output:
        path.chmod(0o600)
        output.write(cipher.encrypt(payload))
    return {'file':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}


def restore(store, source, key_file):
    from cryptography.fernet import Fernet
    document=json.loads(Fernet(Path(key_file).read_bytes().strip()).decrypt(Path(source).read_bytes()))
    if document.get('format')!='screening-backup-v1' or set(document.get('tables',{}))!=set(TABLES):
        raise ValueError('Backup format is unsupported')
    # Validate the complete structure before writing any rows. SQL identifiers
    # always come from the fixed application map, never from backup input.
    for table,columns in TABLES.items():
        item=document['tables'][table]
        if item.get('columns')!=list(columns) or not isinstance(item.get('rows'),list):
            raise ValueError('Backup table contract is invalid')
        if any(not isinstance(row,list) or len(row)!=len(columns) for row in item['rows']):
            raise ValueError('Backup row contract is invalid')
    counts={}
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if store.backend=='postgresql':
            db.execute('LOCK TABLE '+','.join(TABLES)+' IN ACCESS EXCLUSIVE MODE')
        empty_tables=list(TABLES)+['login_sessions','login_attempts','account_recovery','worker_heartbeats']
        if any(db.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in empty_tables):
            raise ValueError('Restore target must be empty; no records were replaced')
        for table,columns in TABLES.items():
            rows=document['tables'][table]['rows']
            for row in rows:
                if table in ('jobs','runs'):
                    row=list(row)
                    i=columns.index('document'); value=json.loads(row[i])
                    active=value['status'] in ('queued','processing') if table=='jobs' else value['status'] in ('received','evaluating','validating')
                    if active:
                        value.update(status='failed',error='restore_requires_retry')
                        if table=='jobs':
                            row[columns.index('status')]='failed'
                        row[i]=json.dumps(value)
                db.execute('INSERT INTO '+table+'('+','.join(columns)+') VALUES ('+','.join('?' for _ in columns)+')',tuple(row))
            counts[table]=len(rows)
        if store.backend=='postgresql':
            db.execute("SELECT setval(pg_get_serial_sequence('audit','id'), COALESCE((SELECT MAX(id) FROM audit), 1), EXISTS(SELECT 1 FROM audit))")
    return counts
