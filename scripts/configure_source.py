"""Prepare an approved JSON feed in workflow configuration; no secret values."""
import argparse
import json
import subprocess
from urllib.parse import urlsplit
from scripts.cloud_release import validate


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',required=True)
    parser.add_argument('--role-version',required=True)
    parser.add_argument('--token-secret')
    parser.add_argument('--token-version')
    parser.add_argument('--repo',default='srinu7893/recruitment-screening-assistant')
    args=parser.parse_args()
    parts=urlsplit(args.url)
    if parts.scheme!='https' or not parts.hostname or parts.username or parts.password or parts.fragment or parts.query or parts.port not in (None,443):
        raise SystemExit('Use an approved HTTPS feed URL without credentials, query tokens or fragments')
    if bool(args.token_secret)!=bool(args.token_version):
        raise SystemExit('Provide both token secret name and pinned version, or neither')
    result=subprocess.run(['gh','variable','get','CLOUD_RUN_CONFIG_JSON','--repo',args.repo,'--env','recruitment-cloud'],check=True,capture_output=True,text=True)
    config=json.loads(result.stdout)
    config.update(connector_url=args.url,connector_role=args.role_version,sync_seconds=0)
    config['allowed_hosts']=sorted(set(config.get('allowed_hosts',[]))|{parts.hostname.lower()})
    if args.token_secret:
        config['secrets']['SCREENING_CONNECTOR_TOKEN']={'name':args.token_secret,'version':args.token_version}
    else:
        config['secrets'].pop('SCREENING_CONNECTOR_TOKEN',None)
    validate(config,require_scanner=False)
    print('This will configure the approved host with automatic polling initially paused: '+parts.hostname)
    print('Confirm that the feed and role are approved before deploying this configuration.')
    subprocess.run(['gh','variable','set','CLOUD_RUN_CONFIG_JSON','--repo',args.repo,'--env','recruitment-cloud'],input=json.dumps(config),text=True,check=True,capture_output=True)
    print('Workflow configuration updated. Grant runtime access to any token secret, deploy main and verify Sync now. Then choose the role, feed and interval in Automation to enable polling. No live connection has been claimed.')


if __name__=='__main__':
    try:
        main()
    except subprocess.CalledProcessError:
        raise SystemExit('GitHub configuration update failed. Check Cloud Shell GitHub access.') from None
