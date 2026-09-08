"""Color/polarity transfer contracts independent of the natural tuning sources."""
import cv2
import numpy as np
import pytest
from image_to_editable_ppt.region.strokes import stroke_mask
from image_to_editable_ppt.region.tracing import trace_scene
from image_to_editable_ppt.v3.core.enums import NodeKind,PortOwnerKind
from image_to_editable_ppt.v3.core.types import BBox,ImageSize
from image_to_editable_ppt.v3.emit.models import EmitScene,EmitShapePrimitive


def chain(color,background,thickness=2,vertical=False,connected=True):
    rgb=np.full((300,720,3),background,np.uint8)
    shapes=[]
    for i,x in enumerate((30,290,550)):
        cv2.rectangle(rgb,(x,100),(x+140,200),color,thickness)
        shapes.append(EmitShapePrimitive(str(i),PortOwnerKind.NODE,NodeKind.BOX,BBox(x,100,x+140,200),1.))
    if connected:
        for x in (170,430): cv2.arrowedLine(rgb,(x,150),(x+120,150),color,thickness,tipLength=.15)
    if vertical:
        rgb=cv2.rotate(rgb,cv2.ROTATE_90_CLOCKWISE)
        from dataclasses import replace
        shapes=[replace(s,bbox=BBox(300-s.bbox.y1,s.bbox.x0,300-s.bbox.y0,s.bbox.x1)) for s in shapes]
    return rgb,EmitScene(ImageSize(rgb.shape[1],rgb.shape[0]),shapes=tuple(shapes))


@pytest.mark.parametrize('color,background',[
    ((0,0,0),(255,255,255)),((50,130,240),(255,255,255)),
    ((220,60,190),(255,255,255)),((20,180,120),(255,255,255)),
    ((255,255,255),(0,0,0)),((255,230,60),(15,15,15))])
@pytest.mark.parametrize('vertical',[False,True])
def test_owned_strokes_transfer_hue_and_polarity(color,background,vertical):
    rgb,scene=chain(color,background,vertical=vertical)
    out,_,_=trace_scene(scene,rgb,(0,0,1,1))
    assert [(c.source_owner_id,c.target_owner_id) for c in out.connectors]==[('0','1'),('1','2')]
    assert all(c.arrowhead_end for c in out.connectors)


@pytest.mark.parametrize('background',[0,70,180,255])
def test_uniform_background_is_not_ink(background):
    assert not stroke_mask(np.full((160,220,3),background,np.uint8)).any()


@pytest.mark.parametrize('color,background',[((50,130,240),(255,255,255)),((255,255,255),(0,0,0))])
def test_unconnected_owners_do_not_gain_links(color,background):
    rgb,scene=chain(color,background,connected=False)
    assert not trace_scene(scene,rgb,(0,0,1,1))[0].connectors


@pytest.mark.parametrize('color,background',[
    ((0,0,0),(255,255,255)),((50,130,240),(255,255,255)),((255,255,255),(0,0,0))])
def test_end_to_end_owner_detection_and_trace(color,background):
    from image_to_editable_ppt.region.geometry import detect_scene
    rgb,_=chain(color,background)
    scene=detect_scene(rgb,(0,0,1,1))
    assert len(scene.shapes)==3 and all(s.owner_kind is PortOwnerKind.NODE for s in scene.shapes)
    out,_,_=trace_scene(scene,rgb,(0,0,1,1))
    assert len(out.connectors)==2 and all(c.arrowhead_end for c in out.connectors)


@pytest.mark.parametrize('thickness',[2,6,12])
@pytest.mark.parametrize('arrow',[False,True])
def test_shaft_scaled_direction_has_plain_line_counterexamples(thickness,arrow):
    from image_to_editable_ppt.region.tracing import shortest,direction
    mask=np.zeros((160,400),np.uint8)
    if arrow: cv2.arrowedLine(mask,(30,80),(370,80),1,thickness,tipLength=.12)
    else: cv2.line(mask,(30,80),(370,80),1,thickness)
    assert direction(mask,shortest(mask,(30,80),(370,80)))[0]==int(arrow)


def test_colored_closed_children_do_not_merge_into_parent_fill():
    from image_to_editable_ppt.region.proposals import detect_region_geometry
    rgb=np.full((350,600,3),255,np.uint8)
    cv2.rectangle(rgb,(30,30),(570,320),(220,235,220),-1)
    cv2.rectangle(rgb,(30,30),(570,320),(110,175,90),2)
    for x in (70,250,430):
        cv2.rectangle(rgb,(x,100),(x+110,240),(255,245,205),-1)
        cv2.rectangle(rgb,(x,100),(x+110,240),(220,175,80),2)
    result=detect_region_geometry(rgb)
    assert len(result.containers)==1 and len(result.nodes)==3


def test_uniform_dark_fill_is_not_a_header_divider():
    from image_to_editable_ppt.region.proposals import detect_region_geometry
    rgb=np.zeros((260,400,3),np.uint8)
    cv2.rectangle(rgb,(60,50),(340,210),(255,220,150),-1)
    result=detect_region_geometry(rgb)
    assert len(result.nodes)==1 and not result.containers


def test_center_overlap_does_not_establish_containment():
    from image_to_editable_ppt.region.proposals import nested
    from image_to_editable_ppt.ml.visual_geometry import GeometryCandidate
    parent=GeometryCandidate((20,20,200,200),'closed_outline',1.)
    crossing=GeometryCandidate((170,100,220,140),'closed_outline',1.)
    assert not nested(parent,[crossing])
