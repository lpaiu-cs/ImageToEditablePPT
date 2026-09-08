"""Post-calibration baselines, global instance matching and actual COM verification."""
import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess
import sys
import numpy as np
from PIL import Image,ImageDraw
from scipy.optimize import linear_sum_assignment
from r19_instance_detector import ROOT,digest,save,verify,code_lock,geometry,summary,object_counts,write_shapes
from r16_primitive_visual_audit import run as stage_pptx
from image_to_editable_ppt.research.closed_rect_proposals import _iou


def match_indices(objects,expected,ignore_kind=False):
    score=np.array([[_iou(o['bbox'],g['bbox']) if ignore_kind or o['kind']==g['kind'] else 0 for g in expected] for o in objects]).reshape(len(objects),len(expected))
    if not score.size:return set()
    ii,jj=linear_sum_assignment(-((score>=.5).astype(float)+score/(min(score.shape)+1)))
    matched={int(j) for i,j in zip(ii,jj) if score[i,j]>=.5}
    assert len(matched)==(geometry if ignore_kind else object_counts)(objects,expected)['tp']
    return matched


def baseline(manifest,evaluation,output):
    from r18_candidate_validity import observe,load_model,new_classifier,validator,OCC,KIND,select,WEIGHTS,code_lock as old_code
    output.mkdir(parents=True,exist_ok=False);data=json.loads(manifest.read_text())['records']
    result=json.loads((evaluation/'results.json').read_text());assert result['manifest_sha256']==digest(manifest)
    assert (evaluation/'calibration.json').exists();verify(json.loads((evaluation/'lock.json').read_text()))
    checkpoint=ROOT/'artifacts/region-image-only-r18/training-v1/validity.pt'
    assert digest(checkpoint)=='b33985754ffe0a15bc9546c1c75df0f8fa5187d273d441ba22b9a418054ef998'
    lock=dict(files={**old_code(),**WEIGHTS,str(checkpoint):digest(checkpoint),str(manifest.resolve()):digest(manifest),
        **{r['image']:digest(r['image']) for r in data if r['split']=='eval'}});verify(lock);save(output/'baseline-lock.json',lock)
    occupancy=load_model(OCC);kind=new_classifier(KIND);validity=validator(checkpoint).eval()
    for view,threshold in [('full',.5),('multiscale',.99)]:
        arm='r18_'+view;rows=[]
        for r in data:
            if r['split']!='eval':continue
            observed,size=observe(occupancy,kind,validity,r['image']);candidates=observed[view];objects=select(candidates,threshold)
            folder=output/arm/r['id'];folder.mkdir(parents=True);write_shapes(objects,size,folder/'result.pptx')
            rows.append(dict(id=r['id'],family=r['family'],stage=r['stage'],objects=objects,all_candidates=candidates,
                **object_counts(objects,r['objects']),geometry=geometry(objects,r['objects']),coverage=geometry(candidates,r['objects']),
                source_sha256=digest(r['image']),pptx_sha256=digest(folder/'result.pptx')))
        result['arms'][arm]=dict(**summary(rows),rows=rows,per_family={f:summary([r for r in rows if r['family']==f]) for f in sorted({r['family'] for r in rows})},
            negative_fp=sum(r['fp'] for r in rows if r['stage']=='negative'),geometry=summary([r['geometry'] for r in rows]),coverage=summary([r['coverage'] for r in rows]))
    # Stage the instance arm beside baselines without changing any original predictions.
    import shutil
    for r in result['arms']['instance']['rows']:
        folder=output/'instance'/r['id'];folder.mkdir(parents=True);source=evaluation/'instance'/r['id']/'result.pptx'
        assert digest(source)==r['pptx_sha256'];shutil.copyfile(source,folder/'result.pptx')
    verify(lock);save(output/'results.json',result)
    print(json.dumps({a:{k:v for k,v in r.items() if k not in ('rows','per_family')} for a,r in result['arms'].items()},indent=2))


def review(manifest,evaluation,output):
    result=json.loads((evaluation/'results.json').read_text());assert result['manifest_sha256']==digest(manifest)
    records={r['id']:r for r in json.loads(manifest.read_text())['records'] if r['split']=='eval'}
    inputs=json.loads((output/'inputs.json').read_text());assert inputs['results_sha256']==digest(evaluation/'results.json')
    receipts={r['id']:r for r in json.loads((output/'renders/powerpoint_render_manifest.json').read_text(encoding='utf-8-sig'))['records']}
    assert len(receipts)==len(inputs['rows'])
    for row in inputs['rows']:
        receipt=receipts[row['id']];assert row['pptx_sha256']==receipt['pptx_sha256']==digest(receipt['pptx_path'])
        assert receipt['render_sha256']==digest(receipt['render_path'])
    boards=[];roles={}
    for identity,r in records.items():
        assert digest(r['image'])==r['image_sha256'];board=Image.new('RGB',((len(result['arms'])+1)*480,330),'white');draw=ImageDraw.Draw(board)
        with Image.open(r['image']) as im:board.paste(im.convert('RGB').resize((480,300)),(0,30))
        draw.text((4,4),identity,fill='black')
        for col,(arm,arm_result) in enumerate(result['arms'].items(),1):
            row=next(v for v in arm_result['rows'] if v['id']==identity);receipt=receipts[f'{arm}--{identity}']
            with Image.open(receipt['render_path']) as im:
                assert im.size==(960,600);board.paste(im.convert('RGB').resize((480,300)),(col*480,30))
            draw.text((col*480+4,4),f'{arm} TP{row["tp"]} FP{row["fp"]} FN{row["fn"]}',fill='black')
        path=output/(identity+'.png');assert not path.exists();board.save(path);boards.append(dict(id=identity,path=str(path.resolve()),sha256=digest(path)))
    for arm,arm_result in result['arms'].items():
        counts={role:Counter() for role in ('node','container')}
        for row in arm_result['rows']:
            expected=records[row['id']]['objects'];strict=match_indices(row['objects'],expected);geom=match_indices(row['objects'],expected,True)
            candidates=match_indices(row['all_candidates'],expected,True)
            for j,g in enumerate(expected):
                role='container' if g['id'].startswith('container') else 'node';counts[role].update(expected=1,strict_tp=int(j in strict),geometry_tp=int(j in geom),candidate_tp=int(j in candidates))
        roles[arm]=counts
    save(output/'audit.json',dict(boards=boards,roles=roles,checked_pptx=len(inputs['rows']),native_shape_count=sum(r['shape_count'] for r in inputs['rows']),
        results_sha256=digest(evaluation/'results.json'),receipts_sha256=digest(output/'renders/powerpoint_render_manifest.json'),code_sha256=digest(__file__),
        scope='Global one-to-one matches are assigned to GT roles; no separate parent/child rematching.'))
    print(json.dumps(roles,indent=2))


def guarded_predict(trained,image,threshold,output):
    prior=json.loads((trained/'lock.json').read_text());verify(prior)
    files={**code_lock(),str(image.resolve()):digest(image),str((trained/'final.pt').resolve()):digest(trained/'final.pt')}
    subprocess.run(['rtk','proxy',sys.executable,str(ROOT/'tools/r19_instance_detector.py'),'predict','--trained',str(trained),
        '--image',str(image),'--threshold',str(threshold),'--output',str(output)],check=True)
    verify(dict(files=files));save(output/'external-guard.json',dict(files=files,before_after_equal=True,code_sha256=digest(__file__)))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['baseline','prepare','review','predict'])
    for name in ('manifest','evaluation','trained','image','output'):p.add_argument('--'+name,type=Path,required=name=='output')
    p.add_argument('--threshold',type=float,default=.95);a=p.parse_args()
    if a.mode=='baseline':baseline(a.manifest,a.evaluation,a.output)
    elif a.mode=='prepare':stage_pptx(a.manifest,a.evaluation,a.output,'prepare')
    elif a.mode=='review':review(a.manifest,a.evaluation,a.output)
    else:guarded_predict(a.trained,a.image,a.threshold,a.output)
