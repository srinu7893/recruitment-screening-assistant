"""Create a hashed account secret directly in GCP; never print credentials."""
import argparse
import getpass
import json
import subprocess
from screening.password_auth import hash_password


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True)
    parser.add_argument('--secret', default='recruitment-password-accounts')
    args = parser.parse_args()
    username = input('Admin username (lowercase): ').strip()
    name = input('Admin display name: ').strip()
    password = getpass.getpass('Admin password (at least 15 characters): ')
    if password != getpass.getpass('Repeat password: '):
        raise SystemExit('Passwords did not match; nothing changed')
    accounts = [{'username': username, 'name': name, 'role': 'admin', 'password_hash': hash_password(password)}]
    from screening.password_auth import PasswordAuth
    PasswordAuth(None, accounts, True)
    result = subprocess.run(['gcloud', 'secrets', 'describe', args.secret, '--project', args.project], capture_output=True)
    if result.returncode:
        # A failed permission/network check must not be treated as absence.
        if b'NOT_FOUND' not in result.stderr:
            raise SystemExit('Unable to inspect secret; check your Cloud Shell project access')
        command = ['gcloud', 'secrets', 'create', args.secret, '--replication-policy=automatic']
    else:
        command = ['gcloud', 'secrets', 'versions', 'add', args.secret]
    subprocess.run([*command, '--project', args.project, '--data-file=-'], input=json.dumps(accounts).encode(), check=True)
    print('Hashed admin account saved in Secret Manager. Keep the password private.')


if __name__ == '__main__':
    main()
