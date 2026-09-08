"""Spatial OCR observations from RGB/bboxes only; shared by tools and pipeline."""
import itertools
import math
import cv2
import numpy as np
from image_to_editable_ppt.research.duplicate_owner_observations import overlap,components


def observe(rgb, owners, engine):
    adj=[set() for _ in owners]
    for i,j in itertools.combinations(range(len(owners)),2):
        if overlap(owners[i]['bbox'],owners[j]['bbox'])[0]>0:adj[i].add(j);adj[j].add(i)
    results=[]
    for indices in components(adj):
        if len(indices)<2:continue
        group=[owners[i] for i in indices];boxes=[o['bbox'] for o in group]
        row=dict(owners=group,observations=[]);results.append(row)
        if len(indices)>4 or any(j not in adj[i] for i,j in itertools.combinations(indices,2)):
            row['reason']='unsupported_cluster';continue
        x0=max(0,math.floor(min(b[0] for b in boxes))-2);y0=max(0,math.floor(min(b[1] for b in boxes))-2)
        x1=min(rgb.shape[1],math.ceil(max(b[2] for b in boxes))+2);y1=min(rgb.shape[0],math.ceil(max(b[3] for b in boxes))+2)
        crop=rgb[y0:y1,x0:x1];color=np.median(crop.reshape(-1,3),axis=0).tolist()
        padded=cv2.copyMakeBorder(crop,16,16,16,16,cv2.BORDER_CONSTANT,value=color)
        row['crop']=[x0,y0,x1,y1]
        for scale in (3.,4.5):
            enlarged=cv2.resize(padded,None,fx=scale,fy=scale,interpolation=cv2.INTER_CUBIC)
            found,_=engine(enlarged)
            row['observations'].append(dict(scale=scale,words=[dict(
                polygon=[[float(p[0])/scale-16+x0,float(p[1])/scale-16+y0] for p in word[0]],
                text=word[1],confidence=float(word[2])) for word in found or []]))
    return results
