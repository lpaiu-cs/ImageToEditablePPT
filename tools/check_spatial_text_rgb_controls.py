"""Real OCR from generated RGB; expectations locked before recognition."""
from pathlib import Path
import argparse
import cv2
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from run_region_rgb_baseline import ROOT,digest,save
from image_to_editable_ppt.research.spatial_text import observe_box,select_text
from image_to_editable_ppt.v3.text.ocr import _load_engine


def main(args):
    out=args.output
    out.mkdir(parents=True,exist_ok=False)
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',16)
    cases=[]
    for text in ['CP','PP','Adj','dog','V','v1','q1','n1','two_words','nearby']:
        im=Image.new('RGB',(640,360),'white');draw=ImageDraw.Draw(im)
        token='PP' if text in ('two_words','nearby') else text
        draw.text((300,160),token,font=font,fill='black')
        x,y,r,t=draw.textbbox((300,160),token,font=font)
        box=[x-2,y-2,r+2,t+2]
        if text=='two_words':
            draw.text((r+12,160),'dog',font=font,fill='black');box[2]=r+50
        if text=='nearby':draw.text((r+10,160),'PP',font=font,fill='black')
        if text in ('CP','Adj','dog','V'):draw.line([(r+3,t+3),(r+13,t+60)],fill='black',width=3)
        path=out/(text+'.png');im.save(path)
        cases.append(dict(id=text,image=path.name,sha256=digest(path),box=box,allowed=[None] if text=='two_words' else [None,token]))
    save(out/'lock.json',dict(cases=cases,source_sha256=digest(ROOT/'src/image_to_editable_ppt/research/spatial_text.py'),
        runner_sha256=digest(__file__),font_sha256=digest('C:/Windows/Fonts/arial.ttf'),stage='before_OCR'))
    cv2.setNumThreads(1);engine=_load_engine();rows=[]
    for c in cases:
        rgb=np.array(Image.open(out/c['image']))
        observed=observe_box(rgb,c['box'],engine,context=args.context);label,audit=select_text(rgb,c['box'],observed)
        rows.append(dict(id=c['id'],label=label,audit=audit,observations=observed,passed=label in c['allowed']))
        print(c['id'],label,audit['reason'],flush=True)
    save(out/'results.json',dict(rows=rows,passed=all(r['passed'] for r in rows),selected=sum(r['label'] is not None for r in rows)))
    assert all(r['passed'] for r in rows) and sum(r['label'] is not None for r in rows)>=3


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--context',action='store_true');main(p.parse_args())
