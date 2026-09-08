"""Reject borrowed faces and unbounded same-background fill fragments, not blank boxes."""
from dataclasses import replace
import numpy as np
from image_to_editable_ppt.region.geometry import pixel_box, intersection
from image_to_editable_ppt.region._selection_base import bounds, gap_owners, source_features
from image_to_editable_ppt.v3.core.enums import PortOwnerKind


def filter_identity(scene,rgb,roi):
    scope=pixel_box(roi,(scene.image_size.width,scene.image_size.height))
    removed={}; records={}
    for s in scene.shapes:
        if s.owner_kind is not PortOwnerKind.NODE: continue
        f=source_features(rgb,s,scope); records[s.id]=f
        incident=[c for c in scene.connectors if s.id in (c.source_owner_id,c.target_owner_id)]
        if s.label or incident: continue
        pair=gap_owners(s,scene.shapes)
        if pair and min(f['interior_median'])>=225 and f['interior_uniform_fraction']>=.95:
            # Require TWO observed directed paths on opposing borders, anchored elsewhere.
            b=s.bbox; tol=max(3,.04*min(b.width,b.height)); sides=set(); evidence=[]
            for c in scene.connectors:
                if not c.arrowhead_end and not c.arrowhead_start: continue
                if not set(pair)&{c.source_owner_id,c.target_owner_id}: continue
                for p,q in zip(c.path_points,c.path_points[1:]):
                    for axis,low,high,start,end in ((0,b.x0,b.x1,b.y0,b.y1),(1,b.y0,b.y1,b.x0,b.x1)):
                        fixed=(p.x,q.x) if axis==0 else (p.y,q.y)
                        span=sorted((p.y,q.y) if axis==0 else (p.x,q.x))
                        if span[0]>start+tol or span[1]<end-tol: continue
                        for side,value in enumerate((low,high)):
                            if max(abs(v-value) for v in fixed)<=tol:
                                sides.add((axis,side)); evidence.append(c.id)
            if any((axis,0) in sides and (axis,1) in sides for axis in (0,1)):
                removed[s.id]=dict(reason='borrowed_arrow_borders',connectors=sorted(set(evidence)))
                continue
        if not (s.source or '').endswith(':uniform_fill'): continue
        parents=[p for p in scene.shapes if p.owner_kind is PortOwnerKind.CONTAINER
            and intersection(bounds(s),bounds(p))>=.99*s.bbox.area]
        a,b,c,d=map(round,bounds(s)); pad=max(2,round(min(c-a,d-b)*.08))
        if not parents or a-pad<scope[0] or b-pad<scope[1] or c+pad>scope[2] or d+pad>scope[3]: continue
        bands=[rgb[b-pad:b+pad,a:c],rgb[d-pad:d+pad,a:c],rgb[b:d,a-pad:a+pad],rgb[b:d,c-pad:c+pad]]
        contrasts=[float(np.percentile(np.max(np.abs(v.astype(float)-f['interior_median']),axis=2),90)) for v in bands]
        f['perimeter_contrasts']=contrasts
        # Require all four boundaries to lack contrast, not merely two weak sides.
        if max(contrasts)<18 and f['interior_uniform_fraction']>=.98:
            parent=min(parents,key=lambda p:p.bbox.area)
            pf=source_features(rgb,parent,scope)
            if max(abs(a-b) for a,b in zip(pf['interior_median'],f['interior_median']))<18:
                removed[s.id]=dict(reason='unbounded_container_fill_fragment',parent=parent.id)
    return replace(scene,shapes=tuple(s for s in scene.shapes if s.id not in removed)),dict(removed=removed,features=records)
