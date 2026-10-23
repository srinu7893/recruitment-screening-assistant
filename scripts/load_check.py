"""Small authenticated synthetic load check; not a production capacity claim."""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import getpass
import http.cookiejar
import json
import statistics
import time
from urllib.request import Request,build_opener,HTTPCookieProcessor
from uuid import uuid4


def check(url, username, password, count=10, workers=2):
    if not 1<=count<=20 or not 1<=workers<=4:
        raise ValueError('Use 1–20 resumes and 1–4 submitting workers')
    opener=build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()));csrf=''
    def call(path,body=None):
        request=Request(url+path,data=json.dumps(body).encode() if body is not None else None,
                        headers={'Content-Type':'application/json','X-CSRF-Token':csrf})
        with opener.open(request,timeout=180) as response:
            return json.load(response)
    session=call('/auth/login',{'username':username,'password':password});csrf=session['csrf']
    prefix='loadcheck-'+uuid4().hex[:16]
    started=time.monotonic();ids=[prefix+'-'+str(i) for i in range(count)]
    try:
        health=call('/health')
        if health['identity']['role']!='admin' or health['provider']!='rules':
            raise ValueError('This check requires an admin in a rules-mode workspace')
        call('/roles',{'role_version':prefix,'title':'FICTIONAL LOAD CHECK - '+prefix,
                      'criteria':[{'id':'python','description':'Support scripting','phrases':['Python'],'required':True,'question':'Explain your work.'}]})
        def submit(key):
            begin=time.monotonic()
            call('/uploads',{'request_id':key,'role_version':prefix,'filename':key+'-FICTIONAL.txt',
                             'content_base64':base64.b64encode(('FICTIONAL LOAD CHECK ONLY. Used Python for test support. '+key).encode()).decode()})
            return time.monotonic()-begin
        with ThreadPoolExecutor(max_workers=workers) as pool:
            latencies=list(pool.map(submit,ids))
        pending=set(ids);deadline=time.monotonic()+180
        while pending and time.monotonic()<deadline:
            for job in call('/jobs'):
                if job['id'] in pending:
                    if job['status']=='failed':
                        raise ValueError('A synthetic load job failed; inspect the loadcheck records')
                    if job['status']=='completed':
                        run=call('/runs?id='+job['id'])
                        if run['result']['assessments'][0]['status']!='partial':
                            raise ValueError('Unexpected synthetic screening result')
                        pending.remove(job['id'])
            if pending:time.sleep(2)
        if pending:raise ValueError('Synthetic jobs did not finish within the check window')
        elapsed=time.monotonic()-started
        for key in ids:
            call('/delete',{'run_id':key})
        report={'synthetic_resumes':count,'submitting_workers':workers,'elapsed_seconds':round(elapsed,2),
                'submit_median_seconds':round(statistics.median(latencies),2),
                'submit_max_seconds':round(max(latencies),2),'all_results_verified':True,'synthetic_runs_deleted':True}
        print(json.dumps(report,indent=2))
        print('Small workload check only. The synthetic role remains in role history; this does not certify capacity.')
        return report
    finally:
        try:call('/auth/logout',{})
        except Exception:pass


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',required=True);parser.add_argument('--count',type=int,default=10);parser.add_argument('--workers',type=int,default=2)
    args=parser.parse_args()
    from screening.deployment import public_origin
    url=public_origin(args.url)
    if not url:raise ValueError('Use the HTTPS application URL')
    check(url,input('Admin username: ').strip(),getpass.getpass('Admin password (not displayed): '),args.count,args.workers)


if __name__=='__main__':
    try:main()
    except Exception:raise SystemExit('Load check failed. Inspect the clearly labelled loadcheck jobs and service health. No credential values were printed.') from None
