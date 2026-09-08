"""Conservative raw-ink refinement of existing two-owner box trace candidates."""
from collections import Counter
from dataclasses import replace

import cv2
import numpy as np

from image_to_editable_ppt.v3.core.enums import NodeKind, PortOwnerKind
from image_to_editable_ppt.v3.core.types import Point


def _bounds(shape):
    b=shape.bbox
    return np.array([b.x0,b.y0,b.x1,b.y1],dtype=float)


def _line_interval(origin,axis,box):
    low,high=-np.inf,np.inf
    for k in (0,1):
        if abs(axis[k])<1e-10:
            if not box[k]<=origin[k]<=box[k+2]:return None
        else:
            a,b=sorted([(box[k]-origin[k])/axis[k],(box[k+2]-origin[k])/axis[k]])
            low,high=max(low,a),min(high,b)
    return (low,high) if low<=high else None


def _support(t,axis):
    half=float(np.abs(axis).sum())/2
    intervals=sorted((float(x)-half,float(x)+half) for x in t)
    first,right=intervals[0];left=first;covered=0.;gap=0.
    for a,b in intervals[1:]:
        if a<=right+1e-9:right=max(right,b)
        else:
            covered+=right-left;gap=max(gap,a-right);left,right=a,b
    covered+=right-left
    return covered/(right-first),gap,first,right


def _fit(raw,boxes,path,other_boxes,scale):
    audit={}
    def reject(reason):return None,dict(audit,decision='unchanged',reason=reason)
    start,end=path[0],path[-1];length=float(np.linalg.norm(end-start))
    if length<24*scale:return reject('short_candidate')
    axis=(end-start)/length;normal=np.array([-axis[1],axis[0]])
    yy,xx=np.where(raw);pixels=np.column_stack([xx,yy]).astype(float)
    t=(pixels-start)@axis;v=(pixels-start)@normal
    seed=pixels[(t>.2*length)&(t<.8*length)&(abs(v)<=8*scale)]
    if len(seed)<12:return reject('insufficient_seed')
    center=seed.mean(axis=0);values,vectors=np.linalg.eigh(np.cov(seed-center,rowvar=False))
    if values[-1]<4*max(values[0],1e-12):return reject('ambiguous_axis')
    proposed=vectors[:,-1]
    if proposed@axis<0:proposed=-proposed
    axis=proposed;normal=np.array([-axis[1],axis[0]])
    residual=abs((seed-center)@normal)
    audit.update(seed_pixels=len(seed),seed_p95=float(np.percentile(residual,95)),seed_max=float(residual.max()))
    if audit['seed_p95']>2*scale or audit['seed_max']>3*scale:return reject('nonlinear_or_competing_seed')
    if np.ptp((seed-center)@axis)<12*scale:return reject('short_seed_span')
    hits=[_line_interval(center,axis,b) for b in boxes]
    if any(h is None for h in hits):return reject('axis_misses_owner')
    a=center+axis*hits[0][1];b=center+axis*hits[1][0]
    length=float((b-a)@axis)
    if length<24*scale:return reject('short_exterior_span')
    movements=np.linalg.norm(np.array([a,b])-np.array([start,end]),axis=1)
    audit['endpoint_movements']=movements.tolist()
    if movements.max()>6*scale:return reject('large_endpoint_change')
    if abs((path-a)@normal).max()>6*scale:return reject('old_path_conflicts_with_axis')
    for box in other_boxes:
        expanded=box+np.array([-2,-2,2,2])*scale
        interval=_line_interval(a,axis,expanded)
        if interval is not None and max(0,interval[0])<=min(length,interval[1]):return reject('third_owner_near_route')
    t=(pixels-a)@axis;v=(pixels-a)@normal
    exterior=(t>=0)&(t<=length)
    for box in boxes:
        x0,y0,x1,y1=box+np.array([-3,-3,3,3])*scale
        exterior&=~((pixels[:,0]>=x0)&(pixels[:,0]<=x1)&(pixels[:,1]>=y0)&(pixels[:,1]<=y1))
    query=np.zeros(raw.shape,np.uint8)
    coords=pixels[exterior].astype(int)
    if len(coords)<12:return reject('insufficient_exterior')
    query[coords[:,1],coords[:,0]]=1
    _,labels=cv2.connectedComponents(query,connectivity=8)
    ids=labels[yy,xx]
    central=exterior&(t>=8*scale)&(t<=length-8*scale)&(abs(v)<=8*scale)
    seed_ids=np.unique(ids[central]);seed_ids=seed_ids[seed_ids!=0]
    if len(seed_ids)!=1:return reject('multiple_or_missing_source_components')
    selected=exterior&(ids==seed_ids[0])
    nearby=exterior&(abs(v)<=8*scale)&(ids!=seed_ids[0])
    if nearby.any():return reject('disconnected_competing_ink')
    middle=selected&(t>=8*scale)&(t<=length-8*scale)
    if not middle.any():return reject('missing_interior_support')
    audit.update(interior_max=float(abs(v[middle]).max()),whole_component_max=float(abs(v[selected]).max()),
                 original_component_pixels=int(selected.sum()))
    if audit['interior_max']>3*scale or audit['whole_component_max']>6*scale:return reject('branch_crossing_or_curved_source')
    coverage,gap,left,right=_support(t[selected],axis)
    extensions=[max(0.,left),max(0.,length-right)]
    audit.update(coverage=coverage,max_gap=gap,extensions=extensions,support='physical_pixel_cell_projection')
    if coverage<.95 or gap>2*scale:return reject('unsupported_continuity')
    if max(extensions)>6*scale:return reject('unsupported_extension')
    return tuple(Point(float(p[0]),float(p[1])) for p in (a,b)),dict(audit,decision='refined',reason='supported_box_raw_centerline')


def refine_box_centerlines(scene,rgb):
    """Return a scene with only supported existing connector paths replaced."""
    rgb=np.asarray(rgb)
    if rgb.dtype!=np.uint8 or rgb.ndim!=3 or rgb.shape[2]!=3:raise ValueError('uint8 RGB required')
    if (scene.image_size.width,scene.image_size.height)!=(rgb.shape[1],rgb.shape[0]):raise ValueError('original image coordinate size required')
    scale=rgb.shape[0]/360
    raw=(rgb.astype(np.int64)@np.array([2126,7152,722],dtype=np.int64)<1300000).astype(np.uint8)
    owners={s.id:s for s in scene.shapes}
    counts=Counter(frozenset((e.source_owner_id,e.target_owner_id)) for e in scene.connectors)
    edges=[];records={}
    for edge in scene.connectors:
        pair=[owners.get(edge.source_owner_id),owners.get(edge.target_owner_id)]
        supported=(edge.source=='r3_stroke_trace' and 'r3:continuous_component' in edge.provenance
            and len(edge.path_points)>=2 and all(s is not None and s.owner_kind is PortOwnerKind.NODE
                and s.shape_kind in (NodeKind.BOX,NodeKind.ROUNDED_BOX) for s in pair))
        if not supported:
            edges.append(edge);records[edge.id]=dict(decision='unchanged',reason='outside_b_v1_scope');continue
        boxes=[_bounds(s) for s in pair];path=np.array([[p.x,p.y] for p in edge.path_points])
        if not np.isfinite(np.concatenate([*boxes,path.ravel()])).all():raise ValueError('finite geometry required')
        if counts[frozenset((edge.source_owner_id,edge.target_owner_id))]!=1:
            points=None;audit=dict(decision='unchanged',reason='duplicate_owner_pair')
        elif np.all(np.maximum(boxes[0][:2],boxes[1][:2])<=np.minimum(boxes[0][2:],boxes[1][2:])):
            points=None;audit=dict(decision='unchanged',reason='overlapping_owners')
        else:
            x0,y0=np.maximum(0,np.floor(np.minimum(boxes[0][:2],boxes[1][:2]))).astype(int)
            x1,y1=np.minimum([rgb.shape[1],rgb.shape[0]],np.ceil(np.maximum(boxes[0][2:],boxes[1][2:]))).astype(int)
            region=rgb[y0:y1,x0:x1]
            if not region.size or np.median(region.reshape(-1,3),axis=0).min()<225:
                points=None;audit=dict(decision='unchanged',reason='outside_bright_scope')
            else:
                others=[_bounds(s) for s in scene.shapes if s.owner_kind is PortOwnerKind.NODE and s.id not in {p.id for p in pair}]
                points,audit=_fit(raw,boxes,path,others,scale)
        records[edge.id]=dict(audit,previous_path=path.tolist(),new_path=[[p.x,p.y] for p in points] if points else None)
        edges.append(replace(edge,path_points=points) if points else edge)
    return replace(scene,connectors=tuple(edges)),dict(schema='box_centerline_b_v1',connectors=records)
