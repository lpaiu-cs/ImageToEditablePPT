"""Post-result read-only explanation of frozen R2 color components; no selection rerun."""
import json
from pathlib import Path
import cv2
import numpy as np
from PIL import Image,ImageDraw,ImageFont,ImageOps
from image_to_editable_ppt.research.native_emit import load_scene
from image_to_editable_ppt.research.region_first import digest

root=Path(__file__).resolve().parents[1]
output=root/'artifacts/region-first-r2/rejection-inspection-v1'
output.mkdir(parents=True,exist_ok=False)
inputs=json.loads((root/'benchmarks/region_first_r2_inputs_v1.json').read_text())['inputs']
results=json.loads((root/'artifacts/region-first-r2/run1/results.json').read_text(encoding='utf-8'))
records=[]
for sample,owner in [('mixed-blip','node:r0:0'),('mixed-attention','container:r0:0'),('negative-plots','node:r0:0')]:
    item=next(x for x in inputs if x['sample']==sample)
    s=next(s for s in load_scene(root/item['scene_path']).shapes if s.id==owner)
    with Image.open(root/item['source_path']) as im:
        crop=np.asarray(im.convert('RGB'))[round(s.bbox.y0):round(s.bbox.y1),round(s.bbox.x0):round(s.bbox.x1)]
    h,w=crop.shape[:2]
    ix,iy=max(1,round(w*.06)),max(1,round(h*.06))
    crop=crop[iy:max(iy+1,h-iy),ix:max(ix+1,w-ix)]
    f=min(1,512/max(crop.shape[:2]))
    small=cv2.resize(crop,(max(1,round(crop.shape[1]*f)),max(1,round(crop.shape[0]*f))))
    mask=((small.max(axis=2).astype(int)-small.min(axis=2)>=50)&(small.max(axis=2)>=100)).astype('uint8')
    count,labels,stats,_=cv2.connectedComponentsWithStats(mask,8)
    ids=[i for i in range(1,count) if 1<=stats[i,cv2.CC_STAT_AREA]<=.005*mask.size]
    used=np.isin(labels,ids)
    record=next(r for r in results['records'] if r['sample']==sample and r['arm']=='evidence_select')
    assert len(ids)==record['selection']['features'][owner]['small_color_components']
    assert abs(used.mean()-record['selection']['features'][owner]['small_color_area_fraction'])<1e-12
    masked=np.full(small.shape,255,np.uint8)
    masked[used]=(0,0,0)
    combined=small.copy()
    combined[used]=(255,0,255)
    sheet=Image.new('RGB',(1560,450),'#f1f5f9')
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',18)
    for i,(arr,title) in enumerate([(small,'Source inner crop'),(masked,'Small colored components'),(combined,'Counted pixels highlighted')]):
        thumb=ImageOps.contain(Image.fromarray(arr),(500,390))
        sheet.paste(thumb,(i*520+(520-thumb.width)//2,50+(390-thumb.height)//2))
        ImageDraw.Draw(sheet).text((i*520+10,10),title,font=font,fill='black')
    path=output/f'{sample}-mask.png'
    sheet.save(path)
    records.append(dict(sample=sample,owner=owner,components=len(ids),fraction=float(used.mean()),path=str(path.relative_to(root)),sha256=digest(path)))
(output/'manifest.json').write_text(json.dumps(dict(status='post_result_explanation_not_new_arm',records=records),indent=2),encoding='utf-8')
