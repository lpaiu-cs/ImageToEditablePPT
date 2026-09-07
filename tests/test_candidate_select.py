from dataclasses import replace

import cv2
import numpy as np

from image_to_editable_ppt.research.candidate_select import duplicate,select_scene
from image_to_editable_ppt.v3.core.enums import NodeKind,PortOwnerKind,ConnectorKind
from image_to_editable_ppt.v3.core.types import BBox,ImageSize,Point
from image_to_editable_ppt.v3.emit.models import EmitScene,EmitShapePrimitive,EmitConnectorPrimitive


def shape(name,box,source='closed_outline'):
    return EmitShapePrimitive(name,PortOwnerKind.NODE,NodeKind.BOX,BBox(*box),.9,
        label='Frozen OCR',source='visual_geometry:'+source)


def scene(*shapes,connectors=()):
    return EmitScene(image_size=ImageSize(400,400),shapes=shapes,connectors=connectors)


def select(s,rgb=None,arm='deduplicate'):
    return select_scene(s,np.full((400,400,3),255,np.uint8) if rgb is None else rgb,(0,0,1,1),arm)


def test_fill_ellipse_observations_dedup_but_nested_and_touching_survive():
    outer=shape('outer',(20,20,380,380))
    ellipse=shape('ellipse',(100,100,160,160),'closed_ellipse')
    fill=shape('fill',(106,106,154,154),'uniform_fill')
    adjacent=shape('adjacent',(160,100,220,160))
    out,_=select(scene(outer,fill,ellipse,adjacent))
    assert {s.id for s in out.shapes}=={'outer','ellipse','adjacent'}


def test_no_transitive_duplicate_chain():
    a,b,c=[shape(str(i),(40+d,40,140+d,140)) for i,d in enumerate((0,8,16))]
    assert duplicate(a,b) and duplicate(b,c) and not duplicate(a,c)
    out,_=select(scene(a,b,c))
    assert len(out.shapes)==2


def test_blank_standalone_box_kept():
    rgb=np.full((400,400,3),255,np.uint8)
    cv2.rectangle(rgb,(30,30),(180,180),(0,0,0),2)
    s=scene(shape('empty',(30,30,180,180)))
    out,_=select(s,rgb,'evidence_select')
    assert out==s


def test_shared_border_empty_gap_face_removed():
    rgb=np.full((400,400,3),255,np.uint8)
    cv2.rectangle(rgb,(20,20),(380,120),(0,0,0),2)
    cv2.rectangle(rgb,(20,180),(380,280),(0,0,0),2)
    cv2.line(rgb,(100,120),(100,180),(0,0,0),2)
    cv2.line(rgb,(180,120),(180,180),(0,0,0),2)
    s=scene(shape('top',(20,20,380,120)),shape('bottom',(20,180,380,280)),shape('gap',(100,120,180,180)))
    out,audit=select(s,rgb,'evidence_select')
    assert 'gap' not in {s.id for s in out.shapes}
    assert audit['removed']['gap']['reason']=='blank_shared_border_face'
    assert len(out.shapes)==2


def test_discontinuous_envelope_rejected():
    rgb=np.full((400,400,3),255,np.uint8)
    cv2.rectangle(rgb,(20,20),(380,120),(0,0,0),2)
    cv2.rectangle(rgb,(20,230),(380,330),(0,0,0),2)
    out,audit=select(scene(shape('outer',(20,20,380,330))),rgb,'evidence_select')
    assert not out.shapes
    assert audit['removed']['outer']['reason']=='discontinuous_envelope'


def test_scatter_rejection_is_local_not_whole_image():
    rgb=np.full((400,400,3),255,np.uint8)
    cv2.rectangle(rgb,(10,10),(190,190),(0,0,0),2)
    cv2.rectangle(rgb,(210,10),(390,190),(0,0,0),2)
    for y in range(30,180,20):
        for x in range(30,180,20): cv2.circle(rgb,(x,y),2,(255,0,0),-1)
    out,audit=select(scene(shape('chart',(10,10,190,190)),shape('node',(210,10,390,190))),rgb,'evidence_select')
    assert [s.id for s in out.shapes]==['node']
    assert audit['removed']['chart']['reason']=='scatter_region'


def test_no_label_or_id_semantics_and_retained_primitives_unchanged():
    a=shape('a',(20,20,120,120),'closed_ellipse')
    b=shape('b',(25,25,115,115),'uniform_fill')
    s=scene(a,b)
    first,_=select(s)
    second,_=select(replace(s,shapes=tuple(replace(o,id=o.id+'renamed',label='unrelated') for o in s.shapes)))
    assert first.shapes==(a,)
    assert [o.bbox for o in first.shapes]==[o.bbox for o in second.shapes]


def test_dropped_owner_connector_not_rebound():
    a=shape('a',(20,20,180,180))
    b=shape('b',(220,20,380,180))
    edge=EmitConnectorPrimitive('edge',ConnectorKind.ARROW,1,'a',PortOwnerKind.NODE,'b',PortOwnerKind.NODE,
        'a:port','b:port',path_points=(Point(180,100),Point(220,100)))
    # No observed borders: both envelopes fail. No inferred replacement or dangling edge.
    out,audit=select(scene(a,b,connectors=(edge,)),arm='evidence_select')
    assert out.connectors==()
    assert audit['dropped_connector_ids']==['edge']
