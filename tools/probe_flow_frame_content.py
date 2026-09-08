"""Diagnostic reuse of saved RGB-derived OCR; not a fresh inference result."""
import argparse
import json
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
from run_region_rgb_baseline import save,digest
from image_to_editable_ppt.research.closed_rect_proposals import propose_union
from image_to_editable_ppt.research.closed_content_gate import inspect_content


def run(result,output):
    output.mkdir(parents=True,exist_ok=False)
    data=json.loads(result.read_text());lock=json.loads((result.parent/'lock.json').read_text())
    image=Path(lock['source_path']);assert digest(image)==lock['source_sha256']
    rgb=np.asarray(Image.open(image).convert('RGB'))
    candidates,_=propose_union(rgb,portrait_boxes=True,pixel_agreement=True,compact_boxes=True)
    rows={}
    for i,c in enumerate(candidates):
        key=f'closed:{i}';mask=np.zeros(rgb.shape[:2],np.uint8)
        cv2.drawContours(mask,[c['contour']],-1,1,cv2.FILLED)
        rows[key]=inspect_content(rgb,c,mask,data['text_audit'][key])
        if not rows[key]['eligible'] and 'median' in rows[key]:
            scale=rgb.shape[0]/360
            mask=cv2.erode(mask,np.ones((max(3,round(2*scale))|1,)*2,np.uint8))
            x,y,x1,y1=c['bbox']
            for line in data['text_audit'][key]['accepted']:
                for word in line['words']:
                    a,b,d,e=word['bbox'];pad=max(1,round(scale))
                    mask[max(0,y+int(b)-pad):y+int(np.ceil(e))+pad,max(0,x+int(a)-pad):x+int(np.ceil(d))+pad]=0
            unexplained=(mask!=0)&(np.max(abs(rgb.astype(float)-rows[key]['median']),axis=2)>24)
            marked=rgb.copy();marked[unexplained]=(255,0,0)
            Image.fromarray(marked[y:y1,x:x1]).save(output/(key.replace(':','-')+'.png'))
    save(output/'diagnosis.json',dict(rows=rows,input_sha256=digest(image),result_sha256=digest(result),
        runner_sha256=digest(Path(__file__)),scope='cached image-derived OCR diagnostic; not fresh inference'))
    print([(k,v['reason'],v.get('unexplained_fraction')) for k,v in rows.items() if not v['eligible']])


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--result',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.result,a.output)
