"""Directions only from visible arrowheads outside verified closed node ink."""
from dataclasses import replace

import cv2
import numpy as np

from image_to_editable_ppt.research.closed_nodes import closed_interiors,observe_closed_node
from image_to_editable_ppt.research.source_rays import _head
from image_to_editable_ppt.research.source_centerline_v2 import pixel_cell_support


def _filled_triangle(t,v,length,width,scale,cell,original_pixels,reverse=False):
    """A filled wedge may meet a border before its very last raster tip cell."""
    along=length-t if reverse else t
    across=-v if reverse else v
    _,coarse=_head(t,-v if reverse else v,length,width,scale,cell,reverse=reverse)
    profile=coarse['profile'];peak=coarse['peak'];step=max(.75,scale)
    if peak<2 or len(profile)-peak<3 or len(profile)-peak>12 or profile[peak]<max(1.6*width,width+2*scale):
        return False,dict(coarse,triangle_reason='no_wedge_base')
    left=float(along.max())-16*scale+peak*step
    # Verify the WHOLE terminal enlargement, not just the tail after its widest
    # bin. A T glyph can look solid if its earlier empty arms are cropped away.
    body_start=peak
    while body_start>0 and profile[body_start-1]>=max(1.6*width,width+2*scale):
        body_start-=1
    body_left=float(along.max())-16*scale+body_start*step
    selected=along>=body_left-cell/2
    points=original_pixels[selected].astype(np.int32)
    points-=points.min(axis=0)
    ink=np.zeros((points[:,1].max()+3,points[:,0].max()+3),np.uint8)
    points+=1;ink[points[:,1],points[:,0]]=1
    hull=np.zeros_like(ink)
    cv2.fillConvexPoly(hull,cv2.convexHull(points),1)
    core=cv2.erode(hull,np.ones((3,3),np.uint8))
    core_pixels=int(core.sum())
    solidity=float((core&ink).sum()/max(1,core_pixels))
    if core_pixels<4 or solidity<.95:
        return False,dict(coarse,triangle_reason='unfilled_terminal_core',solidity=solidity,core_pixels=core_pixels)
    rows=[]
    for x in np.arange(left,float(along.max())+.01,step):
        values=across[(along+cell/2>x)&(along-cell/2<x+step)]
        if len(values):rows.append([x+step/2,float(values.min())-cell/2,float(values.max())+cell/2])
    rows=np.asarray(rows)
    if len(rows)<3:return False,dict(coarse,triangle_reason='short_wedge')
    design=np.column_stack([rows[:,0],np.ones(len(rows))])
    low=np.linalg.lstsq(design,rows[:,1],rcond=None)[0]
    high=np.linalg.lstsq(design,rows[:,2],rcond=None)[0]
    residual=max(float(abs(design@low-rows[:,1]).max()),float(abs(design@high-rows[:,2]).max()))
    if low[0]<=.15 or high[0]>=-.15 or residual>max(1.,scale):
        return False,dict(coarse,triangle_reason='unsupported_triangle_sides',solidity=solidity,residual=residual)
    apex=float((high[1]-low[1])/(low[0]-high[0]));apex_v=float(low[0]*apex+low[1])
    extension=apex-(float(along.max())+cell/2)
    accepted=-cell<=extension<=4*scale and abs(apex_v)<=width/2+cell
    return accepted,dict(coarse,triangle_reason='supported_filled_wedge' if accepted else 'unsupported_apex',
        solidity=solidity,side_residual=residual,apex_extension=extension,apex_across=apex_v)


def observe_terminal(rgb,points,boxes):
    if not isinstance(rgb,np.ndarray) or rgb.dtype!=np.uint8 or rgb.ndim!=3 or rgb.shape[2]!=3 or min(rgb.shape[:2])<1:
        raise ValueError('nonempty original uint8 RGB required')
    points=np.asarray(points,dtype=float);boxes=np.asarray(boxes,dtype=float)
    if points.shape!=(2,2) or boxes.shape!=(2,4) or not np.isfinite(points).all() or not np.isfinite(boxes).all():
        raise ValueError('finite two-owner original geometry required')
    if np.any(boxes[:,:2]<0) or np.any(boxes[:,2:]<=boxes[:,:2]) or np.any(boxes[:,2:]>[rgb.shape[1],rgb.shape[0]]):
        raise ValueError('positive boxes inside RGB required')
    s=rgb.shape[0]/360
    contour_raw,holes=closed_interiors(rgb)
    # This stage's bright-page scope has dark/chromatic arrow ink. The generic
    # polarity mask can mark a narrow WHITE gap by a black node border as bright
    # ink, artificially widening a head. Use original integer luminance here.
    raw=(rgb.astype(np.int64)@np.array([2126,7152,722])<1300000).astype(np.uint8)
    a,b=np.asarray(points,dtype=float);delta=b-a;length=float(np.linalg.norm(delta))
    if length<40*s:return None,dict(reason='short_terminal_span')
    axis=delta/length;normal=np.array([-axis[1],axis[0]])
    excluded=np.zeros(raw.shape,np.uint8)
    for box in boxes:
        node,audit=observe_closed_node(rgb,box,evidence=(contour_raw,holes))
        if node is None:return None,dict(reason='unverified_closed_owner',node=audit)
        cv2.drawContours(excluded,[node['contour']],-1,1,cv2.FILLED)
    radius=max(1,round(2*s))
    excluded=cv2.dilate(excluded,np.ones((2*radius+1,2*radius+1),np.uint8))
    y,x=np.where(raw & (1-excluded));pixels=np.column_stack([x,y])
    t=(pixels-a)@axis;v=(pixels-a)@normal
    inside=(t>=-6*s)&(t<=length+6*s)
    query=np.zeros(raw.shape,np.uint8);query[y[inside],x[inside]]=1
    _,components=cv2.connectedComponents(query,connectivity=8)
    ids=components[y,x]
    mid=(t>=16*s)&(t<=length-16*s)&(abs(v)<=8*s)&inside
    keys=np.unique(ids[mid]);keys=keys[keys!=0]
    if len(keys)!=1 or mid.sum()<12:return None,dict(reason='ambiguous_terminal_component')
    selected=inside&(ids==keys[0])
    if (inside&(abs(v)<=8*s)&(ids!=keys[0])).any():return None,dict(reason='separate_terminal_ink')
    if abs(v[selected]).max()>8*s or abs(v[mid]).max()>3*s:return None,dict(reason='branch_or_contact')
    original_pixels=pixels[selected]
    t,v=t[selected],v[selected]
    coverage,gap=pixel_cell_support(t,axis)
    if coverage<.95 or gap>2*s:return None,dict(reason='unsupported_terminal_continuity')
    width=float(mid.sum()/max(1,length-32*s));cell=float(abs(axis).sum())
    end,ea=_filled_triangle(t,v,length,width,s,cell,original_pixels)
    start,sa=_filled_triangle(t,v,length,width,s,cell,original_pixels,reverse=True)
    audit=dict(start=sa,end=ea,shaft_width=width,coverage=coverage,max_gap=gap)
    if start==end:return None,dict(audit,reason='no_unique_observed_head')
    opposite=ea if start else sa
    if max(opposite['profile'])>=max(1.6*width,width+2*s):return None,dict(audit,reason='uncertain_opposite_terminal')
    return (start,end),dict(audit,reason='observed_closed_owner_terminal')


def recover_box_terminals(scene,rgb,box_audit):
    if (scene.image_size.width,scene.image_size.height)!=(rgb.shape[1],rgb.shape[0]):
        raise ValueError('original coordinate scene required')
    owners={s.id:s for s in scene.shapes};edges=[];records={}
    for edge in scene.connectors:
        if edge.arrowhead_start or edge.arrowhead_end or len(edge.path_points)!=2 or box_audit['connectors'].get(edge.id,{}).get('decision')!='refined':
            edges.append(edge);continue
        pair=[owners[edge.source_owner_id],owners[edge.target_owner_id]]
        boxes=[[s.bbox.x0,s.bbox.y0,s.bbox.x1,s.bbox.y1] for s in pair]
        direction,audit=observe_terminal(rgb,[[p.x,p.y] for p in edge.path_points],boxes)
        records[edge.id]=audit
        edges.append(replace(edge,arrowhead_start=direction[0],arrowhead_end=direction[1]) if direction else edge)
    return replace(scene,connectors=tuple(edges)),dict(connectors=records)
