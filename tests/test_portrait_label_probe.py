import sys
from pathlib import Path
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from observe_portrait_labels import observe_portrait
from render_portrait_label_probe import physical_bbox


@pytest.mark.parametrize('orientation,expected',[('clockwise',[30,10,50,100]),('counterclockwise',[20,100,40,190])])
def test_exact_rotation_to_source_coordinates(orientation,expected):
    assert physical_bbox([10,20,100,40],70,200,orientation)==expected


def test_horizontal_owner_never_invokes_ocr():
    def forbidden(*a,**k):raise AssertionError('outside scope')
    value,audit=observe_portrait(np.zeros((100,200,3),np.uint8),[0,0,200,100],np.zeros((100,200),np.uint8),forbidden)
    assert value is None and audit['reason']=='outside_portrait_scope'


def test_empty_portrait_does_not_invent_label():
    def empty(*a,**k):return None,None
    value,audit=observe_portrait(np.full((300,60,3),255,np.uint8),[0,0,60,300],np.zeros((300,60),np.uint8),empty)
    assert value is None


def test_unknown_orientation_rejected():
    with pytest.raises(ValueError):physical_bbox([0,0,10,10],20,40,'guessed')


@pytest.mark.parametrize('score',[.97,1.0])
def test_low_confidence_or_two_approved_directions_abstain(score):
    def engine(image,**kwargs):
        if kwargs.get('use_det') is False:return [('Test',score)],None
        h,w=image.shape[:2]
        return [([[.1*w,.2*h],[.8*w,.2*h],[.8*w,.8*h],[.1*w,.8*h]],'Test',1.)],None
    value,audit=observe_portrait(np.full((300,60,3),255,np.uint8),[0,0,60,300],np.zeros((300,60),np.uint8),engine)
    assert value is None
    assert sum(a['approved'] for a in audit['arms'])==(0 if score<.98 else 2)
