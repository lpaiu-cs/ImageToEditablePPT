"""Raster-valid offline contracts plus V3 safety checks on frozen V2 proposals.

This is not a new owner detector/selector. Expectations never enter V3 helpers.
"""
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

from r9_duplicate_owner_fixtures import save,sha


def luma_ref(rgb):
    # Independent offline raster calculation; no observer import in build mode.
    x=rgb.astype(np.int64)
    return x[:,:,0]*2126+x[:,:,1]*7152+x[:,:,2]*722


def in_box(shape,b,origin=(0,0)):
    yy,xx=np.indices(shape);xx=xx+origin[0]+.5;yy=yy+origin[1]+.5
    return (b[0]<=xx)&(xx<b[2])&(b[1]<=yy)&(yy<b[3])


def build(args):
    root=Path('artifacts/r9-d-v2-fixtures-final')
    manifest=json.loads((root/'manifest.json').read_text());lookup={r['id']:r for r in manifest}
    expectations={r['id']:r for r in json.loads((root/'expectations.json').read_text())}
    proposals={r['id']:r for r in json.loads(Path('artifacts/r9-d-v2-controls/results.json').read_text())['results']}
    args.out.mkdir(parents=True,exist_ok=False);(args.out/'feature_masks').mkdir()
    records=[];contracts=[]
    for r in manifest:
        if r['population']!='v2_new':continue
        record=dict(r,cached_proposal_ids=proposals[r['id']]['kept_ids'])
        records.append(record)
        e=expectations[r['id']];owners=json.loads(Path(r['owners']).read_text());ids=sorted(o['id'] for o in owners)
        allowed=[ids]
        if e['mode']=='select_or_abstain':allowed.append([e['allowed_keep']])
        elif e['mode']=='preserve_or_either':allowed.extend([[i] for i in ids])
        contract=dict(id=r['id'],allowed_keep_sets=allowed,classification='unchanged_structural_or_scope_contract',
                      category=e['category'],original_v2_expectation=e,new_clean=e['new_clean'])
        if r['base'].startswith(('bright','punct','speck')) or r['base']=='bbox_shift_loss':
            refid=r['id'].replace('v2-'+r['base']+'-','v2-row_clean-',1)
            ref=np.array(Image.open(lookup[refid]['rgb']).convert('RGB'));rgb=np.array(Image.open(r['rgb']).convert('RGB'))
            delta=np.maximum(0,luma_ref(ref)-luma_ref(rgb));maximum=int(delta.max())
            body=(2*delta>=maximum)&(delta>0) if maximum else np.zeros(delta.shape,bool)
            Image.fromarray(body.astype('uint8')*255).save(args.out/'feature_masks'/f'{r["id"]}.png')
            retention={o['id']:bool(np.all(in_box(body.shape,o['bbox_xyxy'])[body])) for o in owners}
            noise_valid=False
            if maximum and r['base']=='speck_far':
                baseline=luma_ref(ref);black_support=(2550000-baseline)>=1275000
                gy,gx=np.where(black_support);fy,fx=np.where(body)
                gh=gy.max()-gy.min()+1;dx=max(gx.min()-fx.max()-1,fx.min()-gx.max()-1,0);dy=max(gy.min()-fy.max()-1,fy.min()-gy.max()-1,0)
                noise_valid=bool(body.sum()<=max(1,(rgb.shape[0]/360)**2) and maximum<=240000 and np.hypot(dx,dy)>2*gh)
            if maximum==0:classification='rasterized_away'
            elif noise_valid:classification='verified_far_background_speck'
            elif all(retention.values()):classification='body_shared'
            else:classification='body_at_risk'
            allowed=[ids]
            for i in ids:
                if maximum==0 or noise_valid or retention[i]:allowed.append([i])
            contract.update(allowed_keep_sets=allowed,classification=classification,reference_id=refid,
                reference_sha256=lookup[refid]['rgb_sha256'],added_pixel_count=int((delta>0).sum()),max_added_luminance_num=maximum,
                body_pixel_count=int(body.sum()),body_retention=retention,noise_valid=noise_valid,
                feature_mask_sha256=sha(args.out/'feature_masks'/f'{r["id"]}.png'))
        contracts.append(contract)
    save(args.out/'manifest.json',records);save(args.out/'expectations.json',contracts)
    lock=dict(schema='r9_d_v3_control_lock',phase='before_v3_execution',records=len(records),mechanism_tests=41,
        v1_v2_unchanged=True,source_v2_manifest_sha256=sha(root/'manifest.json'),source_v2_result_sha256=sha('artifacts/r9-d-v2-controls/results.json'),
        observer_sha256=sha('src/image_to_editable_ppt/research/duplicate_owner_v3.py'),
        test_sha256=sha('tests/test_duplicate_owner_v3_mechanisms.py'),tool_sha256=sha(__file__),
        spec_sha256=sha('docs/r9_d_v3_revision_contract.md'),manifest_sha256=sha(args.out/'manifest.json'),expectations_sha256=sha(args.out/'expectations.json'),
        classifications=dict(Counter(r['classification'] for r in contracts)))
    save(args.out/'lock.json',lock);print(json.dumps(lock))


def run(args):
    from image_to_editable_ppt.research.duplicate_owner_v3 import integer_contrast,candidate_support_check,background_speck_mask
    root=args.fixtures;lock=json.loads((root/'lock.json').read_text())
    assert sha('src/image_to_editable_ppt/research/duplicate_owner_v3.py')==lock['observer_sha256']
    assert sha(__file__)==lock['tool_sha256']
    assert sha(root/'manifest.json')==lock['manifest_sha256'] and sha(root/'expectations.json')==lock['expectations_sha256']
    rows=json.loads((root/'manifest.json').read_text());expected={r['id']:r for r in json.loads((root/'expectations.json').read_text())}
    args.out.mkdir(parents=True,exist_ok=False);(args.out/'audits').mkdir()
    save(args.out/'execution-lock.json',dict(lock_sha256=sha(root/'lock.json'),phase='before_v3_calls',numpy=np.__version__,opencv=cv2.__version__))
    guard=dict(active=False,denied=[])
    def hook(event,values):
        if event=='open' and guard['active']:guard['denied'].append(str(values[0]));raise PermissionError('V3 file IO prohibited')
    sys.addaudithook(hook)
    results=[]
    for r in rows:
        assert sha(r['rgb'])==r['rgb_sha256'] and sha(r['owners'])==r['owners_sha256']
        rgb=np.array(Image.open(r['rgb']).convert('RGB'));owners=json.loads(Path(r['owners']).read_text())
        origin=r['frame']['origin_xy'] if r['frame'] else [0,0]
        full_size=r['frame']['full_size'] if r['frame'] else [rgb.shape[1],rgb.shape[0]]
        # This is a veto of an already-frozen proposal, not an identity decision.
        proposed=r['cached_proposal_ids'];kept=proposed.copy();observations={};failure=[]
        ring=np.ones(rgb.shape[:2],bool);ring[2:-2,2:-2]=False
        try:
            guard['active']=True
            ch=integer_contrast(rgb,ring)
            gy,gx=np.where(ch['core']);ignored=np.zeros(rgb.shape[:2],bool)
            if len(gx):
                gb=[int(gx.min())+origin[0],int(gy.min())+origin[1],int(gx.max())+1+origin[0],int(gy.max())+1+origin[1]]
                ignored,_=background_speck_mask(ch['core'],ch['weak']|ch['residual'],ch['contrast2'],gb,gb[3]-gb[1],scale=full_size[1]/360,origin=origin)
            for o in owners:
                observations[o['id']]=candidate_support_check(ch['core'],ch['weak'],ch['residual'],o['bbox_xyxy'],origin=origin,ignored=ignored)
            if len(proposed)<len(owners) and any(not observations[i]['eligible'] for i in proposed):kept=[o['id'] for o in owners]
            guard['active']=False
            allowed=expected[r['id']]['allowed_keep_sets']
            if sorted(kept) not in allowed:failure.append('raster_valid_contract_violation')
        except Exception as error:
            guard['active']=False;failure.append(type(error).__name__+': '+str(error))
        save(args.out/'audits'/f'{r["id"]}.json',dict(candidate_support=observations,cached_proposal_ids=proposed,kept_ids=kept,
            observer_sha256=lock['observer_sha256'],rgb_sha256=r['rgb_sha256'],source_frame=r['frame']))
        results.append(dict(id=r['id'],base=r['base'],classification=expected[r['id']]['classification'],passed=not failure,failures=failure,
            prior_proposal_passed=sorted(proposed) in expected[r['id']]['allowed_keep_sets'],kept_ids=sorted(kept),
            safety_veto_applied=sorted(kept)!=sorted(proposed),new_clean=expected[r['id']]['new_clean'],selected=len(kept)<len(owners)))
    summary=dict(status='PASS' if all(r['passed'] for r in results) and any(r['new_clean'] and r['selected'] for r in results) and not guard['denied'] else 'FAIL',
        records=len(results),passed=sum(r['passed'] for r in results),failed=sum(not r['passed'] for r in results),
        prior_proposal_raster_valid_failures=sum(not r['prior_proposal_passed'] for r in results),vetoes=sum(r['safety_veto_applied'] for r in results),
        clean_records=sum(r['new_clean'] for r in results),clean_selected=sum(r['new_clean'] and r['selected'] for r in results),
        file_open_denials=guard['denied'],lock_sha256=sha(root/'lock.json'),actual_15_executed=False,
        limitation='Safety mechanisms on frozen V2 proposals, not a new D3 identity/PP recovery run',results=results)
    save(args.out/'results.json',summary);print(json.dumps({k:v for k,v in summary.items() if k!='results'}))
    return 0 if summary['status']=='PASS' else 1


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['build','run']);p.add_argument('--fixtures',type=Path);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();raise SystemExit(build(a) if a.mode=='build' else run(a))
