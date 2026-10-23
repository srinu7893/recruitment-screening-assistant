"""Install a Cloud Monitoring log alert using an existing notification channel."""
import argparse
import json
import subprocess
from urllib.request import Request,urlopen


def policy(project, service, channel):
    import re
    if not re.fullmatch(r'projects/'+re.escape(project)+r'/notificationChannels/[0-9]+',channel):
        raise ValueError('Provide a notification-channel resource from this project')
    if not re.fullmatch(r'[a-z][a-z0-9-]{1,62}',service):
        raise ValueError('Invalid service name')
    return {'displayName':'Recruitment operations - '+service,'combiner':'OR','enabled':True,
            'notificationChannels':[channel],
            'conditions':[{'displayName':'Recruitment worker, queue or database warning',
                           'conditionMatchedLog':{'filter':'resource.type="cloud_run_revision" AND resource.labels.service_name="'+service+'" AND jsonPayload.event="screening_operations" AND severity>=WARNING'}}],
            'alertStrategy':{'notificationRateLimit':{'period':'900s'},'autoClose':'1800s'},
            'documentation':{'mimeType':'text/markdown','content':'Open Account and operations in the recruitment workspace. Check worker heartbeat, queue warnings and scanner signatures. Inspect logs without exporting applicant data.'}}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',default='project-c9bd3d0e-266f-47bf-852')
    parser.add_argument('--service',default='recruitment-screening')
    parser.add_argument('--channel',required=True)
    args=parser.parse_args()
    document=policy(args.project,args.service,args.channel)
    token=subprocess.run(['gcloud','auth','print-access-token'],check=True,capture_output=True,text=True).stdout.strip()
    base='https://monitoring.googleapis.com/v3/projects/'+args.project+'/alertPolicies'
    request=Request(base,headers={'Authorization':'Bearer '+token})
    with urlopen(request,timeout=30) as response:existing=json.load(response)
    if any(p.get('displayName')==document['displayName'] for p in existing.get('alertPolicies',[])):
        print('A policy with this name exists. Review it in Cloud Monitoring instead of creating a duplicate.');return
    request=Request(base,data=json.dumps(document).encode(),method='POST',headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
    with urlopen(request,timeout=30) as response:result=json.load(response)
    print('Operations alert policy created: '+result['name'])
    print('Verify notification delivery with a controlled test before relying on it.')


if __name__=='__main__':
    try:main()
    except Exception:raise SystemExit('Alert installation failed. Check Monitoring permissions, API availability and the channel resource. Credentials were not printed.') from None
