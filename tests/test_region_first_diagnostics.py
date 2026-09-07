from dataclasses import replace
import hashlib
import json

import cv2
import numpy as np
from PIL import Image
import pytest

from image_to_editable_ppt.research.region_first import (
    evaluate,inspect_pptx,manual_box_inputs,match_objects,recover_scene,scene_for_pptx,validate_sample,
)
from image_to_editable_ppt.v3.core.enums import NodeKind,PortOwnerKind
from image_to_editable_ppt.v3.core.types import BBox,ImageSize
from image_to_editable_ppt.v3.emit.models import EmitScene,EmitShapePrimitive
from image_to_editable_ppt.v3.emit import write_pptx


def sample():
    return dict(size=[400,200],roi=[0,0,1,1],excluded=[],objects=[
        dict(id="a",bbox=[.05,.2,.3,.8],role="node",shape="box",label="Secret A"),
        dict(id="b",bbox=[.65,.2,.95,.8],role="node",shape="box",label="Secret B")],edges=[["a","b"]])


def source():
    rgb=np.full((200,400,3),255,dtype=np.uint8)
    cv2.rectangle(rgb,(20,40),(120,160),(0,0,0),2)
    cv2.rectangle(rgb,(260,40),(380,160),(0,0,0),2)
    cv2.arrowedLine(rgb,(120,100),(260,100),(0,0,0),3,tipLength=.15)
    return Image.fromarray(rgb)


def test_oracle_inputs_do_not_contain_expected_labels_or_edges():
    payload=manual_box_inputs(sample())
    assert all(set(o)=={"id","bbox","role","shape"} for o in payload)
    assert "Secret" not in json.dumps(payload)


def test_oracle_shapes_do_not_copy_labels_and_still_require_visible_edges():
    data=sample()
    blank=Image.new("RGB",(400,200),"white")
    result=recover_scene(blank,roi=data["roi"],manual_boxes=manual_box_inputs(data),ocr=False)
    assert len(result.shapes)==2
    assert all(s.label is None for s in result.shapes)
    assert not result.connectors
    metrics=evaluate(result,data)
    assert metrics["matched_objects"]==2
    assert metrics["matched_directed_edges"]==0
    assert metrics["missing_labels"]==["a","b"]


def test_native_source_control_recovers_visible_direction_and_bindings(tmp_path):
    data=sample()
    scene=recover_scene(source(),roi=data["roi"],manual_boxes=manual_box_inputs(data),ocr=False)
    assert len(scene.connectors)==1
    assert evaluate(scene,data)["matched_directed_edges"]==1
    path=tmp_path/"result.pptx"
    write_pptx(scene,path)
    native=inspect_pptx(path)
    assert native["raster_images"]==0
    assert native["connectors"]==1
    assert native["bound_endpoints"]==2


def test_roi_coordinates_return_to_source_space():
    scene=recover_scene(source(),roi=[.01,.1,.99,.9],ocr=False)
    assert len(scene.shapes)==2
    assert evaluate(scene,sample())["matched_objects"]==2
    assert len(scene.connectors)==1
    assert scene.connectors[0].path_points[0].x>100


def test_missing_shapes_cannot_improve_label_score():
    empty=EmitScene(image_size=ImageSize(400,200))
    m=evaluate(empty,sample())
    assert m["missing_labels"]==["a","b"]


def test_matching_does_not_count_duplicate_shapes_twice():
    one=EmitShapePrimitive("x",PortOwnerKind.NODE,NodeKind.BOX,BBox(20,40,120,160),1)
    matched=match_objects([one,replace(one,id="y")],sample()["objects"],(400,200))
    assert len(matched)==1


def test_partial_annotation_does_not_call_unassessed_output_false_positive():
    data=sample()
    data["roi"]=[0,0,.5,1]
    data["objects"]=data["objects"][:1]
    data["edges"]=[]
    outside=EmitShapePrimitive("outside",PortOwnerKind.NODE,NodeKind.BOX,BBox(300,30,380,100),1)
    m=evaluate(EmitScene(image_size=ImageSize(400,200),shapes=(outside,)),data)
    assert m["unmatched_local_objects"]==[]
    assert m["unassessed_outside_roi"]==1
    data["excluded"]=[[.6,0,1,1]]
    assert evaluate(EmitScene(image_size=ImageSize(400,200),shapes=(outside,)),data)["excluded_region_hits"]==["outside"]


def test_physical_slide_scaling_does_not_change_source_scene():
    shape=EmitShapePrimitive("a",PortOwnerKind.NODE,NodeKind.BOX,BBox(100,100,300,300),1)
    original=EmitScene(image_size=ImageSize(6000,2000),shapes=(shape,))
    scaled=scene_for_pptx(original)
    assert scaled.image_size.width==3200
    assert scaled.shapes[0].bbox.x0==pytest.approx(100*3200/6000)
    assert original.shapes[0].bbox.x0==100


def test_source_hash_and_holdout_boundaries(tmp_path):
    path=tmp_path/"source.png"
    source().save(path)
    data={**sample(),"path":"source.png","sha256":hashlib.sha256(path.read_bytes()).hexdigest()}
    assert validate_sample(data,tmp_path).size==(400,200)
    with pytest.raises(ValueError,match="hash"):
        validate_sample({**data,"sha256":"bad"},tmp_path)
    with pytest.raises(ValueError,match="holdout"):
        validate_sample({**data,"path":"holdout/source.png"},tmp_path)


def test_roles_are_measured_separately_from_box_recall():
    from image_to_editable_ppt.v3.core.enums import ContainerKind
    shape=EmitShapePrimitive("x",PortOwnerKind.CONTAINER,ContainerKind.FLOW_CLUSTER,BBox(20,40,120,160),1)
    m=evaluate(EmitScene(image_size=ImageSize(400,200),shapes=(shape,)),sample())
    assert m["matched_objects"]==1
    assert m["role_errors"]==["a"]
