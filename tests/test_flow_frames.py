from dataclasses import replace
import pytest
from image_to_editable_ppt.research.flow_frames import frame_witnesses,surviving_frames
from image_to_editable_ppt.v3.core.enums import NodeKind,PortOwnerKind,ConnectorKind
from image_to_editable_ppt.v3.core.types import BBox,ImageSize,Point
from image_to_editable_ppt.v3.emit.models import EmitScene,EmitShapePrimitive,EmitConnectorPrimitive


def scene_pair():
    shapes=tuple(EmitShapePrimitive(k,PortOwnerKind.NODE,NodeKind.BOX,BBox(*b),.9,label='Caption',
        source='raw_closed_rectangle_proposal') for k,b in [('frame',(100,100,200,250)),('seed',(400,80,520,270))])
    edges=tuple(EmitConnectorPrimitive(k,ConnectorKind.ARROW,.9,a,PortOwnerKind.NODE,b,PortOwnerKind.NODE,
        k+':s',k+':e',path_points=tuple(Point(*p) for p in points),arrowhead_end=True,source='r3_stroke_trace')
        for k,a,b,points in [('out','frame','seed',[(200,140),(400,140)]),('in','seed','frame',[(400,210),(200,210)])])
    return EmitScene(ImageSize(600,360),shapes=shapes,connectors=edges),{'frame':{'eligible':False},'seed':{'eligible':True}}


@pytest.mark.parametrize('case',['valid','single','same_port','lines','two_out','unlabelled','chain','third_owner','inside','bad_attachment','unverified'])
def test_only_fixed_external_independent_flow_admits_frame(case):
    scene,content=scene_pair();a,b=scene.connectors
    if case=='single':scene=replace(scene,connectors=(a,))
    if case=='same_port':scene=replace(scene,connectors=(a,replace(b,path_points=tuple(reversed(a.path_points)))))
    if case=='lines':scene=replace(scene,connectors=tuple(replace(e,arrowhead_end=False) for e in scene.connectors))
    if case=='two_out':scene=replace(scene,connectors=(a,replace(b,source_owner_id='frame',target_owner_id='seed',path_points=tuple(reversed(b.path_points)))))
    if case=='unlabelled':scene=replace(scene,shapes=(scene.shapes[0],replace(scene.shapes[1],label=None)))
    if case=='chain':content['seed']['eligible']=False
    if case in ('third_owner','inside'):
        box=(280,125,310,160) if case=='third_owner' else (120,120,160,160)
        scene=replace(scene,shapes=scene.shapes+(replace(scene.shapes[1],id='child',bbox=BBox(*box)),));content['child']={'eligible':True}
    if case=='bad_attachment':scene=replace(scene,connectors=(a,replace(b,path_points=(Point(400,210),Point(210,210)))))
    if case=='unverified':scene=replace(scene,shapes=(replace(scene.shapes[0],source='unverified'),scene.shapes[1]))
    before=dict(content['frame']);witnesses=frame_witnesses(scene,content)
    assert set(witnesses)==({'frame'} if case=='valid' else set())
    assert content['frame']==before and scene.shapes[0].label=='Caption'
    if witnesses:
        assert surviving_frames(witnesses,scene)=={'frame'}
        assert not surviving_frames(witnesses,replace(scene,connectors=(a,)))
        assert not surviving_frames(witnesses,replace(scene,connectors=(a,replace(b,arrowhead_end=False))))


def test_nontext_policy_covers_texture_pass_without_mutual_endorsement():
    scene,content=scene_pair();content['frame']['eligible']=True
    nontext={'frame':{'reason':'unexplained_interior_content'},'seed':{'reason':'flat_owned_interior'}}
    assert not frame_witnesses(scene,content)
    assert set(frame_witnesses(scene,content,nontext))=={'frame'}
    nontext['seed']['reason']='unexplained_interior_content'
    assert not frame_witnesses(scene,content,nontext)
    nontext['frame']['reason']='insufficient_unexplained_interior'
    nontext['seed']['reason']='flat_owned_interior'
    assert not frame_witnesses(scene,content,nontext)
