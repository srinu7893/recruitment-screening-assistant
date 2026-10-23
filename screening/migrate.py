"""One-time SQLite -> empty PostgreSQL migration. Both servers must be stopped."""
import argparse
import os
from pathlib import Path
from .storage import Store

TABLES = {
    'workspace_accounts': ('username', 'document'),
    'roles': ('version', 'document'),
    'runs': ('id', 'fingerprint', 'document'),
    'jobs': ('id', 'fingerprint', 'status', 'document'),
    'audit': ('id', 'at', 'actor', 'action', 'target'),
    'webhook_events': ('id', 'at'),
    'automation_settings': ('id', 'document'),
    'intake_records': ('id', 'document'),
    'automation_events': ('id', 'at', 'document'),
}


def migrate(source, target):
    if not Path(source).is_file():
        raise ValueError('Source SQLite file does not exist')
    if not str(target).startswith(('postgres://', 'postgresql://')):
        raise ValueError('Target must be PostgreSQL')
    old, new = Store(source), Store(target)
    old_lock = old.acquire_instance()
    try:
        new_lock = new.acquire_instance()
        try:
            counts = {}
            with old.connect() as src, new.connect() as dst:
                src.execute('BEGIN IMMEDIATE')
                # Exclusive tables prevent a concurrent non-server writer from
                # introducing rows after the empty-target check.
                dst.execute('LOCK TABLE ' + ', '.join(TABLES) + ' IN ACCESS EXCLUSIVE MODE')
                if any(dst.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in TABLES):
                    raise ValueError('Target database must be empty; no records were copied')
                for table, columns in TABLES.items():
                    names = ', '.join(columns)
                    rows = src.execute(f'SELECT {names} FROM {table} ORDER BY rowid').fetchall()
                    for row in rows:
                        dst.execute(f"INSERT INTO {table}({names}) VALUES ({', '.join('?' for _ in columns)})", row)
                    counts[table] = len(rows)
                dst.execute("SELECT setval(pg_get_serial_sequence('audit','id'), COALESCE((SELECT MAX(id) FROM audit), 1), EXISTS(SELECT 1 FROM audit))")
            return counts
        finally:
            new_lock.close()
    finally:
        old_lock.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    args = parser.parse_args()
    try:
        counts = migrate(args.source, os.getenv('DATABASE_URL', ''))
    except Exception:
        parser.exit(2, 'Migration failed. Check database connectivity, stopped servers and empty target; source is unchanged.\n')
    print('Migration complete: ' + ', '.join(f'{k}={v}' for k, v in counts.items()))


if __name__ == '__main__':
    main()
