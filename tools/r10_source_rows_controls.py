"""Frozen synthetic row OCR controls; thresholds are diagnostic only."""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from r10_owner_region_p2_audit import snapshot, sha


def build(out):
    out.mkdir(parents=True,exist_ok=False);rows=[]
    fonts=['arial.ttf','times.ttf','consola.ttf']
    texts=['Section 3.4','Model of Code','x=1+2','0O1Il','Compact and Green']
    for font in fonts:
        for index,text in enumerate(texts+['']):
            for variant in ['normal','small','blur','clipped']:
                im=Image.new('RGB',(480,180),'white');draw=ImageDraw.Draw(im)
                f=ImageFont.truetype('C:/Windows/Fonts/'+font,12 if variant=='small' else 20)
                bbox=draw.textbbox((35,65),text,font=f)
                draw.text((35,65),text,font=f,fill='black')
                if not text:
                    draw.line((40,70,180,70),fill='black',width=2)
                    draw.rectangle((200,60,250,85),outline='black',width=2)
                if variant=='clipped' and text:
                    # Remove final glyph's right half; original full text is no longer a strict oracle.
                    draw.rectangle((bbox[2]-5,0,480,180),fill='white')
                if variant=='blur':im=im.filter(ImageFilter.GaussianBlur(1.1))
                key=f'{font[:-4]}-t{index}-{variant}';path=out/(key+'.png');im.save(path)
                rows.append(dict(id=key,rgb=path.name,sha256=sha(path),expected=text,
                                 class_name='nontext' if not text else 'clipped_diagnostic' if variant=='clipped' else 'positive',
                                 font=font,font_sha256=sha('C:/Windows/Fonts/'+font),variant=variant))
    (out/'manifest.json').write_text(json.dumps(rows,indent=2))
    lock=dict(count=len(rows),manifest_sha256=sha(out/'manifest.json'),builder_sha256=sha(__file__))
    (out/'lock.json').write_text(json.dumps(lock,indent=2));print(json.dumps(lock))


def run(fixtures,source,out):
    from rapidocr_onnxruntime import RapidOCR
    out.mkdir(parents=True,exist_ok=False);m,ms=snapshot(source,out,'rows_snapshot')
    lock=json.loads((fixtures/'lock.json').read_text());assert sha(fixtures/'manifest.json')==lock['manifest_sha256']
    engine=RapidOCR();rows=[]
    for c in json.loads((fixtures/'manifest.json').read_text()):
        path=fixtures/c['rgb'];assert sha(path)==c['sha256'];rgb=np.array(Image.open(path));original=rgb.copy()
        owned=np.zeros(rgb.shape[:2],np.uint8);owned[20:160,20:460]=1
        text,audit=m.observe_rows(rgb,dict(bbox=[20,20,460,160]),owned,engine)
        assert np.array_equal(rgb,original)
        diagnostic={}
        for threshold in [.90,.95,.98]:
            accepted=[]
            for b in audit['bands']:
                obs=b['observations']
                if len(obs)!=3 or not obs[0]['text'] or any(o['text']!=obs[0]['text'] or o['confidence']<threshold for o in obs):break
                accepted.append(obs[0]['text'])
            value='\n'.join(accepted) or None
            diagnostic[str(threshold)]=dict(text=value,exact=value==c['expected'] if value else False)
        assert text==diagnostic['0.98']['text']
        rows.append(dict(**c,text=text,audit=audit,diagnostic=diagnostic))
    result=dict(source_sha256=ms,fixture_lock_sha256=sha(fixtures/'lock.json'),runner_sha256=sha(__file__),rows=rows)
    (out/'results.json').write_text(json.dumps(result,indent=2));print(json.dumps({k:v for k,v in result.items() if k!='rows'}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['build','run'])
    p.add_argument('--out',type=Path,required=True);p.add_argument('--source',type=Path);p.add_argument('--fixtures',type=Path);a=p.parse_args()
    if a.mode=='build':build(a.out)
    else:run(a.fixtures,a.source,a.out)
