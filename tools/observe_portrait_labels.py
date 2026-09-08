"""Separate RGB-only portrait-label observation; does not change the frozen CLI."""
import argparse
from pathlib import Path
import sys
import cv2
import numpy as np
from PIL import Image
from run_region_rgb_baseline import ROOT,digest,save
sys.path.insert(0,str(ROOT/'src'))
from image_to_editable_ppt.research.closed_rect_proposals import propose_union,observe_text
from image_to_editable_ppt.research.closed_owner_regions import closed_regions,owner_region
from image_to_editable_ppt.v3.text.ocr import _load_engine


def observe_portrait(rgb,box,excluded,engine):
    x0,y0,x1,y1=box
    if y1-y0<3*(x1-x0):return None,dict(reason='outside_portrait_scope',arms=[])
    crop=rgb[y0:y1,x0:x1];mask=excluded[y0:y1,x0:x1]
    arms=[]
    for name,rotation in [('clockwise',cv2.ROTATE_90_COUNTERCLOCKWISE),('counterclockwise',cv2.ROTATE_90_CLOCKWISE)]:
        patch=cv2.rotate(crop,rotation);omitted=cv2.rotate(mask,rotation)
        label,audit=observe_text(patch,[0,0,patch.shape[1],patch.shape[0]],engine,excluded=omitted,whole_lines=True)
        rereads=[];approved=False
        if label and len(audit['accepted'])==1 and len(audit['lines'][0])==1:
            line=audit['accepted'][0];a,b,c,d=line['bbox']
            a=max(0,int(np.floor(a))-2);b=max(0,int(np.floor(b))-2)
            c=min(patch.shape[1],int(np.ceil(c))+2);d=min(patch.shape[0],int(np.ceil(d))+2)
            if not omitted[b:d,a:c].any():
                for size in (1.,1.5,2.25):
                    result,_=engine(cv2.resize(patch[b:d,a:c],None,fx=size,fy=size,interpolation=cv2.INTER_CUBIC),use_det=False,use_cls=False,use_rec=True)
                    rereads.append(dict(text=result[0][0].strip(),confidence=float(result[0][1]))
                        if result and len(result)==1 and len(result[0])==2 else dict(text='',confidence=0.))
                approved=all(r['text']==label and r['confidence']>=.98 for r in rereads)
        arms.append(dict(orientation=name,label=label,approved=approved,rereads=rereads,spatial=audit))
    accepted=[a for a in arms if a['approved']]
    return (accepted[0] if len(accepted)==1 else None),dict(arms=arms,reason='unique_source_orientation' if len(accepted)==1 else 'ambiguous_or_untrusted_orientation')


def run(image,output):
    output.mkdir(parents=True,exist_ok=False)
    with Image.open(image) as im:
        if im.mode!='RGB':raise ValueError('RGB required')
        rgb=np.asarray(im)
    source=digest(image);code=digest(Path(__file__))
    candidates,_=propose_union(rgb,portrait_boxes=True)
    regions=closed_regions(rgb);engine=_load_engine();rows=[]
    for i,c in enumerate(candidates):
        if c['bbox'][3]-c['bbox'][1]<3*(c['bbox'][2]-c['bbox'][0]):continue
        _,excluded,_,_=owner_region(rgb,c,regions)
        selected,audit=observe_portrait(rgb,c['bbox'],excluded,engine)
        rows.append(dict(id=f'closed:{i}',bbox=c['bbox'],selected=selected,audit=audit))
        print(rows[-1]['id'],selected['label'] if selected else None,[(a['orientation'],a['label'],a['rereads']) for a in audit['arms']],flush=True)
    assert digest(image)==source and digest(Path(__file__))==code
    save(output/'observations.json',dict(source_path=str(image.resolve()),source_sha256=source,runner_sha256=code,rows=rows))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--image',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    a=parser.parse_args();run(a.image,a.output)
