import cv2
import numpy as np
import pytest

from image_to_editable_ppt.research.closed_nodes import observe_closed_node


def render(kind,scale=1,color=(0,0,0),background=(255,255,255),offset=0):
    rgb=np.full((160*scale,240*scale,3),background,np.uint8)
    center=(120*scale,80*scale);axes=(50*scale,35*scale)
    if kind in ('ellipse','open_arc'):
        cv2.ellipse(rgb,center,axes,0,0,360 if kind=='ellipse' else 325,color,2*scale,cv2.LINE_AA)
    elif kind=='rectangle':
        cv2.rectangle(rgb,(70*scale,45*scale),(170*scale,115*scale),color,2*scale,cv2.LINE_AA)
    elif kind=='open_box':
        cv2.rectangle(rgb,(70*scale,45*scale),(170*scale,115*scale),color,2*scale,cv2.LINE_AA)
        rgb[42*scale:49*scale,110*scale:125*scale]=background
    elif kind=='cross':
        cv2.line(rgb,(70*scale,45*scale),(170*scale,115*scale),color,2*scale)
        cv2.line(rgb,(70*scale,115*scale),(170*scale,45*scale),color,2*scale)
    cv2.putText(rgb,'A',(108*scale,88*scale),cv2.FONT_HERSHEY_SIMPLEX,.6*scale,color,scale,cv2.LINE_AA)
    return rgb,[70*scale+offset,45*scale+offset,170*scale+offset,115*scale+offset]


@pytest.mark.parametrize('kind',['ellipse','rectangle'])
@pytest.mark.parametrize('scale',[1,2,3])
@pytest.mark.parametrize('offset',[-3,0,3])
@pytest.mark.parametrize('color',[(0,0,0),(20,50,180),(170,60,0)])
def test_supported_closed_primitives(kind,scale,offset,color):
    rgb,bbox=render(kind,scale,color,offset=offset)
    observed,audit=observe_closed_node(rgb,bbox)
    assert observed is not None,audit
    assert observed['ellipse']==(kind=='ellipse')
    assert max(abs(a-b) for a,b in zip(observed['style'].stroke,color))<20


@pytest.mark.parametrize('kind',['open_arc','open_box','cross','blank'])
@pytest.mark.parametrize('scale',[1,2,3])
def test_no_closing_or_inventing_outline(kind,scale):
    rgb,bbox=render(kind,scale)
    observed,audit=observe_closed_node(rgb,bbox)
    assert observed is None,audit


def test_connected_external_arrow_does_not_make_node_bbox_larger():
    rgb,bbox=render('ellipse',2)
    cv2.arrowedLine(rgb,(20,160),(140,160),(0,0,0),4,tipLength=.1)
    observed,audit=observe_closed_node(rgb,bbox)
    assert observed is not None and observed['ellipse'],audit


def test_fill_sampled_only_in_closed_interior():
    rgb,bbox=render('ellipse',2)
    cv2.ellipse(rgb,(240,160),(96,66),0,0,360,(240,225,180),cv2.FILLED)
    observed,audit=observe_closed_node(rgb,bbox)
    assert observed is not None and observed['style'].fill==(240,225,180),audit


def test_long_shallow_box_has_axis_specific_detector_uncertainty():
    rgb=np.full((150,500,3),255,np.uint8)
    cv2.rectangle(rgb,(50,50),(450,85),(0,0,0),2)
    observed,audit=observe_closed_node(rgb,[46,49,465,86])
    assert observed is not None and not observed['ellipse'],audit


def test_wrong_nearby_owner_and_rotated_ellipse_abstain():
    rgb,bbox=render('ellipse')
    assert observe_closed_node(rgb,[v+30 for v in bbox])[0] is None
    rgb[:]=255
    cv2.ellipse(rgb,(120,80),(50,25),30,0,360,(0,0,0),2)
    assert observe_closed_node(rgb,[70,45,170,115])[0] is None


@pytest.mark.parametrize('thickness',[1,2,4])
@pytest.mark.parametrize('background',[(255,255,255),(230,235,245),(255,240,200)])
def test_thin_closed_boundary_and_background(thickness,background):
    rgb=np.full((160,240,3),background,np.uint8)
    cv2.ellipse(rgb,(120,80),(50,35),0,0,360,(0,0,0),thickness,cv2.LINE_AA)
    observed,audit=observe_closed_node(rgb,[70,45,170,115])
    assert observed is not None and observed['ellipse'],audit


@pytest.mark.parametrize('mode',['soft_shadow','solid_patch','two_half_boxes','glyph_bridge'])
def test_not_every_dark_enclosure_is_a_supported_node(mode):
    rgb=np.full((160,240,3),255,np.uint8)
    if mode in ('soft_shadow','solid_patch'):
        cv2.rectangle(rgb,(70,45),(170,115),(180,180,180),cv2.FILLED)
        if mode=='soft_shadow':rgb=cv2.GaussianBlur(rgb,(21,21),5)
    else:
        cv2.rectangle(rgb,(70,45),(170,115),(0,0,0),2)
        cv2.line(rgb,(120,45),(120,115),(0,0,0),3)
        if mode=='glyph_bridge':cv2.putText(rgb,'A',(88,95),cv2.FONT_HERSHEY_SIMPLEX,2,(0,0,0),3)
    observed,audit=observe_closed_node(rgb,[70,45,170,115])
    assert observed is None,audit
