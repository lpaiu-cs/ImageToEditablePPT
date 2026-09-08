"""Independent Pillow closed-contour RGB fixtures, locked before observation."""
import argparse
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import sys

import cv2
import numpy as np
from PIL import Image,ImageDraw


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def build(out):
    out.mkdir(parents=True,exist_ok=False);rows=[]
    modes=['ellipse','rectangle','roundedrect','capsule','diamond','rotatedellipse','openarc',
           'rawgap','colorfill','nested','nested_green','nested_blue','nested_small_green','nested_small_blue','adjacent','arrowcontact','solidpatch']
    for mode,s,aa,thickness,offset in itertools.product(modes,[.75,1,2],[1,4],[1,2,4],[0,.08]):
        r=s*aa;im=Image.new('RGB',(round(240*r),round(160*r)),'white');d=ImageDraw.Draw(im)
        b=[70,50,170,110];fill=(230,205,160) if mode=='colorfill' else (255,255,255)
        if mode.endswith('_green'):fill=(180,230,190)
        if mode.endswith('_blue'):fill=(180,210,240)
        box=tuple(v*r for v in b);width=max(1,round(thickness*r))
        if mode in ('ellipse','colorfill','adjacent','arrowcontact') or mode.startswith('nested'):d.ellipse(box,fill=fill,outline='black',width=width)
        if mode in ('rectangle','rawgap'):d.rectangle(box,fill=fill,outline='black',width=width)
        if mode in ('roundedrect','capsule'):d.rounded_rectangle(box,radius=(12 if mode=='roundedrect' else 30)*r,fill=fill,outline='black',width=width)
        if mode=='diamond':d.polygon([(120*r,50*r),(170*r,80*r),(120*r,110*r),(70*r,80*r)],outline='black',width=width)
        if mode=='rotatedellipse':
            t=np.linspace(0,2*np.pi,361);u=np.array([np.cos(np.pi/6),np.sin(np.pi/6)]);v=np.array([-u[1],u[0]])
            points=[tuple((np.array([120,80])+50*np.cos(a)*u+30*np.sin(a)*v)*r) for a in t]
            d.line(points,fill='black',width=width)
            xy=np.array(points)/r;b=[*xy.min(axis=0),*xy.max(axis=0)]
        if mode=='openarc':d.arc(box,15,340,fill='black',width=width)
        if mode=='rawgap':d.rectangle((119*r,47*r,121*r,(52+thickness)*r),fill='white')
        if mode.startswith('nested'):
            child=(98,67,142,93) if '_small_' in mode else (83,58,157,102)
            d.ellipse(tuple(x*r for x in child),fill=(240,180,180),outline='black',width=width)
        if mode=='adjacent':d.ellipse((173*r,50*r,233*r,110*r),fill=(180,220,240),outline='black',width=width)
        if mode=='arrowcontact':
            d.line([(20*r,80*r),(70*r,80*r)],fill='black',width=width)
            d.polygon([(70*r,80*r),(62*r,75*r),(62*r,85*r)],fill='black')
        if mode=='solidpatch':d.rectangle(box,fill=(100,100,100))
        if aa!=1:im=im.resize((round(240*s),round(160*s)),Image.Resampling.LANCZOS)
        # Detector association perturbation; no pixels or expected verdicts depend on observer.
        bw,bh=b[2]-b[0],b[3]-b[1]
        bbox=[(b[0]+offset*bw)*s,(b[1]+offset*bh)*s,(b[2]+offset*bw)*s,(b[3]+offset*bh)*s]
        key=f'{mode}-s{s}-aa{aa}-w{thickness}-o{offset}';p=out/(key+'.png');im.save(p)
        rgb=np.array(im);dark=(rgb.astype(np.int64)@np.array([2126,7152,722])<1300000).astype(np.uint8)
        contours,hierarchy=cv2.findContours(dark,cv2.RETR_CCOMP,cv2.CHAIN_APPROX_NONE)
        areas=[] if hierarchy is None else [cv2.contourArea(c) for c,h in zip(contours,hierarchy[0]) if h[3]>=0]
        large_hole=any(a>.3*bw*bh*s*s for a in areas)
        expected='ellipse' if mode in ('ellipse','colorfill','arrowcontact','adjacent') else 'rectangle' if mode=='rectangle' else 'not_ellipse' if mode in ('roundedrect','capsule') else 'nested_no_child_fill' if mode=='nested' else 'abstain'
        if mode.startswith('nested_'):expected='parent_color_or_abstain'
        valid=(not large_hole) if mode in ('rawgap','openarc') else large_hole if mode in ('ellipse','rectangle','colorfill','arrowcontact','adjacent','roundedrect','capsule') else True
        rows.append(dict(id=key,mode=mode,rgb=p.name,sha256=sha(p),bbox=bbox,expected=expected,
                         expected_fill=list(fill) if mode=='colorfill' or mode.startswith('nested_') else None,raster_valid=valid,independent_hole_areas=areas))
    (out/'manifest.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
    lock=dict(count=len(rows),valid=sum(r['raster_valid'] for r in rows),manifest_sha256=sha(out/'manifest.json'),builder_sha256=sha(__file__),
        contract='Expected geometry/fill fixed before observer. Nested child color is not outer fill. Open raster gaps must have no large dark-ink hole.')
    (out/'lock.json').write_text(json.dumps(lock,indent=2));print(json.dumps(lock))


def run(fixtures,source,out):
    out.mkdir(parents=True,exist_ok=False);lock=json.loads((fixtures/'lock.json').read_text())
    assert sha(fixtures/'manifest.json')==lock['manifest_sha256']
    snapshot=out/'closed_nodes_snapshot.py';snapshot.write_bytes(source.read_bytes());sys.path.insert(0,str(source.parents[2]))
    spec=importlib.util.spec_from_file_location('closed_nodes_snapshot',snapshot);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    rows=[]
    for c in json.loads((fixtures/'manifest.json').read_text()):
        path=fixtures/c['rgb'];assert sha(path)==c['sha256'];rgb=np.array(Image.open(path));before=rgb.copy()
        observed,audit=module.observe_closed_node(rgb,c['bbox']);assert np.array_equal(rgb,before)
        result=None if observed is None else dict(ellipse=observed['ellipse'],fill=observed['style'].fill,stroke=observed['style'].stroke)
        if c['expected']=='abstain':passed=observed is None
        elif c['expected']=='not_ellipse':passed=observed is None or not observed['ellipse']
        elif c['expected']=='nested_no_child_fill':passed=observed is None or observed['style'].fill is None
        elif c['expected']=='parent_color_or_abstain':passed=observed is None or (observed['style'].fill is not None and max(abs(x-y) for x,y in zip(observed['style'].fill,c['expected_fill']))<=3)
        else:
            passed=observed is not None and observed['ellipse']==(c['expected']=='ellipse')
            if passed and c['expected_fill'] is not None:passed=observed['style'].fill is not None and max(abs(x-y) for x,y in zip(observed['style'].fill,c['expected_fill']))<=3
        rows.append(dict(id=c['id'],mode=c['mode'],raster_valid=c['raster_valid'],passed=bool(passed),observed=result,audit=audit))
    summary=dict(count=len(rows),valid=sum(r['raster_valid'] for r in rows),failed_by_mode={m:sum(r['raster_valid'] and not r['passed'] for r in rows if r['mode']==m) for m in sorted({r['mode'] for r in rows})},source_sha256=sha(snapshot),fixture_lock_sha256=sha(fixtures/'lock.json'),runner_sha256=sha(__file__))
    (out/'results.json').write_text(json.dumps(dict(summary=summary,rows=rows),indent=2));print(json.dumps(summary))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['build','run']);p.add_argument('--out',required=True,type=Path);p.add_argument('--source',type=Path);p.add_argument('--fixtures',type=Path);a=p.parse_args()
    if a.mode=='build':build(a.out)
    else:run(a.fixtures,a.source,a.out)
