import cv2
import numpy as np
import pytest
from image_to_editable_ppt.research.source_rays import observe_pair


def fixture(angle=0, scale=1, mode='arrow', reverse=False):
    mask = np.zeros((round(360*scale),round(360*scale)),np.uint8)
    theta=np.deg2rad(angle)
    u=np.array([np.cos(theta),np.sin(theta)]);v=np.array([-u[1],u[0]])
    center=np.array([180,180])
    def point(x,y=0):return np.rint((center+x*u+y*v)*scale).astype(np.int32)
    start,end=-100,100
    if reverse:start,end=end,start
    if mode not in ('empty','gap','elbow','parallel'):
        cv2.line(mask,point(start),point(end),1,max(1,round(3*scale)))
    if mode=='arrow':
        base=end-np.sign(end-start)*8
        cv2.fillConvexPoly(mask,np.array([point(end),point(base,5),point(base,-5)]),1)
    if mode=='bar':cv2.line(mask,point(end,-7),point(end,7),1,max(1,round(2*scale)))
    if mode=='dot':cv2.circle(mask,point(end),round(5*scale),1,-1)
    if mode=='gap':
        cv2.line(mask,point(-100),point(-10),1,round(3*scale));cv2.line(mask,point(10),point(100),1,round(3*scale))
    if mode=='elbow':cv2.polylines(mask,[np.array([point(-100),point(0,20),point(100)])],False,1,round(3*scale))
    if mode=='parallel':
        for offset in [-5,5]:cv2.line(mask,point(-100,offset),point(100,offset),1,round(3*scale))
    owners=[]
    for t in [-112,112]:
        c=(center+t*u)*scale
        owners.append([c[0]-8*scale,c[1]-8*scale,c[0]+8*scale,c[1]+8*scale])
    yy,xx=np.where(mask)
    return np.column_stack([xx,yy]),owners


@pytest.mark.parametrize('angle',[0,30,60,90,135])
@pytest.mark.parametrize('scale',[.75,1,1.5])
@pytest.mark.parametrize('reverse',[False,True])
def test_independent_arrow_rgb(angle,scale,reverse):
    pixels,boxes=fixture(angle,scale,reverse=reverse)
    result,audit=observe_pair(pixels,boxes,scale=scale)
    assert result is not None,audit
    assert audit['reversed']==reverse


@pytest.mark.parametrize('mode',['empty','line','gap','elbow','parallel','bar','dot','third'])
def test_unsupported_geometry(mode):
    pixels,boxes=fixture(mode='arrow' if mode=='third' else mode)
    result,audit=observe_pair(pixels,boxes,scale=1,other_boxes=[[175,175,185,185]] if mode=='third' else [])
    assert result is None,audit


@pytest.mark.parametrize('angle',[0,15,30,45,60,75,90,135])
@pytest.mark.parametrize('scale',[.75,1,1.5])
@pytest.mark.parametrize('reverse',[False,True])
@pytest.mark.parametrize('mode',['line','gap','elbow','parallel','bar','dot'])
def test_negative_rotation_scale_matrix(angle,scale,reverse,mode):
    pixels,boxes=fixture(angle,scale,mode,reverse)
    assert observe_pair(pixels,boxes,scale=scale)[0] is None
