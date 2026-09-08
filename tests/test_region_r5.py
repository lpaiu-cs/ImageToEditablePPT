"""Independent source-pixel counterexamples for R5, not target-image fixtures."""
from dataclasses import replace
import cv2
import numpy as np
import pytest
from image_to_editable_ppt.ml.visual_geometry import GeometryCandidate
from image_to_editable_ppt.region.proposals import fill_boundary_support,detect_region_geometry
from image_to_editable_ppt.region.tracing import direction,shortest,straight_fanout
from image_to_editable_ppt.region.text import recover_labels
from image_to_editable_ppt.v3.core.enums import NodeKind,PortOwnerKind
from image_to_editable_ppt.v3.core.types import BBox,ImageSize
from image_to_editable_ppt.v3.emit.models import EmitScene,EmitShapePrimitive


def owner(name,bounds):
    return EmitShapePrimitive(name,PortOwnerKind.NODE,NodeKind.BOX,BBox(*bounds),1.)


def test_background_fragment_has_no_closed_fill_boundary():
    rgb=np.full((220,360,3),235,np.uint8)
    c=GeometryCandidate((60,50,240,170),'uniform_fill',.9)
    assert min(fill_boundary_support(rgb,c))==0
    rgb[50:170,60:240]=(190,225,160)
    assert min(fill_boundary_support(rgb,c))==1
    rgb[50:170,240:300]=(190,225,160)  # no right boundary at candidate edge
    assert min(fill_boundary_support(rgb,c))==0


def test_clipped_fill_does_not_supply_four_sides():
    rgb=np.full((150,240,3),255,np.uint8); rgb[0:100,20:190]=180
    assert min(fill_boundary_support(rgb,GeometryCandidate((20,0,190,100),'uniform_fill',1)))==0


def test_inset_quantized_fill_uses_observed_outer_border():
    rgb=np.full((180,340,3),255,np.uint8)
    cv2.rectangle(rgb,(30,35),(310,145),(210,220,230),-1)
    cv2.rectangle(rgb,(30,35),(310,145),(170,190,210),3)
    candidate=GeometryCandidate((37,42,304,139),'uniform_fill',.9)
    assert min(fill_boundary_support(rgb,candidate))>=.70
    rgb[30:150,305:340]=(210,220,230)
    assert min(fill_boundary_support(rgb,candidate))<.70


def test_narrow_tall_outline_and_square_fill_tie_break():
    rgb=np.full((260,1000,3),255,np.uint8)
    cv2.rectangle(rgb,(20,25),(50,230),(0,0,0),2)
    cv2.rectangle(rgb,(300,70),(500,180),(170,215,160),-1)
    cv2.rectangle(rgb,(300,70),(500,180),(0,0,0),2)
    result=detect_region_geometry(rgb)
    assert len(result.nodes)==2
    assert all(c.source=='closed_outline' for c in result.nodes)


def test_fill_only_panel_cannot_suppress_or_own_child_nodes():
    rgb=np.full((320,600,3),255,np.uint8)
    rgb[30:290,25:575]=235
    for x in (70,240,410):
        cv2.rectangle(rgb,(x,100),(x+100,220),(255,255,255),-1)
        cv2.rectangle(rgb,(x,100),(x+100,220),(0,0,0),2)
    result=detect_region_geometry(rgb)
    assert len(result.nodes)==3 and not result.containers
    assert all(c.area<15000 for c in result.nodes)


@pytest.mark.parametrize('reverse',[False,True])
def test_long_elbow_direction_ignores_corner(reverse):
    mask=np.zeros((260,640),np.uint8)
    a=(35,20); corner=(35,215); b=(605,215)
    if reverse:
        cv2.line(mask,b,corner,1,2); cv2.arrowedLine(mask,corner,a,1,2,tipLength=.08)
    else:
        cv2.line(mask,a,corner,1,2); cv2.arrowedLine(mask,corner,b,1,2,tipLength=.025)
    path=shortest(mask,a,b)
    assert direction(mask,path)[0]==(-1 if reverse else 1)


def test_plain_long_elbow_is_not_an_arrow():
    mask=np.zeros((260,640),np.uint8)
    cv2.line(mask,(35,20),(35,215),1,2); cv2.line(mask,(35,215),(605,215),1,2)
    assert direction(mask,shortest(mask,(35,20),(605,215)))[0]==0


@pytest.mark.parametrize('arrows',[False,True])
def test_straight_fanout_requires_leaf_heads(arrows):
    mask=np.zeros((320,440),np.uint8)
    root=(20,160); ends=((410,40),(410,280))
    for p in ends:
        if arrows: cv2.arrowedLine(mask,root,p,1,2,tipLength=.035)
        else: cv2.line(mask,root,p,1,2)
    contacts=[(owner('hub',(0,140,15,180)),root),
        (owner('top',(415,20,439,60)),ends[0]),(owner('bottom',(415,260,439,300)),ends[1])]
    result=straight_fanout(mask,contacts,2)
    assert bool(result)==arrows
    if result: assert [(a.id,b.id) for a,b,_,_ in result]==[('hub','top'),('hub','bottom')]


def test_ocr_padding_fallback_keeps_two_scale_agreement(monkeypatch):
    from image_to_editable_ppt.region import text
    scene=EmitScene(ImageSize(100,60),shapes=(owner('a',(5,5,95,55)),))
    calls=[]
    def recognize(engine,crop):
        calls.append(crop.shape)
        return (None,dict(reason='overlapping_snippets')) if len(calls)==1 else ('Value 2',dict(reason='two_scale_agreement'))
    monkeypatch.setattr(text,'_load_engine',lambda:object())
    monkeypatch.setattr(text,'recognize_consistent',recognize)
    output,audit=recover_labels(scene,np.full((60,100,3),230,np.uint8))
    assert output.shapes[0].label=='Value 2'
    assert calls[1][:2]==(calls[0][0]+32,calls[0][1]+32)
    assert audit['a']['transform']=='interior_color_border_16'
