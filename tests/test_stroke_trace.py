from dataclasses import replace
import cv2
import numpy as np
from image_to_editable_ppt.research.stroke_trace import trace_scene
from image_to_editable_ppt.v3.core.enums import NodeKind,PortOwnerKind
from image_to_editable_ppt.v3.core.types import BBox,ImageSize
from image_to_editable_ppt.v3.emit.models import EmitShapePrimitive,EmitScene


def node(name,box):
    return EmitShapePrimitive(name,PortOwnerKind.NODE,NodeKind.BOX,BBox(*box),1,label='Frozen',source='visual_geometry:closed_outline')


def fixture():
    rgb=np.full((300,400,3),255,np.uint8)
    a=node('a',(20,80,100,140)); b=node('b',(300,80,380,140))
    for s in (a,b): cv2.rectangle(rgb,(int(s.bbox.x0),int(s.bbox.y0)),(int(s.bbox.x1),int(s.bbox.y1)),(0,0,0),2)
    return rgb,EmitScene(image_size=ImageSize(400,300),shapes=(a,b))


def test_blank_no_invented_path():
    rgb,s=fixture()
    out,_,_=trace_scene(s,rgb,(0,0,1,1))
    assert not out.connectors


def test_observed_arrow_and_undirected_line():
    for arrow in (False,True):
        rgb,s=fixture()
        if arrow: cv2.arrowedLine(rgb,(100,110),(300,110),(0,0,0),2,tipLength=.10)
        else: cv2.line(rgb,(100,110),(300,110),(0,0,0),2)
        out,_,_=trace_scene(s,rgb,(0,0,1,1))
        assert len(out.connectors)==1
        assert out.connectors[0].arrowhead_end==arrow
        assert out.shapes==s.shapes


def test_bent_source_path_is_not_replaced_by_chord():
    rgb,s=fixture()
    s=replace(s,shapes=(s.shapes[0],node('b',(260,210,360,280))))
    rgb[:]=255
    cv2.line(rgb,(100,110),(310,110),(0,0,0),2)
    cv2.arrowedLine(rgb,(310,110),(310,210),(0,0,0),2,tipLength=.15)
    out,_,_=trace_scene(s,rgb,(0,0,1,1))
    assert len(out.connectors)==1
    assert len(out.connectors[0].path_points)>=3
    assert out.connectors[0].arrowhead_end


def test_ambiguous_component_with_three_owners_is_omitted():
    rgb,s=fixture()
    third=node('third',(160,220,240,280))
    s=replace(s,shapes=s.shapes+(third,))
    cv2.line(rgb,(100,110),(300,110),(0,0,0),2)
    cv2.line(rgb,(200,110),(200,220),(0,0,0),2)
    out,a,_=trace_scene(s,rgb,(0,0,1,1))
    assert not out.connectors
    assert any(r.get('rejected')=='ambiguous_multi_owner' for r in a['components'])


def test_container_crossing_preserves_source_connection():
    rgb,s=fixture()
    container=replace(node('panel',(170,20,230,270)),owner_kind=PortOwnerKind.CONTAINER)
    s=replace(s,shapes=s.shapes+(container,))
    cv2.rectangle(rgb,(170,20),(230,270),(0,0,0),2)
    cv2.arrowedLine(rgb,(100,110),(300,110),(0,0,0),2,tipLength=.10)
    out,_,_=trace_scene(s,rgb,(0,0,1,1))
    assert len(out.connectors)==1
    assert out.connectors[0].source_owner_id=='a'
    assert out.connectors[0].target_owner_id=='b'
