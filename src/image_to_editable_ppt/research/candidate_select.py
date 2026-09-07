"""R2 fixed candidate selection. No target annotations or OCR-content decisions."""
from dataclasses import replace

import cv2
import numpy as np

from image_to_editable_ppt.research.region_first import area, intersection, pixel_box


def bounds(shape):
    b=shape.bbox
    return b.x0,b.y0,b.x1,b.y1


def duplicate(a,b):
    x,y=bounds(a),bounds(b)
    w=max(a.bbox.width,b.bbox.width)
    h=max(a.bbox.height,b.bbox.height)
    return (intersection(x,y)/min(area(x),area(y))>=.90
        and min(area(x),area(y))/max(area(x),area(y))>=.50
        and all(abs(p-q)<=.16*(w if i%2==0 else h) for i,(p,q) in enumerate(zip(x,y)))
        and abs(a.bbox.center.x-b.bbox.center.x)<=.08*w
        and abs(a.bbox.center.y-b.bbox.center.y)<=.08*h)


def deduplicate(scene):
    incidence={s.id:0 for s in scene.shapes}
    for c in scene.connectors:
        for owner in (c.source_owner_id,c.target_owner_id):
            incidence[owner]+=1
    def priority(s):
        source=(s.source or '').split(':')[-1]
        return (-incidence[s.id],-{'closed_ellipse':3,'closed_outline':2,'uniform_fill':1}.get(source,0),
            -(s.owner_kind.value=='node'),-s.bbox.area,-s.confidence,bounds(s))
    kept=[]
    removed={}
    for s in sorted(scene.shapes,key=priority):
        representative=next((k for k in kept if duplicate(s,k)),None)
        if representative is None:
            kept.append(s)
        else:
            removed[s.id]=dict(reason='duplicate_observation',representative=representative.id)
    return tuple(s for s in scene.shapes if s.id not in removed),removed


def longest_gap(trace):
    best=current=0
    for value in trace:
        current=0 if value else current+1
        best=max(best,current)
    return best/max(1,len(trace))


def source_features(rgb,shape,scope):
    x0,y0,x1,y1=map(round,bounds(shape))
    sx0,sy0,sx1,sy1=scope
    x0,y0,x1,y1=max(sx0,x0),max(sy0,y0),min(sx1,x1),min(sy1,y1)
    crop=rgb[y0:y1,x0:x1]
    if crop.size==0:
        raise ValueError('candidate outside ROI')
    h,w=crop.shape[:2]
    ix,iy=max(1,round(w*.06)),max(1,round(h*.06))
    inner=crop[iy:max(iy+1,h-iy),ix:max(ix+1,w-ix)]
    median=np.median(inner.reshape(-1,3),axis=0)
    uniform=float((np.max(np.abs(inner.astype(float)-median),axis=2)<=24).mean())
    factor=min(1,512/max(inner.shape[:2]))
    small=cv2.resize(inner,(max(1,round(inner.shape[1]*factor)),max(1,round(inner.shape[0]*factor))))
    colored=((small.max(axis=2).astype(int)-small.min(axis=2)>=50)&(small.max(axis=2)>=100)).astype('uint8')
    _,_,stats,_=cv2.connectedComponentsWithStats(colored,8)
    small_areas=[int(n) for n in stats[1:,cv2.CC_STAT_AREA] if 1<=n<=.005*colored.size]
    band=max(2,round(min(w,h)*.025))
    # ROI-clipped bands on both sides of the candidate boundary.
    def dark(a,b,c,d):
        arr=rgb[max(sy0,b):min(sy1,d),max(sx0,a):min(sx1,c)]
        return np.min(arr,axis=2)<200
    tx,ty=max(1,round(w*.1)),max(1,round(h*.1))
    traces=[dark(x0+tx,y0-band,x1-tx,y0+band+1).any(axis=0),
        dark(x0+tx,y1-band,x1-tx,y1+band+1).any(axis=0),
        dark(x0-band,y0+ty,x0+band+1,y1-ty).any(axis=1),
        dark(x1-band,y0+ty,x1+band+1,y1-ty).any(axis=1)]
    return dict(interior_uniform_fraction=uniform,interior_median=median.tolist(),
        small_color_components=len(small_areas),small_color_area_fraction=sum(small_areas)/colored.size,
        side_gap_fractions=[longest_gap(t) for t in traces])


def gap_owners(shape,candidates):
    """Blank face between two wider observed boundaries, not any blank rectangle."""
    x0,y0,x1,y1=bounds(shape)
    tolerance=max(3,.04*min(shape.bbox.width,shape.bbox.height))
    if any(s.id!=shape.id and s.bbox.area<.5*shape.bbox.area
           and intersection(bounds(s),bounds(shape))>=.95*s.bbox.area for s in candidates):
        return None
    for axis in (0,1):
        near,far=[],[]
        for s in candidates:
            if s.id==shape.id:
                continue
            a,b,c,d=bounds(s) if axis==0 else (s.bbox.y0,s.bbox.x0,s.bbox.y1,s.bbox.x1)
            p,q,r,t=(x0,y0,x1,y1) if axis==0 else (y0,x0,y1,x1)
            if c-a<1.5*(r-p) or a>p+tolerance or c<r-tolerance:
                continue
            if abs(d-q)<=tolerance: near.append(s.id)
            if abs(b-t)<=tolerance: far.append(s.id)
        pair=next(((a,b) for a in near for b in far if a!=b),None)
        if pair:
            return pair
    return None


def select_scene(scene,rgb,roi,arm):
    if arm not in ('all_candidates','deduplicate','evidence_select'):
        raise ValueError('unknown R2 arm')
    if arm=='all_candidates':
        return scene,dict(removed={},features={},dropped_connector_ids=[])
    candidates,removed=deduplicate(scene)
    features={}
    if arm=='evidence_select':
        scope=pixel_box(roi,(scene.image_size.width,scene.image_size.height))
        features={s.id:source_features(rgb,s,scope) for s in candidates}
        scatter=[s for s in candidates if features[s.id]['small_color_components']>=20
            and features[s.id]['small_color_area_fraction']>=.01]
        for s in candidates:
            f=features[s.id]
            parent=next((p for p in scatter if intersection(bounds(s),bounds(p))>=.95*s.bbox.area),None)
            gap=gap_owners(s,candidates)
            if parent is not None:
                removed[s.id]=dict(reason='scatter_region',evidence_owner=parent.id)
            elif min(f['interior_median'])>=225 and f['interior_uniform_fraction']>=.985 and gap:
                removed[s.id]=dict(reason='blank_shared_border_face',boundary_owners=gap)
            elif (s.source or '').endswith(':closed_outline') and sum(g>.15 for g in f['side_gap_fractions'])>=2:
                removed[s.id]=dict(reason='discontinuous_envelope')
    retained=tuple(s for s in scene.shapes if s.id not in removed)
    ids={s.id for s in retained}
    connectors=tuple(c for c in scene.connectors if c.source_owner_id in ids and c.target_owner_id in ids)
    return replace(scene,shapes=retained,connectors=connectors),dict(removed=removed,features=features,
        dropped_connector_ids=[c.id for c in scene.connectors if c not in connectors])
