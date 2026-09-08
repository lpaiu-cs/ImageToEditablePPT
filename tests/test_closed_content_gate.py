import cv2
import numpy as np
import pytest
from types import SimpleNamespace
from image_to_editable_ppt.research.closed_content_gate import inspect_content,admitted_ids


@pytest.mark.parametrize('scale',[1,2,3])
@pytest.mark.parametrize('kind',['flat','photo','icon'])
def test_owned_interior_unexplained_content_gate(scale,kind):
    rgb=np.full((360*scale,640*scale,3),255,np.uint8)
    owned=np.zeros(rgb.shape[:2],np.uint8);owned[40*scale:140*scale,50*scale:270*scale]=1
    if kind=='photo':
        rgb[50*scale:130*scale,60*scale:260*scale]=np.random.default_rng(47).integers(30,220,(80*scale,200*scale,3),dtype=np.uint8)
    if kind=='icon':
        cv2.circle(rgb,(160*scale,85*scale),30*scale,(0,0,0),-1)
    result=inspect_content(rgb,{'bbox':[50*scale,40*scale,270*scale,140*scale]},owned,{'accepted':[]})
    assert result['eligible']==(kind=='flat'),result


def test_blank_closed_geometry_requires_native_link_to_trusted_label():
    shapes=[SimpleNamespace(id=x,label='A' if x=='a' else None) for x in ['a','b','c','photo']]
    content={x:dict(eligible=x!='photo') for x in ['a','b','c','photo']}
    edges=[SimpleNamespace(source_owner_id='a',target_owner_id=x) for x in ['b','photo']]
    scene=SimpleNamespace(shapes=shapes,connectors=edges)
    assert admitted_ids(scene,content)=={'a','b'}
    scene.connectors=[]
    assert admitted_ids(scene,content)=={'a'}
