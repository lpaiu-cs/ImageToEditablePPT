from dataclasses import replace

import numpy as np
from PIL import Image,ImageDraw
import pytest

from image_to_editable_ppt.research.box_centerline_b_v1 import refine_box_centerlines
from image_to_editable_ppt.v3.core.enums import NodeKind,PortOwnerKind,ConnectorKind
from image_to_editable_ppt.v3.core.types import BBox,ImageSize,Point
from image_to_editable_ppt.v3.emit.models import EmitScene,EmitShapePrimitive,EmitConnectorPrimitive


def fixture(angle=0,scale=1,mode='line',rounded=False,aa=1):
    r=scale*aa;size=round(360*r);im=Image.new('RGB',(size,size),'white');draw=ImageDraw.Draw(im)
    theta=np.deg2rad(angle);u=np.array([np.cos(theta),np.sin(theta)]);v=np.array([-u[1],u[0]])
    def point(x,y=0):return np.array([180,180])+x*u+y*v
    def line(points):draw.line([tuple(point(x,y)*r) for x,y in points],fill='black',width=max(1,round(2*r)))
    inward=12/max(abs(u));lo,hi=-100+inward,100-inward
    if mode=='gap':
        line([(lo,0),(-12,0)]);line([(12,0),(hi,0)])
    elif mode=='elbow':line([(lo,0),(0,18),(hi,0)])
    elif mode=='curve':
        line([(x,14*np.sin(np.pi*(x-lo)/(hi-lo))) for x in np.linspace(lo,hi,80)])
    elif mode=='parallel':
        for offset in [-4,4]:line([(lo,offset),(hi,offset)])
    else:line([(lo,0),(hi,0)])
    if mode=='crossing':line([(0,-30),(0,30)])
    if mode=='branch':line([(25,0),(40,25)])
    if mode=='terminal_branch':line([(hi-9,0),(hi-9,25)])
    owners=[]
    for i,t in enumerate([-100,100]):
        c=point(t);box=[*(c-12),*(c+12)]
        coords=tuple(x*r for x in box)
        if rounded:draw.rounded_rectangle(coords,radius=3*r,outline='black',width=max(1,round(2*r)))
        else:draw.rectangle(coords,outline='black',width=max(1,round(2*r)))
        owners.append(EmitShapePrimitive(str(i),PortOwnerKind.NODE,NodeKind.ROUNDED_BOX if rounded else NodeKind.BOX,BBox(*(x*scale for x in box)),.9))
    if mode=='third_owner':
        owners.append(EmitShapePrimitive('third',PortOwnerKind.NODE,NodeKind.BOX,BBox(174*scale,174*scale,186*scale,186*scale),.9))
    path=tuple(Point(*(point(x,y)*scale)) for x,y in [(lo,0),(-40,1),(40,-1),(hi,0)])
    edge=EmitConnectorPrimitive('edge',ConnectorKind.LINE,.8,'0',PortOwnerKind.NODE,'1',PortOwnerKind.NODE,'p0','p1',
        path_points=path,source='r3_stroke_trace',provenance=('r3:continuous_component','r3:bounded_mask_gap_repair'))
    if aa!=1:im=im.resize((round(360*scale),)*2,Image.Resampling.LANCZOS)
    return EmitScene(ImageSize(round(360*scale),round(360*scale)),shapes=tuple(owners),connectors=(edge,)),np.array(im)


@pytest.mark.parametrize('angle',[0,30,60,90,135])
@pytest.mark.parametrize('scale',[.75,1,1.5])
@pytest.mark.parametrize('rounded',[False,True])
@pytest.mark.parametrize('aa',[1,4])
def test_supported_source_preserves_identity_and_direction(angle,scale,rounded,aa):
    scene,rgb=fixture(angle,scale,rounded=rounded,aa=aa)
    old=scene.connectors[0]
    # Exercise both flags without interpreting them as RGB-derived directions.
    scene=replace(scene,connectors=(replace(old,arrowhead_start=True,arrowhead_end=True),))
    before=rgb.copy();result,audit=refine_box_centerlines(scene,rgb)
    assert audit['connectors']['edge']['decision']=='refined',audit
    assert len(result.connectors[0].path_points)==2
    assert replace(result.connectors[0],path_points=scene.connectors[0].path_points)==scene.connectors[0]
    assert replace(result,connectors=scene.connectors)==scene
    assert np.array_equal(rgb,before)


@pytest.mark.parametrize('mode',['gap','elbow','curve','parallel','crossing','branch','terminal_branch','third_owner'])
@pytest.mark.parametrize('angle',[0,30,90])
@pytest.mark.parametrize('scale',[.75,1.5])
def test_unsupported_original_ink_abstains(mode,angle,scale):
    scene,rgb=fixture(angle,scale,mode=mode)
    result,audit=refine_box_centerlines(scene,rgb)
    assert result==scene,audit
    assert audit['connectors']['edge']['decision']=='unchanged'


@pytest.mark.parametrize('mode',['foreign_source','anchor','duplicate','owner_miss','endpoint_change','path_elbow'])
def test_scope_and_attachment_abstain(mode):
    scene,rgb=fixture();edge=scene.connectors[0]
    if mode=='foreign_source':scene=replace(scene,connectors=(replace(edge,source='r5_straight_fanout'),))
    if mode=='anchor':scene=replace(scene,shapes=tuple(replace(s,shape_kind=NodeKind.LABEL_ANCHOR) for s in scene.shapes))
    if mode=='duplicate':scene=replace(scene,connectors=(edge,replace(edge,id='duplicate')))
    if mode=='owner_miss':scene=replace(scene,shapes=(replace(scene.shapes[0],bbox=BBox(68,130,92,154)),scene.shapes[1]))
    if mode=='endpoint_change':scene=replace(scene,connectors=(replace(edge,path_points=(Point(92,192),*edge.path_points[1:])),))
    if mode=='path_elbow':scene=replace(scene,connectors=(replace(edge,path_points=(edge.path_points[0],Point(180,200),edge.path_points[-1])),))
    result,audit=refine_box_centerlines(scene,rgb)
    assert result==scene,audit


def test_original_coordinate_contract():
    scene,rgb=fixture()
    with pytest.raises(ValueError):refine_box_centerlines(scene,rgb.astype(float))
    with pytest.raises(ValueError):refine_box_centerlines(replace(scene,image_size=ImageSize(720,720)),rgb)
