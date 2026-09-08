import cv2
import numpy as np
import pytest
from image_to_editable_ppt.research.source_text_rows import observe_rows


def fixture():
    rgb=np.full((360,640,3),255,np.uint8)
    owned=np.zeros((360,640),np.uint8);owned[40:160,50:350]=1
    cv2.putText(rgb,'First',(65,80),cv2.FONT_HERSHEY_SIMPLEX,1,(0,0,0),2)
    cv2.putText(rgb,'Second',(65,130),cv2.FONT_HERSHEY_SIMPLEX,1,(0,0,0),2)
    return rgb,owned,{'bbox':[50,40,350,160]}


def test_source_rows_use_raw_bands_and_keep_complete_prefix():
    rgb,owned,c=fixture();before=rgb.copy();calls=[]
    def engine(image,**kwargs):
        assert kwargs==dict(use_det=False,use_cls=False,use_rec=True)
        calls.append(image.shape)
        return [['First' if len(calls)<=3 else 'Second',.999]],None
    label,audit=observe_rows(rgb,c,owned,engine)
    assert label=='First\nSecond'
    assert len(audit['accepted'])==2
    assert np.array_equal(rgb,before)


@pytest.mark.parametrize('index',[0,1,2])
def test_any_disagreeing_first_row_blocks_later_rows(index):
    rgb,owned,c=fixture();calls=[0]
    def engine(image,**kwargs):
        current=calls[0];calls[0]+=1
        return [['Bad' if current==index else 'Good',.999]],None
    assert observe_rows(rgb,c,owned,engine)[0] is None


def test_excluded_child_text_does_not_become_parent_row():
    rgb,owned,c=fixture();owned[90:150,55:320]=0
    def engine(image,**kwargs):return [['First',.999]],None
    label,audit=observe_rows(rgb,c,owned,engine)
    assert label=='First'
    assert len(audit['bands'])==1
