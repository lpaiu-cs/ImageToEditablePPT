"""Frozen-detector multiscale candidates; binary closed-structure validity is independent of kind."""
import numpy as np
from PIL import Image
import torch
from image_to_editable_ppt.research.object_primitive_learning import candidate_crops
from image_to_editable_ppt.research.ppt_primitive_learning import SIZE
from image_to_editable_ppt.research.closed_rect_proposals import _iou


def view_candidates(model,rgb):
    image=np.array(Image.fromarray(rgb).resize(SIZE,Image.Resampling.BILINEAR))
    tensor=torch.from_numpy(image).permute(2,0,1).float()/255
    with torch.inference_mode():prob=model(tensor[None]).softmax(1)[0].numpy()
    return candidate_crops(rgb,prob)


def merge_views(objects,crops):
    # Full proposals retain priority. Containment alone is not duplicate evidence.
    order=sorted(range(len(objects)),key=lambda i:(objects[i]['view']!='full',
        -(objects[i]['bbox'][2]-objects[i]['bbox'][0])*(objects[i]['bbox'][3]-objects[i]['bbox'][1])))
    kept=[]
    for i in order:
        if objects[i]['view']=='full' or not any(_iou(objects[i]['bbox'],objects[j]['bbox'])>.7 for j in kept):kept.append(i)
    return [objects[i] for i in kept],crops[kept]


def propose(model,rgb):
    if rgb.dtype!=np.uint8 or rgb.ndim!=3 or rgb.shape[2]!=3:raise ValueError('uint8 RGB required')
    h,w=rgb.shape[:2];full,full_crops=view_candidates(model,rgb)
    full=[dict(o,id='full:'+o['id'],view='full') for o in full];objects=list(full);crops=list(full_crops)
    tw,th=round(w*.6),round(h*.6)
    for index,(left,top) in enumerate(((0,0),(w-tw,0),(0,h-th),(w-tw,h-th))):
        rows,tiles=view_candidates(model,rgb[top:top+th,left:left+tw])
        for obj,crop in zip(rows,tiles,strict=True):
            x,y,a,b=obj['bbox']
            if (left>0 and x<=2) or (top>0 and y<=2) or (left+tw<w and a>=tw-2) or (top+th<h and b>=th-2):continue
            objects.append(dict(obj,id=f'tile{index}:'+obj['id'],view=f'tile{index}',bbox=[left+x,top+y,left+a,top+b]));crops.append(crop)
    stacked=torch.stack(crops) if crops else torch.empty(0,2,64,64)
    multi,multi_crops=merge_views(objects,stacked)
    # ponytail: four fixed views, not an adaptive image pyramid or instance segmentation.
    return dict(full=(full,full_crops),multiscale=(multi,multi_crops))


def supervision(objects,expected):
    overlap=np.array([max((_iou(o['bbox'],g['bbox']) for g in expected),default=0.) for o in objects])
    return np.where(overlap>=.7,1,np.where(overlap<=.2,0,-1))


def validity_scores(model,crops):
    if not len(crops):return np.empty(0)
    with torch.inference_mode():return torch.cat([model(x).softmax(1)[:,1] for x in crops.split(64)]).numpy()
