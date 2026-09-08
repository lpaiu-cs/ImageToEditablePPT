"""P geometry-only independent RGB controls; no OCR/model/GT input."""
import argparse
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image,ImageDraw,ImageFilter


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def build(out):
    out.mkdir(parents=True,exist_ok=False);rows=[]
    modes=['rectangle','open','ellipse','diamond','glyph_hole','photo_frame','nested_white',
           'nested_blue','adjacent','shadow','table','colored_rectangle']
    for mode,s,aa,width in itertools.product(modes,[1,2],[1,4],[1,3]):
        r=s*aa;im=Image.new('RGB',(round(400*r),round(240*r)),'white');d=ImageDraw.Draw(im)
        box=(80*r,80*r,200*r,140*r);stroke=(20,70,170) if mode=='colored_rectangle' else 'black'
        if mode in ('rectangle','open','colored_rectangle','photo_frame','nested_white','nested_blue'):
            d.rectangle(box,fill=(120,160,220) if mode=='nested_blue' else 'white',outline=stroke,width=round(width*r))
        if mode=='open':d.rectangle((125*r,75*r,135*r,(83+width)*r),fill='white')
        if mode=='ellipse':d.ellipse(box,outline='black',width=round(width*r))
        if mode=='diamond':d.polygon([(140*r,80*r),(200*r,110*r),(140*r,140*r),(80*r,110*r)],outline='black',width=round(width*r))
        if mode=='glyph_hole':
            d.rectangle((70*r,70*r,210*r,150*r),fill='black');d.rectangle(box,fill='white')
        if mode in ('nested_white','nested_blue'):
            # Two visibly distinct black boundaries with white/blue gap.
            d.rectangle((83*r,83*r,197*r,137*r),fill='white',outline='black',width=round(r))
        if mode=='adjacent':
            for x in (80,220):d.rectangle((x*r,80*r,(x+120)*r,140*r),outline='black',width=round(width*r))
        if mode=='shadow':
            d.rectangle(box,fill=(100,100,100));im=im.filter(ImageFilter.GaussianBlur(4*r))
        if mode=='photo_frame':
            rng=np.random.default_rng(1303);texture=rng.integers(40,220,(round(50*r),round(110*r),3),dtype=np.uint8)
            im.paste(Image.fromarray(texture),(round(85*r),round(85*r)))
        if mode=='table':
            for x in range(3):
                for y in range(2):d.rectangle(((80+x*80)*r,(60+y*50)*r,(160+x*80)*r,(110+y*50)*r),outline='black',width=round(width*r))
        if aa!=1:im=im.resize((400*s,240*s),Image.Resampling.LANCZOS)
        key=f'{mode}-s{s}-aa{aa}-w{width}';p=out/(key+'.png');im.save(p)
        expected='one' if mode in ('rectangle','colored_rectangle') else 'two' if mode=='adjacent' else 'not_single' if mode in ('nested_white','nested_blue') else 'none' if mode in ('open','ellipse','diamond','shadow') else 'diagnostic_only'
        rows.append(dict(id=key,mode=mode,rgb=p.name,sha256=sha(p),expected=expected))
    (out/'manifest.json').write_text(json.dumps(rows,indent=2));lock=dict(count=len(rows),manifest_sha256=sha(out/'manifest.json'),builder_sha256=sha(__file__),
        contract='Geometry controls fixed before observation. Photo frame, glyph hole and table are semantic scope diagnostics, not automatically false-closed geometry. Close true nested boundaries must not become a single owner.')
    (out/'lock.json').write_text(json.dumps(lock,indent=2));print(json.dumps(lock))


def run(fixtures,source,out,inner_boundaries=False):
    out.mkdir(parents=True,exist_ok=False);lock=json.loads((fixtures/'lock.json').read_text());assert sha(fixtures/'manifest.json')==lock['manifest_sha256']
    snap=out/'closed_rect_snapshot.py';snap.write_bytes(source.read_bytes());sys.path.insert(0,str(source.parents[2]))
    spec=importlib.util.spec_from_file_location('locked_p',snap);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);rows=[]
    for c in json.loads((fixtures/'manifest.json').read_text()):
        p=fixtures/c['rgb'];assert sha(p)==c['sha256'];rgb=np.array(Image.open(p));original=rgb.copy();selected,audit=m.propose(rgb,**({'inner_boundaries':True} if inner_boundaries else {}));assert np.array_equal(original,rgb)
        count=len(selected);expected=c['expected'];passed=count==1 if expected=='one' else count==2 if expected=='two' else count!=1 if expected=='not_single' else count==0 if expected=='none' else None
        rows.append(dict(id=c['id'],mode=c['mode'],expected=expected,passed=passed,selected=[{k:v for k,v in x.items() if k!='contour'} for x in selected],audit=audit))
    summary=dict(count=len(rows),passed=sum(r['passed'] is True for r in rows),failed=sum(r['passed'] is False for r in rows),diagnostic=sum(r['passed'] is None for r in rows),failed_by_mode={mode:sum(r['passed'] is False for r in rows if r['mode']==mode) for mode in sorted({r['mode'] for r in rows})},source_sha256=sha(snap),fixture_lock_sha256=sha(fixtures/'lock.json'),runner_sha256=sha(__file__))
    summary['inner_boundaries']=inner_boundaries
    (out/'results.json').write_text(json.dumps(dict(summary=summary,rows=rows),indent=2));print(json.dumps(summary))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['build','run']);p.add_argument('--out',type=Path,required=True);p.add_argument('--source',type=Path);p.add_argument('--fixtures',type=Path);p.add_argument('--inner-boundaries',action='store_true');a=p.parse_args()
    if a.mode=='build':build(a.out)
    else:run(a.fixtures,a.source,a.out,a.inner_boundaries)
