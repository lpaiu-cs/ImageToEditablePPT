"""Evaluate locked R9-D fixtures; expectation data never enters the observer."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import platform
import sys

import cv2
import numpy as np
from PIL import Image

from image_to_editable_ppt.research.duplicate_owner_observations import observe_owners, digest
from r9_duplicate_owner_fixtures import sha, save


def main(args):
    root=args.fixtures
    lock=json.loads((root/'lock.json').read_text())
    assert sha(root/'manifest.json')==lock['manifest_sha256']
    assert sha(root/'expectations.json')==lock['expectations_sha256']
    module=Path('src/image_to_editable_ppt/research/duplicate_owner_observations.py')
    assert sha(module)==lock['observer_sha256']
    assert sha('docs/r9_duplicate_owner_experiment_spec.md')==lock['spec_sha256']
    rows=json.loads((root/'manifest.json').read_text())
    expectations={r['id']:r for r in json.loads((root/'expectations.json').read_text())}
    assert set(expectations)=={r['id'] for r in rows} and len(rows)==lock['count']
    out=args.out;out.mkdir(parents=True,exist_ok=False)
    (out/'audits').mkdir();(out/'masks').mkdir()
    save(out/'execution-lock.json',dict(fixture_lock_sha256=sha(root/'lock.json'),runner_sha256=sha(__file__),
        observer_sha256=sha(module),python=platform.python_version(),numpy=np.__version__,opencv=cv2.__version__,
        spec_sha256=lock['spec_sha256'],phase='before_observer_execution',count=len(rows)))
    guard={'active':False,'denied':[]}
    def hook(event,values):
        if event=='open' and guard['active']:
            guard['denied'].append(str(values[0]));raise PermissionError('observer may not open files')
    sys.addaudithook(hook)
    results=[]; by_geometry={}; written=set(); clean_success=0
    for index,row in enumerate(rows):
        assert sha(row['rgb'])==row['rgb_sha256'] and sha(row['owners'])==row['owners_sha256']
        rgb=np.array(Image.open(row['rgb']).convert('RGB'))
        owners=json.loads(Path(row['owners']).read_text())
        before_rgb=hashlib.sha256(rgb.tobytes()).hexdigest();before_owners=digest(owners)
        failures=[]; audit=None
        try:
            guard['active']=True
            kept_o,audit_o,_=observe_owners(rgb,owners,arm='D-O')
            kept_s,audit,masks=observe_owners(rgb,owners,arm='D-S')
            guard['active']=False
            if kept_o!=owners:failures.append('D-O_mutated_owners')
            if audit_o['clusters']!=audit['clusters'] or audit_o['proposed_suppressed_ids']!=audit['proposed_suppressed_ids']:
                failures.append('arms_disagree')
            if hashlib.sha256(rgb.tobytes()).hexdigest()!=before_rgb or digest(owners)!=before_owners:
                failures.append('input_mutation')
            if any(o not in owners for o in kept_s):failures.append('changed_survivor')
            exp=expectations[row['id']]; kept_ids={o['id'] for o in kept_s}; input_ids={o['id'] for o in owners}
            if exp['mode']=='preserve' and kept_ids!=input_ids:failures.append('false_suppression')
            if exp['mode']=='select_or_abstain' and kept_ids not in (input_ids,{exp['allowed_keep']}):
                failures.append('wrong_representative')
            if exp['required_clean_positive'] and kept_ids=={exp['allowed_keep']}:clean_success+=1
            previous=by_geometry.setdefault(row['geometry_group'],kept_ids)
            if previous!=kept_ids:failures.append('order_or_score_dependence')
            for key,mask in masks.items():
                if key not in written:
                    Image.fromarray(mask.astype('uint8')*255).save(out/'masks'/f'{key}.png');written.add(key)
            for cluster in audit['clusters']:
                for threshold in cluster['thresholds'].values():
                    for metadata in threshold['masks'].values():metadata['artifact']=f"masks/{metadata['sha256']}.png"
            audit.update(spec_sha256=lock['spec_sha256'],code_sha256=lock['observer_sha256'],
                source_png_sha256=row['rgb_sha256'],fixture_lock_sha256=sha(root/'lock.json'))
            save(out/'audits'/f'{row["id"]}.json',audit)
            reasons=sorted({r for c in audit['clusters'] for r in c['reasons']})
        except Exception as error:
            guard['active']=False
            failures.append(type(error).__name__+': '+str(error));kept_ids=set();reasons=[]
        result=dict(id=row['id'],base=row['base'],passed=not failures,failures=failures,kept_ids=sorted(kept_ids),
            proposed_suppressed_ids=audit['proposed_suppressed_ids'] if audit else None,reasons=reasons)
        results.append(result)
        if (index+1)%100==0:print(json.dumps(dict(completed=index+1,failed=sum(not r['passed'] for r in results))),flush=True)
    summary=dict(status='PASS' if all(r['passed'] for r in results) and clean_success and not guard['denied'] else 'FAIL',
        count=len(results),passed=sum(r['passed'] for r in results),failed=sum(not r['passed'] for r in results),
        clean_positive_successes=clean_success,denied_file_opens=guard['denied'],
        failure_counts=dict(Counter(f for r in results for f in r['failures'])),
        reason_counts=dict(Counter(reason for r in results for reason in r['reasons'])),
        by_base={base:dict(total=sum(r['base']==base for r in results),failed=sum(r['base']==base and not r['passed'] for r in results)) for base in sorted({r['base'] for r in results})},
        fixture_lock_sha256=sha(root/'lock.json'),execution_lock_sha256=sha(out/'execution-lock.json'),
        actual_15_image_arm_executed=False,results=results)
    save(out/'results.json',summary)
    print(json.dumps({k:v for k,v in summary.items() if k!='results'},ensure_ascii=False))
    return 0 if summary['status']=='PASS' else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--fixtures',type=Path,required=True);parser.add_argument('--out',type=Path,required=True)
    raise SystemExit(main(parser.parse_args()))
