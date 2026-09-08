import cv2
import numpy as np
import pytest
from image_to_editable_ppt.research.nested_owner_evidence import exclusion_regions,panel_children,trace_nested
from image_to_editable_ppt.research.source_evidence_pipeline import detector_scene
from image_to_editable_ppt.research.closed_owner_regions import owner_region


def scene_for(boxes):
    rgb=np.full((360,640,3),255,np.uint8)
    scene=detector_scene(rgb,[dict(id=f'b{i}',role='node',semantic_kind='box',bbox_xyxy=b,confidence=.9) for i,b in enumerate(boxes)])
    return rgb,scene


@pytest.mark.parametrize('boxes,expected',[
    ([[20,20,600,330],[60,100,200,200],[300,100,450,200]],{'b0':['b1','b2']}),
    ([[20,20,600,330],[60,100,200,200]],{}),
    ([[20,20,600,330],[60,100,200,200],[61,101,199,199]],{}),
    ([[20,20,600,330],[0,100,200,200],[300,100,450,200]],{}),
])
def test_panel_mask_scope_requires_two_separate_strict_children(boxes,expected):
    _,scene=scene_for(boxes);assert panel_children(scene)==expected


def test_verified_dark_child_reserves_its_actual_contour():
    rgb=np.full((360,640,3),255,np.uint8)
    def region(box):
        a,b,c,d=box
        return dict(bbox=box,contour=np.array([[[a,b]],[[c-1,b]],[[c-1,d-1]],[[a,d-1]]],np.int32))
    parent=region([20,20,500,330]);child=region([80,100,200,200])
    pool=exclusion_regions([parent],[parent,child,child])
    assert len(pool)==2
    own,excluded,_,audit=owner_region(rgb,parent,pool)
    assert excluded[150,150] and not own[150,150]
    assert audit['children']==[child['bbox']]


def test_parent_no_longer_erases_real_internal_connector():
    boxes=[[20,20,600,330],[60,100,200,200],[350,100,500,200]]
    rgb,scene=scene_for(boxes)
    for a,b,c,d in boxes:cv2.rectangle(rgb,(a,b),(c,d),(0,0,0),2)
    cv2.arrowedLine(rgb,(201,150),(349,150),(0,0,0),2,tipLength=.10)
    restored,trace,_,_,audit=trace_nested(scene,rgb)
    assert restored.shapes==scene.shapes
    assert audit['border_only_parents']=={'b0':['b1','b2']}
    assert len(restored.connectors)==1
    assert {restored.connectors[0].source_owner_id,restored.connectors[0].target_owner_id}=={'b1','b2'}


def test_no_source_connector_is_not_invented_by_containment():
    boxes=[[20,20,600,330],[60,100,200,200],[350,100,500,200]]
    rgb,scene=scene_for(boxes)
    for a,b,c,d in boxes:cv2.rectangle(rgb,(a,b),(c,d),(0,0,0),2)
    restored,*_=trace_nested(scene,rgb)
    assert not restored.connectors
