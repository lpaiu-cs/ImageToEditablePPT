"""Frozen R2.1 local ablations; never cascade parent rejection into children."""
from dataclasses import replace
import cv2
import numpy as np
from image_to_editable_ppt.research.candidate_select import bounds,deduplicate,gap_owners,source_features
from image_to_editable_ppt.research.region_first import pixel_box

ARMS=('baseline','face_only','envelope_only','local_scatter','guarded_scatter','combined')


def dot_features(rgb,shape,scope):
    x0,y0,x1,y1=map(round,bounds(shape))
    a,b,c,d=scope
    crop=rgb[max(b,y0):min(d,y1),max(a,x0):min(c,x1)]
    h,w=crop.shape[:2]
    ix,iy=max(1,round(w*.06)),max(1,round(h*.06))
    inner=crop[iy:max(iy+1,h-iy),ix:max(ix+1,w-ix)]
    scale=min(1,512/max(inner.shape[:2]))
    small=cv2.resize(inner,(max(1,round(inner.shape[1]*scale)),max(1,round(inner.shape[0]*scale))))
    mask=((small.max(axis=2).astype(int)-small.min(axis=2)>=50)&(small.max(axis=2)>=100)).astype('uint8')
    _,_,stats,centers=cv2.connectedComponentsWithStats(mask,8)
    total=0
    dots=[]
    for stat,center in zip(stats[1:],centers[1:]):
        _,_,w,h,area=map(int,stat)
        if not 1<=area<=.005*mask.size:
            continue
        total+=1
        if area>=3 and .5<=w/h<=2 and area/(w*h)>=.45:
            dots.append(center)
    xspan=yspan=0.
    concentration=1.
    if dots:
        normalized=np.asarray(dots)/[mask.shape[1],mask.shape[0]]
        xspan,yspan=np.percentile(normalized,90,axis=0)-np.percentile(normalized,10,axis=0)
        hist=np.histogram(normalized[:,1],bins=np.linspace(0,1,9))[0]
        concentration=sum(sorted(hist)[-2:])/len(dots)
    return dict(dot_count=len(dots),small_components=total,dot_fraction=len(dots)/max(1,total),
        x_span=float(xspan),y_span=float(yspan),two_row_bin_fraction=float(concentration))


def select_local(scene,rgb,roi,arm):
    if arm not in ARMS:
        raise ValueError('unknown R2.1 arm')
    candidates,removed=deduplicate(scene)
    features={}
    if arm!='baseline':
        scope=pixel_box(roi,(scene.image_size.width,scene.image_size.height))
        for s in candidates:
            f=source_features(rgb,s,scope)
            f['dots']=dot_features(rgb,s,scope)
            gap=gap_owners(s,candidates)
            flags=dict(face=min(f['interior_median'])>=225 and f['interior_uniform_fraction']>=.985 and bool(gap),
                envelope=(s.source or '').endswith(':closed_outline') and sum(g>.15 for g in f['side_gap_fractions'])>=2,
                local_scatter=f['small_color_components']>=20 and f['small_color_area_fraction']>=.01)
            dot=f['dots']
            flags['guarded_scatter']=(flags['local_scatter'] and dot['dot_count']>=20 and dot['dot_fraction']>=.65
                and dot['x_span']>=.25 and dot['y_span']>=.35 and dot['two_row_bin_fraction']<=.70)
            f['flags']=flags
            features[s.id]=f
            enabled={'face_only':('face',),'envelope_only':('envelope',),'local_scatter':('local_scatter',),
                'guarded_scatter':('guarded_scatter',),'combined':('face','envelope','guarded_scatter')}[arm]
            reasons=[r for r in enabled if flags[r]]
            if reasons:
                removed[s.id]=dict(reason='+'.join(reasons),evidence_owner=s.id)
    selected=tuple(s for s in scene.shapes if s.id not in removed)
    owners={s.id for s in selected}
    edges=tuple(c for c in scene.connectors if c.source_owner_id in owners and c.target_owner_id in owners)
    return replace(scene,shapes=selected,connectors=edges),dict(removed=removed,features=features,
        dropped_connector_ids=[c.id for c in scene.connectors if c not in edges])
