"""Small preregistered end-to-end OCR controls, not unseen acceptance."""
import json
from pathlib import Path
import cv2
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from run_region_rgb_baseline import ROOT,digest,save
from diagnose_spatial_ocr_owners import observe
from image_to_editable_ppt.research.spatial_ocr_owners import select_cluster
from image_to_editable_ppt.v3.text.ocr import _load_engine


def main():
    out=ROOT/'artifacts/region-source-evidence-r9/spatial-ocr-rgb-controls-v1'
    out.mkdir(parents=True,exist_ok=False)
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',16)
    cases=[]
    for name in ('pp_duplicate','cp_duplicate','adj_duplicate','two_pp','two_rows','partial_root','dot_loss','tie'):
        im=Image.new('RGB',(640,360),'white');draw=ImageDraw.Draw(im)
        text={'cp_duplicate':'CP','adj_duplicate':'Adj','partial_root':'ROOT'}.get(name,'PP')
        draw.text((300,160),text,font=font,fill='black')
        b=list(draw.textbbox((300,160),text,font=font));x,y,r,t=b
        owners=[dict(id='full',bbox=[x-2,y-2,r+2,t+2]),dict(id='cut',bbox=[x-1,y+1,r+2,t+4])]
        allowed=[None,'full']
        if name=='two_pp':
            draw.text((r+5,160),'PP',font=font,fill='black')
            other=list(draw.textbbox((r+5,160),'PP',font=font))
            owners[0]['bbox'][2]=r+9;owners[1]['bbox']=[r-2,y-2,other[2]+2,t+2];allowed=[None]
        if name=='two_rows':
            draw.text((300,175),'PP',font=font,fill='black')
            owners[0]['bbox'][3]=t+9;owners[1]['bbox']=[x-2,t-2,r+2,t+19];allowed=[None]
        if name=='partial_root':owners[1]['bbox']=[x+12,y-2,r-10,t+2];allowed=[None]
        if name=='dot_loss':
            draw.point((r+3,t-1),fill='black');owners[0]['bbox'][2]=r+5
        if name=='tie':owners[1]['bbox']=owners[0]['bbox'].copy();allowed=[None]
        image=out/(name+'.png');im.save(image)
        cases.append(dict(name=name,image=image.name,image_sha256=digest(image),owners=owners,allowed=allowed))
    save(out/'lock.json',dict(stage='before_OCR',cases=cases,source_sha256=digest(ROOT/'src/image_to_editable_ppt/research/spatial_ocr_owners.py'),
        runner_sha256=digest(Path(__file__)),font_sha256=digest('C:/Windows/Fonts/arial.ttf')))
    engine=_load_engine();cv2.setNumThreads(1);results=[]
    for case in cases:
        rgb=np.array(Image.open(out/case['image']))
        obs=observe(rgb,case['owners'],engine)
        if len(obs)!=1:raise AssertionError('fixture must be an overlap cluster')
        winner,audit=select_cluster(rgb,obs[0]);passed=winner in case['allowed']
        results.append(dict(name=case['name'],winner=winner,passed=passed,observation=obs,audit=audit))
        print(case['name'],winner,passed,audit['reason'],flush=True)
    positive=any(r['winner']=='full' for r in results if r['name'].endswith('_duplicate'))
    save(out/'results.json',dict(records=results,clean_positive=positive,passed=all(r['passed'] for r in results) and positive))
    assert all(r['passed'] for r in results) and positive


if __name__=='__main__':main()
