"""Lock final RGB connectivity before independently observing source rays."""
import argparse
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def ink(rgb):
    # Independent dark-ink extraction, not observer's morphology.
    return (np.max(rgb,axis=2)<110).astype(np.uint8)


def build(out):
    out.mkdir(parents=True,exist_ok=False)
    records=[]
    for mode,angle,s,aa in itertools.product(
        ['clean','nearby','bridged','detached_tip','detached_opposite','short_opposite','central_neighbor'],
        [0,30,60,90,135],[.75,1,1.5],[1,4]):
        r=s*aa;im=Image.new('RGB',(round(360*r),)*2,'white');draw=ImageDraw.Draw(im)
        theta=np.deg2rad(angle);u=np.array([np.cos(theta),np.sin(theta)]);v=np.array([-u[1],u[0]])
        def p(x,y=0):return tuple((np.array([180,180])+x*u+y*v)*r)
        def line(points):draw.line([p(*q) for q in points],fill='black',width=max(1,round(2*r)))
        def poly(points):draw.polygon([p(*q) for q in points],fill='black')
        start=-88 if mode=='detached_opposite' else (-94 if mode=='short_opposite' else -100)
        end=88 if mode=='detached_tip' else 100
        line([(start,0),(end,0)])
        poly([(100,0),(92,5),(92,-5)])
        if mode=='detached_opposite':poly([(-100,0),(-92,5),(-92,-5)])
        if mode=='short_opposite':poly([(-100,0),(-96,5),(-96,-5)])
        if mode in ('nearby','bridged'):
            line([(-94,5),(-94,20)]);line([(-98,20),(-90,20)])
            if mode=='bridged':line([(-94,0),(-94,5)])
        if mode=='central_neighbor':line([(-20,6),(20,6)])
        if aa!=1:im=im.resize((round(360*s),)*2,Image.Resampling.LANCZOS)
        key=f'{mode}-a{angle}-s{s}-aa{aa}';path=out/(key+'.png');im.save(path)
        mask=ink(np.array(im));n,labels,stats,_=cv2.connectedComponentsWithStats(mask,8)
        expected_cc=1 if mode in ('clean','bridged') else 2
        boxes=[]
        for t in [-109 if mode=='short_opposite' else -112,112]:
            c=(np.array([180,180])+t*u)*s;boxes.append([*(c-8*s),*(c+8*s)])
        # This validity gate is recorded before observer import or execution.
        records.append(dict(id=key,mode=mode,scale=s,boxes=boxes,rgb=path.name,sha256=sha(path),
            expected='forward' if mode in ('clean','nearby') else 'abstain',
            expected_components=expected_cc,observed_components=n-1,
            component_areas=stats[1:,cv2.CC_STAT_AREA].tolist(),raster_valid=n-1==expected_cc))
    (out/'manifest.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
    lock=dict(count=len(records),valid=sum(c['raster_valid'] for c in records),
        manifest_sha256=sha(out/'manifest.json'),builder_sha256=sha(__file__),
        contract='Final RGB 8CC count checked before observer. Detached opposite tip must abstain; nearby separate terminal glyph preserves arrow; connected contact and central competitor abstain.')
    (out/'lock.json').write_text(json.dumps(lock,indent=2),encoding='utf-8');print(json.dumps(lock))


def run(fixtures,source,out):
    out.mkdir(parents=True,exist_ok=False)
    lock=json.loads((fixtures/'lock.json').read_text());assert sha(fixtures/'manifest.json')==lock['manifest_sha256']
    snap=out/'source_rays_snapshot.py';snap.write_bytes(source.read_bytes())
    sys.path.insert(0,str(source.parents[2]))
    spec=importlib.util.spec_from_file_location('locked_separated_source',snap)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    rows=[]
    for c in json.loads((fixtures/'manifest.json').read_text()):
        path=fixtures/c['rgb'];assert sha(path)==c['sha256']
        rgb=np.array(Image.open(path));mask=ink(rgb)
        yy,xx=np.where(mask);pixels=np.column_stack([xx,yy])
        for swap in (False,True):
            result,audit=module.observe_pair(pixels,c['boxes'][::-1] if swap else c['boxes'],scale=c['scale'])
            passed=result is None if c['expected']=='abstain' else result is not None and audit['reversed']==swap
            rows.append(dict(id=c['id'],mode=c['mode'],swap=swap,raster_valid=c['raster_valid'],
                passed=bool(passed),expected=c['expected'],audit=audit))
    summary=dict(count=len(rows),valid=sum(r['raster_valid'] for r in rows),
        failed_by_mode={m:sum(r['raster_valid'] and not r['passed'] for r in rows if r['mode']==m) for m in sorted({r['mode'] for r in rows})},
        source_sha256=sha(snap),fixture_lock_sha256=sha(fixtures/'lock.json'),runner_sha256=sha(__file__))
    (out/'results.json').write_text(json.dumps(dict(summary=summary,rows=rows),indent=2),encoding='utf-8');print(json.dumps(summary))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['build','run']);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--source',type=Path);p.add_argument('--fixtures',type=Path);a=p.parse_args()
    if a.mode=='build':build(a.out)
    else:run(a.fixtures,a.source,a.out)
