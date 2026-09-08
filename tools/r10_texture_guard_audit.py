"""Original-pixel texture veto controls, separate from semantic approval."""
import argparse
import json
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from r10_owner_region_p2_audit import snapshot,sha


def build(out):
    out.mkdir(parents=True,exist_ok=False);rows=[]
    for mode in ['flat','gray_gradient','color_gradient','arial_text','times_text']:
        for scale in [1,2]:
            im=Image.new('RGB',(600*scale,360*scale),'white')
            w,h=400*scale,180*scale
            if 'gradient' in mode:
                x,y=np.meshgrid(np.linspace(0,1,w),np.linspace(0,1,h))
                a=np.stack([100+140*x]*3,axis=-1) if mode=='gray_gradient' else np.stack([80+160*x,80+160*y,220-100*x],axis=-1)
                im.paste(Image.fromarray(a.astype(np.uint8)),(80*scale,80*scale))
            d=ImageDraw.Draw(im);d.rectangle((80*scale,80*scale,480*scale,260*scale),outline='black',width=scale)
            if mode.endswith('text'):
                font=ImageFont.truetype('C:/Windows/Fonts/'+('arial.ttf' if mode.startswith('arial') else 'times.ttf'),16*scale)
                for i,line in enumerate(['PARENT HEADER Section 3.4','Model of Code: x = 1 + 2','Compact and Green','Input -> Process -> Output','0123456789 ABC xyz']):
                    d.text((95*scale,(95+i*28)*scale),line,font=font,fill='black')
            key=f'{mode}-s{scale}';p=out/(key+'.png');im.save(p)
            rows.append(dict(id=key,rgb=p.name,sha256=sha(p),bbox=[80*scale,80*scale,481*scale,261*scale],mode=mode))
    (out/'manifest.json').write_text(json.dumps(rows,indent=2));lock=dict(manifest_sha256=sha(out/'manifest.json'),builder_sha256=sha(__file__))
    (out/'lock.json').write_text(json.dumps(lock,indent=2));print(json.dumps(lock))


def run(source,out,fixtures):
    out.mkdir(parents=True,exist_ok=False)
    g,gs=snapshot(source/'source_texture_guard.py',out,'texture_snapshot')
    p,ps=snapshot(source/'closed_rect_proposals.py',out,'proposal_snapshot')
    rows=[]
    for f in fixtures:
        lock=json.loads((f/'lock.json').read_text());assert sha(f/'manifest.json')==lock['manifest_sha256']
        for c in json.loads((f/'manifest.json').read_text()):
            path=f/c['rgb'];assert sha(path)==c['sha256'];rgb=np.array(Image.open(path));before=rgb.copy()
            if 'bbox' in c:
                a,b,e,h=c['bbox'];candidates=[dict(bbox=c['bbox'],contour=np.array([[[a,b]],[[e-1,b]],[[e-1,h-1]],[[a,h-1]]],np.int32))]
            else:candidates,_=p.propose(rgb,inner_boundaries=True)
            obs=[dict(bbox=v['bbox'],audit=g.inspect_texture(rgb,v)) for v in candidates]
            assert np.array_equal(rgb,before)
            rows.append(dict(id=c['id'],suite=f.name,observations=obs))
    result=dict(texture_sha256=gs,proposal_sha256=ps,runner_sha256=sha(__file__),fixture_locks={f.name:sha(f/'lock.json') for f in fixtures},rows=rows)
    (out/'results.json').write_text(json.dumps(result,indent=2));print(json.dumps({k:v for k,v in result.items() if k!='rows'}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['build','run']);p.add_argument('--out',type=Path,required=True);p.add_argument('--source',type=Path);p.add_argument('--fixtures',type=Path,nargs='+');a=p.parse_args()
    if a.mode=='build':build(a.out)
    else:run(a.source,a.out,a.fixtures)
