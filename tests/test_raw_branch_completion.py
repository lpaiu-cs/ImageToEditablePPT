"""Unmerged physical source support, not increased morphological gap tolerance."""
import cv2
import numpy as np
import pytest
from image_to_editable_ppt.region.tracing import trace_scene
from image_to_editable_ppt.research.raw_branch_completion import add_raw_branches
from image_to_editable_ppt.v3.core.enums import NodeKind,PortOwnerKind
from image_to_editable_ppt.v3.core.types import BBox,ImageSize
from image_to_editable_ppt.v3.emit.models import EmitScene,EmitShapePrimitive


@pytest.mark.parametrize('defect',['none','gap','curve','crossing','gray_crossing','owner','parallel'])
def test_source_component_guard_and_no_duplicate(defect):
    rgb=np.full((360,600,3),255,np.uint8)
    boxes=[(20,120,100,240),(490,120,580,240)]
    if defect=='owner':boxes.append((270,160,330,200))
    for box in boxes:cv2.rectangle(rgb,box[:2],box[2:],(0,0,0),2)
    if defect=='gray_crossing':cv2.line(rgb,(290,130),(290,230),(120,120,120),2)
    if defect=='curve':cv2.polylines(rgb,[np.array([(100,180),(260,120),(490,180)])],False,(0,0,0),2)
    else:cv2.line(rgb,(100,180),(490,180),(0,0,0),2)
    if defect=='gap':rgb[176:185,270:280]=255
    if defect=='crossing':cv2.line(rgb,(290,130),(290,230),(0,0,0),2)
    if defect=='parallel':cv2.line(rgb,(100,200),(490,200),(0,0,0),2)
    scene=EmitScene(ImageSize(600,360),shapes=tuple(EmitShapePrimitive(str(i),PortOwnerKind.NODE,
        NodeKind.BOX,BBox(*b),1.) for i,b in enumerate(boxes)))
    output,audit=add_raw_branches(scene,rgb)
    if defect in ('none','owner'):
        assert len(output.connectors)==(1 if defect=='none' else 2)
        assert not any(e.arrowhead_start or e.arrowhead_end for e in output.connectors)
        if defect=='owner':assert all({e.source_owner_id,e.target_owner_id}!={'0','1'} for e in output.connectors)
        repeated,_=add_raw_branches(output,rgb)
        assert repeated==output
    else:assert not output.connectors
    assert output.shapes==scene.shapes
    default=trace_scene(scene,rgb,(0,0,1,1))
    explicit=trace_scene(scene,rgb,(0,0,1,1),raw_components=False)
    assert default[:2]==explicit[:2] and np.array_equal(default[2],explicit[2])


def test_invalid_original_coordinate_input():
    with pytest.raises(ValueError):
        add_raw_branches(EmitScene(ImageSize(20,20)),np.zeros((30,20,3),np.uint8))


def test_closing_merges_real_separate_branches():
    rgb=np.full((360,600,3),255,np.uint8)
    boxes=[(20,120,100,240),(490,40,580,110),(490,260,580,330)]
    for box in boxes:cv2.rectangle(rgb,box[:2],box[2:],(0,0,0),2)
    for end in ((490,75),(490,295)):cv2.line(rgb,(100,180),end,(0,0,0),1)
    scene=EmitScene(ImageSize(600,360),shapes=tuple(EmitShapePrimitive(str(i),PortOwnerKind.NODE,
        NodeKind.BOX,BBox(*b),1.) for i,b in enumerate(boxes)))
    old,_,_=trace_scene(scene,rgb,(0,0,1,1))
    output,audit=add_raw_branches(old,rgb)
    assert not old.connectors
    assert {frozenset((e.source_owner_id,e.target_owner_id)) for e in output.connectors}=={frozenset(('0','1')),frozenset(('0','2'))}
    assert audit['added']==2
