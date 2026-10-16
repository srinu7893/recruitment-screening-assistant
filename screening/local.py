"""Start a persistent loopback workspace, optionally with fictional showcase data."""
import argparse
import os
from pathlib import Path
import secrets
import sys

from .storage import Store
from .showcase import seed, dataset


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--showcase', action='store_true')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    folder = Path('data').resolve()
    folder.mkdir(exist_ok=True, mode=0o700)
    token_file = folder / 'local-token.txt'
    if not os.getenv('SCREENING_API_TOKEN'):
        if not token_file.exists():
            token_file.touch(mode=0o600)
            token_file.write_text(secrets.token_urlsafe(32), encoding='utf-8')
        os.environ['SCREENING_API_TOKEN'] = token_file.read_text(encoding='utf-8').strip()
        print(f'Workspace token: open {token_file}', flush=True)
    database = folder / 'screening.sqlite3'
    if args.showcase:
        if os.getenv('DATABASE_URL') or os.getenv('SCREENING_PROVIDER', 'demo') != 'demo':
            parser.error('Showcase startup requires a local demo workspace')
        store = Store(database)
        # Seed only before any server owns this database.
        lock = store.acquire_instance()
        try:
            seed(store, 'local-showcase')
            inbox = folder / 'inbox'
            inbox.mkdir(exist_ok=True)
            marker = folder / '.showcase-inbox-created'
            if not marker.exists():
                (inbox / 'fictional-incoming-resume.txt').write_text(dataset()['profiles'][0]['profile_text'], encoding='utf-8')
                marker.write_text('Synthetic inbox example created once.\n', encoding='utf-8')
            import json
            settings = {'enabled': True, 'role_version': dataset()['role']['role_version'],
                        'inbox_enabled': True, 'feed_enabled': False, 'interval_seconds': 60, 'revision': 0}
            with store.connect() as db:
                db.execute('INSERT OR IGNORE INTO automation_settings VALUES (?, ?)', ('intake', json.dumps(settings)))
        finally:
            lock.close()
    print(f'Open http://127.0.0.1:{args.port} | Resume inbox: {folder / "inbox"}', flush=True)
    from .server import main as serve
    sys.argv = [sys.argv[0], '--db', str(database), '--port', str(args.port)]
    serve()


if __name__ == '__main__':
    main()
