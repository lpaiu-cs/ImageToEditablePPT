from dataclasses import replace

import cv2
import numpy as np
import pytest

from image_to_editable_ppt.research.box_terminals import observe_terminal,recover_box_terminals
from image_to_editable_ppt.v3.core.enums import NodeKind,PortOwnerKind,ConnectorKind
from image_to_editable_ppt.v3.core.types import BBox,ImageSize,Point
from image_to_editable_ppt.v3.emit.models import EmitScene,EmitShapePrimitive,EmitConnectorPrimitive


def fixture(mode='arrow',ellipse=False):
    rgb=np.full((360,640,3),255,np.uint8)
    boxes=[[120,155,170,205],[420,155,470,205]]
    for x0,y0,x1,y1 in boxes:
        if ellipse:cv2.ellipse(rgb,((x0+x1)//2,180),(25,25),0,0,360,(0,0,0),2)
        else:cv2.rectangle(rgb,(x0,y0),(x1,y1),(0,0,0),2)
    cv2.line(rgb,(170,180),(420,180),(0,0,0),2)
    if mode in ('arrow','double','branch','crossing','detached_opposite'):
        cv2.fillConvexPoly(rgb,np.array([[420,180],[409,174],[409,186]]),(0,0,0))
    if mode=='double':cv2.fillConvexPoly(rgb,np.array([[170,180],[181,174],[181,186]]),(0,0,0))
    if mode=='branch':cv2.line(rgb,(330,180),(345,155),(0,0,0),2)
    if mode=='crossing':cv2.line(rgb,(300,145),(300,215),(0,0,0),2)
    if mode=='detached_opposite':
        cv2.fillConvexPoly(rgb,np.array([[174,180],[184,174],[184,186]]),(0,0,0))
        rgb[172:189,185:189]=255
    return rgb,[[170,180],[420,180]],boxes


@pytest.mark.parametrize('ellipse',[False,True])
def test_original_visible_tip_direction_and_pixels(ellipse):
    rgb,points,boxes=fixture(ellipse=ellipse);before=rgb.copy()
    direction,audit=observe_terminal(rgb,points,boxes)
    assert direction==(False,True),audit
    assert np.array_equal(rgb,before)
    direction,audit=observe_terminal(rgb,list(reversed(points)),list(reversed(boxes)))
    assert direction==(True,False),audit


@pytest.mark.parametrize('mode',['plain','double','branch','crossing','detached_opposite'])
def test_ambiguous_direction_is_not_invented(mode):
    rgb,points,boxes=fixture(mode)
    assert observe_terminal(rgb,points,boxes)[0] is None


@pytest.mark.parametrize('mode',['dtype','size','nan','outside','empty'])
def test_invalid_geometry_rejected(mode):
    rgb,points,boxes=fixture()
    if mode=='dtype':rgb=rgb.astype(float)
    if mode=='size':points.append([0,0])
    if mode=='nan':points[0][0]=float('nan')
    if mode=='outside':boxes[0][0]=-1
    if mode=='empty':rgb=rgb[:0]
    with pytest.raises(ValueError):observe_terminal(rgb,points,boxes)


def test_only_direction_flags_of_b_verified_edge_change():
    rgb,points,boxes=fixture()
    owners=tuple(EmitShapePrimitive(str(i),PortOwnerKind.NODE,NodeKind.BOX,BBox(*box),.9) for i,box in enumerate(boxes))
    edge=EmitConnectorPrimitive('e',ConnectorKind.LINE,.9,'0',PortOwnerKind.NODE,'1',PortOwnerKind.NODE,'p0','p1',
        path_points=tuple(Point(*p) for p in points))
    scene=EmitScene(ImageSize(640,360),shapes=owners,connectors=(edge,))
    unchanged,_=recover_box_terminals(scene,rgb,{'connectors':{}})
    assert unchanged==scene
    changed,_=recover_box_terminals(scene,rgb,{'connectors':{'e':{'decision':'refined'}}})
    assert changed.connectors[0].arrowhead_end
    assert replace(changed.connectors[0],arrowhead_end=False)==edge
    assert replace(changed,connectors=scene.connectors)==scene
    conflicting=replace(scene,connectors=(replace(edge,arrowhead_start=True),))
    assert recover_box_terminals(conflicting,rgb,{'connectors':{'e':{'decision':'refined'}}})[0]==conflicting
