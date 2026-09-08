"""Independent final-RGB controls for closed-owner terminal direction."""
import argparse
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image,ImageDraw


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def build(out):
    out.mkdir(parents=True,exist_ok=False);rows=[]
    modes=['arrow','plain','double','glyph','compact_glyph','branch','cross','separate_opposite','hidden_opposite',
           'truncated_opposite','nearbyhead','curve','shape_contact']
    for mode,angle,s,aa,shape in itertools.product(modes,[0,30,90],[.75,1,1.5],[1,4],['rectangle','ellipse']):
        r=s*aa;im=Image.new('RGB',(round(360*r),)*2,'white');d=ImageDraw.Draw(im)
        theta=np.deg2rad(angle);u=np.array([np.cos(theta),np.sin(theta)]);v=np.array([-u[1],u[0]])
        def point(x,y=0):return np.array([180,180])+x*u+y*v
        def line(points):d.line([tuple(point(x,y)*r) for x,y in points],fill='black',width=max(1,round(2*r)))
        def poly(points):d.polygon([tuple(point(x,y)*r) for x,y in points],fill='black')
        inset=16 if shape=='ellipse' else 16/max(abs(u));lo,hi=-100+inset,100-inset
        line([(lo,0),(0,15),(hi,0)] if mode=='curve' else [(lo,0),(hi,0)])
        if mode not in ('plain','glyph','compact_glyph'):poly([(hi,0),(hi-8,5),(hi-8,-5)])
        if mode=='double':poly([(lo,0),(lo+8,5),(lo+8,-5)])
        if mode=='glyph':
            line([(hi-6,-6),(hi-6,6)]);line([(hi-10,-6),(hi-2,-6)])
        if mode=='compact_glyph':
            line([(hi-4,-4),(hi-4,4)]);line([(hi-7,-4),(hi-1,-4)])
        if mode=='branch':line([(25,0),(40,25)])
        if mode=='cross':line([(0,-30),(0,30)])
        if mode=='separate_opposite':poly([(lo+1,0),(lo+5,5),(lo+5,-5)]);d.line([tuple(point(lo+6,y)*r) for y in [-7,7]],fill='white',width=max(1,round(2*r)))
        if mode=='hidden_opposite':poly([(lo-10,0),(lo-2,5),(lo-2,-5)])
        if mode=='truncated_opposite':poly([(lo-2,0),(lo+6,5),(lo+6,-5)])
        if mode=='nearbyhead':poly([(lo+6,5),(lo+12,10),(lo+12,5)])
        if mode=='shape_contact':line([(hi-1,0),(hi-1,12)])
        boxes=[]
        for t in [-100,100]:
            c=point(t);b=[*(c-16),*(c+16)];boxes.append([x*s for x in b])
            coords=tuple(x*r for x in b)
            # Outline only: hidden original stroke evidence must remain in RGB.
            if shape=='ellipse':d.ellipse(coords,outline='black',width=max(1,round(2*r)))
            else:d.rectangle(coords,outline='black',width=max(1,round(2*r)))
        if aa!=1:im=im.resize((round(360*s),)*2,Image.Resampling.LANCZOS)
        key=f'{mode}-{shape}-a{angle}-s{s}-aa{aa}';p=out/(key+'.png');im.save(p)
        rows.append(dict(id=key,mode=mode,rgb=p.name,sha256=sha(p),boxes=boxes,
            points=[(point(lo)*s).tolist(),(point(hi)*s).tolist()],expected='forward' if mode=='arrow' else 'abstain'))
    (out/'manifest.json').write_text(json.dumps(rows,indent=2));lock=dict(count=len(rows),manifest_sha256=sha(out/'manifest.json'),builder_sha256=sha(__file__),contract='Only arrow positive. Hidden or truncated opposing head/contact must not gain direction by owner exclusion. Other structural negatives abstain; final raster validity audited separately.')
    (out/'lock.json').write_text(json.dumps(lock,indent=2));print(json.dumps(lock))


def run(fixtures,source,out):
    out.mkdir(parents=True,exist_ok=False);lock=json.loads((fixtures/'lock.json').read_text());assert sha(fixtures/'manifest.json')==lock['manifest_sha256']
    snap=out/'box_terminals_snapshot.py';snap.write_bytes(source.read_bytes());sys.path.insert(0,str(source.parents[2]))
    spec=importlib.util.spec_from_file_location('locked_terminals',snap);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    dependency_paths=[source.with_name(n) for n in ['closed_nodes.py','source_rays.py','source_centerline_v2.py']]
    deps={str(p):sha(p) for p in dependency_paths};rows=[]
    for c in json.loads((fixtures/'manifest.json').read_text()):
        p=fixtures/c['rgb'];assert sha(p)==c['sha256'];rgb=np.array(Image.open(p));original=rgb.copy()
        for swap in [False,True]:
            direction,audit=module.observe_terminal(rgb,c['points'][::-1] if swap else c['points'],c['boxes'][::-1] if swap else c['boxes'])
            assert np.array_equal(rgb,original)
            passed=direction is None if c['expected']=='abstain' else direction is not None and tuple(direction)==((True,False) if swap else (False,True))
            rows.append(dict(id=c['id'],mode=c['mode'],swap=swap,passed=passed,direction=direction,audit=audit))
    assert all(sha(p)==h for p,h in deps.items()),'dependency changed during execution'
    summary=dict(count=len(rows),passed=sum(r['passed'] for r in rows),failed_by_mode={m:sum(not r['passed'] for r in rows if r['mode']==m) for m in sorted({r['mode'] for r in rows})},source_sha256=sha(snap),dependencies=deps,fixture_lock_sha256=sha(fixtures/'lock.json'),runner_sha256=sha(__file__))
    (out/'results.json').write_text(json.dumps(dict(summary=summary,rows=rows),indent=2));print(json.dumps(summary))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['build','run']);p.add_argument('--out',type=Path,required=True);p.add_argument('--fixtures',type=Path);p.add_argument('--source',type=Path);a=p.parse_args()
    if a.mode=='build':build(a.out)
    else:run(a.fixtures,a.source,a.out)
