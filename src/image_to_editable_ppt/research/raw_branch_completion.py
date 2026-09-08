"""Supplement existing edges using whole unmerged two-owner source components."""
from dataclasses import replace
from collections import Counter
import cv2
import numpy as np
from image_to_editable_ppt.region.tracing import trace_scene
from image_to_editable_ppt.research.box_centerline_b_v1 import _bounds, _fit
from image_to_editable_ppt.research.box_terminals import observe_terminal
from image_to_editable_ppt.v3.core.enums import ConnectorKind, NodeKind, PortOwnerKind


def add_raw_branches(scene,rgb):
    if (not isinstance(rgb,np.ndarray) or rgb.dtype!=np.uint8 or rgb.ndim!=3
            or rgb.shape[2]!=3 or (scene.image_size.width,scene.image_size.height)!=(rgb.shape[1],rgb.shape[0])):
        raise ValueError('original-coordinate uint8 RGB required')
    raw,audit,mask=trace_scene(scene,rgb,(0,0,1,1),transparent_gaps=True,raw_components=True)
    _,labels=cv2.connectedComponents(mask,connectivity=8)
    records={r['connector_id']:r for r in audit['components'] if 'connector_id' in r}
    owners={s.id:s for s in scene.shapes};edges=list(scene.connectors);checks=[]
    occupied={frozenset((e.source_owner_id,e.target_owner_id)) for e in edges}
    counts=Counter(frozenset((e.source_owner_id,e.target_owner_id)) for e in raw.connectors)
    for edge in raw.connectors:
        pair=[owners[edge.source_owner_id],owners[edge.target_owner_id]]
        key=frozenset(s.id for s in pair);record=records[edge.id]
        if key in occupied or counts[key]!=1 or len(record['owners'])!=2:continue
        if any(s.owner_kind is not PortOwnerKind.NODE or s.shape_kind not in (NodeKind.BOX,NodeKind.ROUNDED_BOX) for s in pair):continue
        boxes=[_bounds(s) for s in pair]
        if np.all(np.maximum(boxes[0][:2],boxes[1][:2])<=np.minimum(boxes[0][2:],boxes[1][2:])):continue
        x0,y0=np.maximum(0,np.floor(np.minimum(boxes[0][:2],boxes[1][:2]))).astype(int)
        x1,y1=np.minimum([rgb.shape[1],rgb.shape[0]],np.ceil(np.maximum(boxes[0][2:],boxes[1][2:]))).astype(int)
        region=rgb[y0:y1,x0:x1]
        if not region.size or np.median(region.reshape(-1,3),axis=0).min()<225:continue
        component=(labels==record['component']).astype(np.uint8)
        points,fit=_fit(component,boxes,np.array([[p.x,p.y] for p in edge.path_points]),
            [_bounds(s) for s in scene.shapes if s.owner_kind is PortOwnerKind.NODE and s.id not in key],rgb.shape[0]/360)
        check=dict(owners=[s.id for s in pair],component=record['component'],fit=fit);checks.append(check)
        if points is None:continue
        direction,terminal=observe_terminal(rgb,[[p.x,p.y] for p in points],boxes)
        check['terminal']=terminal
        cid=f'connector:r12-raw:{record["component"]}'
        edges.append(replace(edge,id=cid,kind=ConnectorKind.ARROW if direction else ConnectorKind.LINE,
            source_port_id=cid+':start',target_port_id=cid+':end',path_points=points,
            arrowhead_start=bool(direction and direction[0]),arrowhead_end=bool(direction and direction[1]),
            source='r12_raw_component',provenance=('r12:unmerged_two_owner_component','r12:component_local_b_v1')))
        occupied.add(key);check['connector_id']=cid
    return replace(scene,connectors=tuple(edges)),dict(checks=checks,added=len(edges)-len(scene.connectors),raw_trace=audit)
