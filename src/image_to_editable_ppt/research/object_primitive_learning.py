"""R17 RGB-derived candidate geometry and object-level preset classification."""
import numpy as np
from PIL import Image
import torch
from torch import nn
from image_to_editable_ppt.ml.family_classifier import _build_cnn
from image_to_editable_ppt.research.ppt_primitive_learning import components


def object_classifier():
    model=_build_cnn(6)
    model[0]=nn.Conv2d(2,16,3,stride=2,padding=1)
    model[9]=nn.AdaptiveAvgPool2d((4,4));model[11]=nn.Linear(64*4*4,6)
    return model


def candidate_crops(rgb,probabilities):
    if rgb.dtype!=np.uint8 or rgb.ndim!=3 or rgb.shape[2]!=3:raise ValueError('uint8 RGB required')
    # Validate the original seven-class tensor before collapsing classes.
    components(probabilities,(rgb.shape[1],rgb.shape[0]),.5)
    p=np.zeros_like(probabilities);p[0]=probabilities[0];p[1]=1-p[0]
    h,w=rgb.shape[:2];objects=components(p,(w,h),.5)
    mask=Image.fromarray(((p[1]>=.5)*255).astype(np.uint8)).resize((w,h),Image.Resampling.NEAREST)
    gray=Image.fromarray(rgb).convert('L');crops=[]
    for obj in objects:
        x,y,a,b=obj['bbox'];px=max(2,(a-x)*.1);py=max(2,(b-y)*.1)
        box=(max(0,int(np.floor(x-px))),max(0,int(np.floor(y-py))),min(w,int(np.ceil(a+px))),min(h,int(np.ceil(b+py))))
        crops.append(np.stack([np.array(gray.crop(box).resize((64,64),Image.Resampling.BILINEAR)),
            np.array(mask.crop(box).resize((64,64),Image.Resampling.NEAREST))]))
    # ponytail: separate non-touching candidates only; overlapping shapes need instance separation.
    return objects,torch.from_numpy(np.stack(crops)).float()/255 if crops else torch.empty(0,2,64,64)


def classify_candidates(model,objects,crops):
    if len(objects)!=len(crops):raise ValueError('candidate/crop count differs')
    if not objects:return []
    with torch.inference_mode():prob=model(crops).softmax(1)
    return [dict(obj,kind=int(p.argmax())+1,confidence=float(p.max())) for obj,p in zip(objects,prob,strict=True)]
