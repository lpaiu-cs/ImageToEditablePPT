"""RGB/owner-erasure integration probes; expectations locked before source import."""
import argparse
import hashlib
import importlib.util
import itertools
import json
import math
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageDraw


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def build(out):
    out.mkdir(parents=True,exist_ok=False)
    rows=[]
    modes=['clean','tip_outside','double_source_hidden','contact_unmasked',
           'contact_other_masked','head_other_masked','glyph_owner_contact']
    for mode,s,aa,offset in itertools.product(modes,[.75,1,1.5],[1,4],[.1,.5,.9,1.1]):
        r=s*aa
        im=Image.new('RGB',(round(360*r),)*2,'white');d=ImageDraw.Draw(im)
        def line(points): d.line([(x*r,y*r) for x,y in points],fill='black',width=max(1,round(2*r)))
        def poly(points): d.polygon([(x*r,y*r) for x,y in points],fill='black')
        line([(80,180),(280,180)])
        poly([(280,180),(272,175),(272,185)])
        boxes=[[60,172,76,188],[284,172,300,188]]
        if mode=='tip_outside':
            boxes[1][0]=280+offset
        if mode=='double_source_hidden':
            poly([(80,180),(88,175),(88,185)])
            boxes[0][2]=90+offset
        if mode in ('contact_unmasked','contact_other_masked'):
            line([(274,180),(274,200)])
        if mode=='contact_other_masked':
            boxes.append([270,180+offset,278,203])
        if mode=='head_other_masked':
            # Other owner's bbox covers one wing without crossing the axis.
            boxes.append([270,180+offset,282,187])
        if mode=='glyph_owner_contact':
            # Geometric T-like glyph touches the tip and continues inside owner.
            line([(280,180),(291,180)])
            line([(288,174),(288,186)])
            boxes[1][0]=280+offset
        if aa!=1: im=im.resize((round(360*s),)*2,Image.Resampling.LANCZOS)
        key=f'{mode}-s{s}-aa{aa}-o{offset}';p=out/(key+'.png');im.save(p)
        rows.append(dict(id=key,mode=mode,scale=s,rgb=p.name,sha256=sha(p),
                         boxes=[[v*s for v in b] for b in boxes],
                         expected='forward' if mode in ('clean','tip_outside') else 'abstain'))
    (out/'manifest.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
    lock=dict(count=len(rows),manifest_sha256=sha(out/'manifest.json'),builder_sha256=sha(__file__),
              contract='Clean and complete exterior tip should survive. Masked competing heads and contacts must not become newly certain arrows. Glyph contact is a conservative ambiguity probe, not proof of wrong direction.')
    (out/'lock.json').write_text(json.dumps(lock,indent=2),encoding='utf-8');print(json.dumps(lock))


def run(fixtures,source,out):
    out.mkdir(parents=True,exist_ok=False)
    lock=json.loads((fixtures/'lock.json').read_text());assert sha(fixtures/'manifest.json')==lock['manifest_sha256']
    snap=out/'source_rays_snapshot.py';snap.write_bytes(source.read_bytes())
    sys.path.insert(0,str(source.parents[2]))
    spec=importlib.util.spec_from_file_location('locked_rays',snap)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    from image_to_editable_ppt.v3.emit.models import EmitScene,EmitShapePrimitive
    from image_to_editable_ppt.v3.core.enums import NodeKind,PortOwnerKind
    from image_to_editable_ppt.v3.core.types import BBox,ImageSize
    import image_to_editable_ppt.region.strokes as strokes
    import image_to_editable_ppt.research.source_centerline_v2 as centerline
    dependencies={m.__file__:sha(m.__file__) for m in (strokes,centerline)}
    rows=[]
    for c in json.loads((fixtures/'manifest.json').read_text()):
        p=fixtures/c['rgb'];assert sha(p)==c['sha256']
        rgb=np.array(Image.open(p).convert('RGB'))
        raw=module.stroke_mask(rgb);masked=raw.copy()
        for x0,y0,x1,y1 in c['boxes']:
            masked[max(0,math.floor(y0)):math.ceil(y1)+1,max(0,math.floor(x0)):math.ceil(x1)+1]=0
        removed=int(np.count_nonzero(raw & ~masked))
        for swap in (False,True):
            shapes=tuple(EmitShapePrimitive(str(i),PortOwnerKind.NODE,
                NodeKind.LABEL_ANCHOR if i<2 else NodeKind.BOX,BBox(*b),.9) for i,b in enumerate(c['boxes']))
            if swap: shapes=shapes[::-1]
            scene=EmitScene(ImageSize(rgb.shape[1],rgb.shape[0]),shapes=shapes)
            result,audit=module.add_source_rays(scene,rgb)
            edges=[(e.source_owner_id,e.target_owner_id) for e in result.connectors]
            expected=[] if c['expected']=='abstain' else [('0','1')]
            yy,xx=np.where(raw)
            before,before_audit=module.observe_pair(np.column_stack([xx,yy]),c['boxes'][:2],
                scale=c['scale'],other_boxes=c['boxes'][2:])
            rows.append(dict(id=c['id'],mode=c['mode'],swap=swap,expected=c['expected'],
                passed=edges==expected,edges=edges,removed_pixels=removed,
                raw_pair_supported=before is not None,raw_pair_audit=before_audit,audit=audit))
    summary=dict(count=len(rows),passed=sum(r['passed'] for r in rows),
                 failed_by_mode={m:sum(not r['passed'] for r in rows if r['mode']==m) for m in sorted({r['mode'] for r in rows})},
                 source_sha256=sha(snap),dependencies=dependencies,fixture_lock_sha256=sha(fixtures/'lock.json'),runner_sha256=sha(__file__))
    (out/'results.json').write_text(json.dumps(dict(summary=summary,rows=rows),indent=2),encoding='utf-8');print(json.dumps(summary))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['build','run']);p.add_argument('--out',required=True,type=Path)
    p.add_argument('--source',type=Path);p.add_argument('--fixtures',type=Path);a=p.parse_args()
    if a.mode=='build':build(a.out)
    else:run(a.fixtures,a.source,a.out)
