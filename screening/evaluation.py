"""Small fictional regression corpus; never a substitute for a recruiter pilot."""
import argparse
import json
from pathlib import Path
from .contracts import validate_output
from .providers import DemoProvider, OpenAIProvider
from .showcase import export_dataset


def evaluate_provider(provider):
    data=export_dataset(); records=[]; matched=0; compared=0; valid=0
    for profile in data['profiles']:
        record={'scenario':profile['id'],'valid_output':False,'agreement':None}
        try:
            raw=provider.analyze(data['role'],profile['id'],profile['profile_text'])
            result=validate_output(raw,data['role'],profile['id'],profile['profile_text'])
            expected={a['criterion_id']:a['status'] for a in profile['assessments']}
            differences=[{'criterion':a['criterion_id'],'expected':expected[a['criterion_id']],'actual':a['status']}
                         for a in result['assessments'] if expected[a['criterion_id']] != a['status']]
            count=len(expected); matched+=count-len(differences);compared+=count;valid+=1
            record.update(valid_output=True,agreement=(count-len(differences))/count,
                          recommendation=result['recommendation'],expected_recommendation=profile['result']['recommendation'],
                          differences=differences)
        except Exception:
            record['error']='provider_or_validation_failed'
        records.append(record)
    return {'provider':provider.name,'model':provider.model,'profiles':len(records),'valid_outputs':valid,
            'criterion_agreement':matched/compared if compared else None,'criteria_compared':compared,
            'limitations':'Six fictional authored scenarios only. Agreement excludes invalid outputs, which are counted separately. Exact quotes do not prove semantic correctness. Recruiter review and broader evaluation required; no deployment is automatically approved.',
            'scenarios':records}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--provider',choices=['demo','openai'],default='demo')
    parser.add_argument('--output',default='artifacts/evaluation/report.json')
    args=parser.parse_args()
    provider=OpenAIProvider() if args.provider=='openai' else DemoProvider()
    report=evaluate_provider(provider)
    path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,indent=2))
    print('Evaluation complete: '+str(report['valid_outputs'])+'/'+str(report['profiles'])+' valid outputs; review the report before drawing quality conclusions.')


if __name__=='__main__':main()
