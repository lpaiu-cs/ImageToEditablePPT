"""Separate scope/content diagnostics for the locked D-v2 controls."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

import cv2
import numpy as np
import numpy.ma
from PIL import Image

from image_to_editable_ppt.research.duplicate_owner_v2 import observe_owners_v2
from image_to_editable_ppt.research.duplicate_owner_observations import digest
from r9_duplicate_owner_fixtures import save,sha


def main(args):
    root=args.fixtures;lock=json.loads((root/'lock.json').read_text())
    for file,key in [('manifest.json','manifest_sha256'),('expectations.json','expectations_sha256')]:assert sha(root/file)==lock[key]
    assert sha('src/image_to_editable_ppt/research/duplicate_owner_v2.py')==lock['observer_sha256']
    assert sha('src/image_to_editable_ppt/research/duplicate_owner_observations.py')==lock['helper_sha256']
    assert sha('docs/r9_duplicate_owner_v2_spec.md')==lock['spec_sha256']
    rows=json.loads((root/'manifest.json').read_text());expected={r['id']:r for r in json.loads((root/'expectations.json').read_text())}
    assert len(rows)==lock['total'] and set(expected)=={r['id'] for r in rows}
    out=args.out;out.mkdir(parents=True,exist_ok=False);(out/'audits').mkdir();(out/'masks').mkdir()
    save(out/'execution-lock.json',dict(fixture_lock_sha256=sha(root/'lock.json'),runner_sha256=sha(__file__),numpy=np.__version__,opencv=cv2.__version__,phase='before_geometry'))
    # Validate internal crops against the full RGB before activating the no-IO observer guard.
    fulls={r['id'].split('-aa')[1].split('-')[0]:r for r in rows if r['base']=='crop_full'}
    for r in rows:
        if r['frame'] is None:continue
        aa=r['id'].split('-aa')[1].split('-')[0];full=np.array(Image.open(fulls[aa]['rgb']))
        assert hashlib.sha256(full.tobytes()).hexdigest()==r['frame']['source_sha256']
        crop=np.array(Image.open(r['rgb']));x,y=r['frame']['origin_xy']
        assert np.array_equal(crop,full[y:y+crop.shape[0],x:x+crop.shape[1]])
    guard=dict(active=False,denied=[])
    def hook(event,values):
        if event=='open' and guard['active']:
            guard['denied'].append(str(values[0]));raise PermissionError('observer file IO forbidden')
    sys.addaudithook(hook)
    results=[];geometry={};written=set();crop_observations={}
    for number,r in enumerate(rows,1):
        assert sha(r['rgb'])==r['rgb_sha256'] and sha(r['owners'])==r['owners_sha256']
        rgb=np.array(Image.open(r['rgb']).convert('RGB'));owners=json.loads(Path(r['owners']).read_text())
        rgb_before=hashlib.sha256(rgb.tobytes()).hexdigest();before=digest(owners);fail=[];kept_ids=set();audit=None
        e=expected[r['id']];scope=False;information=False
        try:
            guard['active']=True
            original,oa,_=observe_owners_v2(rgb,owners,arm='V2-O',frame=r['frame'])
            kept,audit,masks=observe_owners_v2(rgb,owners,arm='V2-S',frame=r['frame'])
            guard['active']=False
            assert original==owners and oa['clusters']==audit['clusters']
            assert before==digest(owners) and rgb_before==hashlib.sha256(rgb.tobytes()).hexdigest()
            assert all(o in owners for o in kept)
            kept_ids={o['id'] for o in kept};all_ids={o['id'] for o in owners}
            legal=kept_ids==all_ids
            if e['mode']=='select_or_abstain':legal|=kept_ids=={e['allowed_keep']}
            if e['mode']=='preserve_or_either':legal|=len(kept_ids)==1 and kept_ids<=all_ids
            if not legal:
                scope=e['category']=='scope';information=not scope
                fail.append('scope_violation' if scope else 'fixture_support_or_owner_loss')
            previous=geometry.setdefault(r['geometry_group'],kept_ids)
            if previous!=kept_ids:fail.append('order_or_score_dependence')
            if r['base'] in ('crop_full','crop_context'):
                signature=r['id'].split('-s')[1]
                current=digest(audit['clusters'])
                if signature in crop_observations and current!=crop_observations[signature]:fail.append('crop_full_difference')
                crop_observations[signature]=current
            for key,mask in masks.items():
                if key not in written:Image.fromarray(mask.astype('uint8')*255).save(out/'masks'/f'{key}.png');written.add(key)
            for c in audit['clusters']:
                for m in c.get('masks',{}).values():m['artifact']=f"masks/{m['sha256']}.png"
            audit.update(spec_sha256=lock['spec_sha256'],code_sha256=lock['observer_sha256'],source_png_sha256=r['rgb_sha256'])
            save(out/'audits'/f'{r["id"]}.json',audit)
        except Exception as error:
            guard['active']=False;fail.append(type(error).__name__+': '+str(error))
        proposed=audit['proposed_suppressed_ids'] if audit else []
        reasons=sorted({why for c in audit['clusters'] for why in c['reasons']}) if audit else []
        results.append(dict(id=r['id'],population=r['population'],base=r['base'],passed=not fail,failures=fail,
            kept_ids=sorted(kept_ids),suppressed_ids=proposed,scope_violation=scope,
            offline_fixture_support_or_owner_loss=information,
            semantic_character_loss='not_inferred_from_RGB',geometry_only_control=e['category']=='geometry_only',
            uncertainty_reason=reasons,historical_positive=e.get('historical_positive',False),new_clean=e['new_clean'],
            selected_expected=bool(e.get('allowed_keep') and kept_ids=={e['allowed_keep']})))
        if number%500==0:print(json.dumps(dict(completed=number,failures=sum(not z['passed'] for z in results))),flush=True)
    clean=[r for r in results if r['new_clean']];old=[r for r in results if r['historical_positive']]
    effective=any(r['selected_expected'] for r in clean if r['base']=='row_clean') and any(r['selected_expected'] for r in clean if r['base']=='speck_far')
    summary=dict(status='PASS' if all(r['passed'] for r in results) and effective and not guard['denied'] else 'FAIL',
        total=len(results),passed=sum(r['passed'] for r in results),failed=sum(not r['passed'] for r in results),
        scope_violations=sum(r['scope_violation'] for r in results),fixture_support_or_owner_loss=sum(r['offline_fixture_support_or_owner_loss'] for r in results),
        failure_counts=dict(Counter(f for r in results for f in r['failures'])),denied_file_opens=guard['denied'],
        new_clean=dict(records=len(clean),selected=sum(r['selected_expected'] for r in clean),by_base={b:dict(total=sum(r['base']==b for r in clean),selected=sum(r['base']==b and r['selected_expected'] for r in clean)) for b in {r['base'] for r in clean}},effective=effective),
        historical_positive=dict(records=len(old),selected=sum(r['selected_expected'] for r in old),abstained=sum(not r['suppressed_ids'] for r in old)),
        by_population={p:dict(total=sum(r['population']==p for r in results),failed=sum(r['population']==p and not r['passed'] for r in results)) for p in ('v1_replay','v2_new')},
        by_base={b:dict(total=sum(r['base']==b for r in results),failed=sum(r['base']==b and not r['passed'] for r in results)) for b in sorted({r['base'] for r in results})},
        fixture_lock_sha256=sha(root/'lock.json'),execution_lock_sha256=sha(out/'execution-lock.json'),actual_15_executed=False,results=results)
    save(out/'results.json',summary);print(json.dumps({k:v for k,v in summary.items() if k not in ('results','by_base')}))
    return 0 if summary['status']=='PASS' else 1


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--fixtures',type=Path,required=True);p.add_argument('--out',type=Path,required=True);raise SystemExit(main(p.parse_args()))
