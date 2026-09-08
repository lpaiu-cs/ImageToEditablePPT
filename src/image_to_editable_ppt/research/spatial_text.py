"""RGB-only spatial OCR labels; preserves all geometry and connector fields."""
from dataclasses import replace
import math
import cv2
import numpy as np
from image_to_editable_ppt.region.strokes import stroke_mask
from image_to_editable_ppt.research.spatial_ocr_owners import envelope, intersection, area
from image_to_editable_ppt.v3.core.enums import PortOwnerKind


def observe_box(rgb, box, engine):
    x0=max(0,math.floor(box[0])-2);y0=max(0,math.floor(box[1])-2)
    x1=min(rgb.shape[1],math.ceil(box[2])+2);y1=min(rgb.shape[0],math.ceil(box[3])+2)
    if x0>=x1 or y0>=y1 or (x1-x0)*(y1-y0)>40000:
        return []
    crop=rgb[y0:y1,x0:x1]
    color=np.median(crop.reshape(-1,3),axis=0).tolist()
    padded=cv2.copyMakeBorder(crop,16,16,16,16,cv2.BORDER_CONSTANT,value=color)
    observations=[]
    for scale in (3.,4.5):
        found,_=engine(cv2.resize(padded,None,fx=scale,fy=scale,interpolation=cv2.INTER_CUBIC))
        observations.append(dict(scale=scale,words=[dict(text=w[1],confidence=float(w[2]),
            polygon=[[float(p[0])/scale-16+x0,float(p[1])/scale-16+y0] for p in w[0]]) for w in found or []]))
    return observations


def select_text(rgb, box, observations):
    def reject(reason):return None,dict(reason=reason)
    if len(observations)!=2:return reject('missing_observations')
    chosen=[];extras=[]
    for observation in observations:
        inside=[]
        for word in observation['words']:
            b=envelope(word);cx=(b[0]+b[2])/2;cy=(b[1]+b[3])/2
            if not box[0]<=cx<=box[2] or not box[1]<=cy<=box[3]:
                continue
            inside.append(word)
        major=[w for w in inside if w['confidence']>=.95]
        if len(major)!=1:return reject('not_single_confident_owned_word')
        chosen.append(major[0]);extras.extend(w for w in inside if w is not major[0])
    first,second=chosen
    if first['text'].strip()!=second['text'].strip():return reject('text_scale_disagreement')
    a,b=map(envelope,chosen)
    inter=intersection(a,b)
    if inter/max(1e-9,area(a)+area(b)-inter)<.8:return reject('spatial_scale_disagreement')
    if any(intersection(box,b)/max(1e-9,area(b))<.9 for b in (a,b)):
        return reject('word_outside_owner')
    for word in chosen:
        p=np.asarray(word['polygon']);direction=p[1]-p[0]
        if abs(math.degrees(math.atan2(direction[1],direction[0])))>10:return reject('word_orientation_unsupported')
    # Lower-confidence OCR can be discarded only if it is an actual long stroke,
    # not an unexplained extra glyph in this same owner.
    if extras:
        raw=stroke_mask(rgb)
        _,labels=cv2.connectedComponents(raw,connectivity=8)
        yy,xx=np.indices(raw.shape)
        height=max(a[3]-a[1],b[3]-b[1]);scale=rgb.shape[0]/360
        for word in extras:
            e=envelope(word)
            if intersection(e,a)>0 or intersection(e,b)>0:return reject('overlapping_extra_snippet')
            mask=(xx>=e[0])&(xx<=e[2])&(yy>=e[1])&(yy<=e[3])&(raw>0)
            ids=np.unique(labels[mask])
            if not len(ids):return reject('unexplained_extra_snippet')
            for key in ids:
                y,x=np.where(labels==key);points=np.column_stack([x,y]).astype(float)
                if len(points)<4:return reject('extra_glyph_component')
                center=points.mean(0);_,v=np.linalg.eigh(np.cov(points-center,rowvar=False));u=v[:,-1]
                t=(points-center)@u;r=np.abs((points-center)@np.array([-u[1],u[0]]))
                if np.ptp(t)<3*height or np.percentile(r,95)>2.5*scale or r.max()>4*scale:
                    return reject('extra_glyph_component')
    return first['text'].strip(),dict(reason='two_scale_spatial_word',word_boxes=[a,b],
        confidence=min(w['confidence'] for w in chosen),source_stroke_extras=len(extras))


def recover_spatial_text(scene,rgb,engine):
    shapes=[];audit={}
    for shape in scene.shapes:
        if shape.owner_kind is not PortOwnerKind.NODE:
            shapes.append(shape);continue
        b=shape.bbox;box=[b.x0,b.y0,b.x1,b.y1]
        observations=observe_box(rgb,box,engine)
        label,record=select_text(rgb,box,observations)
        audit[shape.id]=dict(record,observations=observations,previous_label=shape.label,
            changed=label is not None and label!=shape.label)
        shapes.append(replace(shape,label=label) if label is not None else shape)
    return replace(scene,shapes=tuple(shapes)),audit
