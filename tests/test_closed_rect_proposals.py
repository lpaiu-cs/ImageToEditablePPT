import cv2
import numpy as np
import pytest

from image_to_editable_ppt.research.closed_rect_proposals import propose,observe_text


@pytest.mark.parametrize('scale',[1,2,3])
@pytest.mark.parametrize('color',[(0,0,0),(30,80,150),(180,180,180)])
def test_closed_rectangle_is_observed(scale,color):
    rgb=np.full((360*scale,640*scale,3),255,np.uint8)
    cv2.rectangle(rgb,(50*scale,40*scale),(270*scale,140*scale),color,scale)
    candidates,audit=propose(rgb)
    assert len(candidates)==1,audit


@pytest.mark.parametrize('mode',['open','circle','diamond','text','gradient','nested'])
def test_nonrectangular_or_ambiguous_outlines_abstain(mode):
    rgb=np.full((360,640,3),255,np.uint8)
    if mode in ('open','nested'):
        cv2.rectangle(rgb,(50,40),(270,140),(0,0,0),1)
        if mode=='open':rgb[38:44,130:150]=255
        else:cv2.rectangle(rgb,(54,44),(266,136),(0,0,0),1)
    if mode=='circle':cv2.ellipse(rgb,(160,90),(110,50),0,0,360,(0,0,0),1)
    if mode=='diamond':cv2.polylines(rgb,[np.array([[160,30],[270,90],[160,150],[50,90]])],True,(0,0,0),1)
    if mode=='text':cv2.putText(rgb,'DATA',(50,110),cv2.FONT_HERSHEY_SIMPLEX,2,(0,0,0),2)
    if mode=='gradient':rgb[:]=np.arange(640,dtype=float)[None,:,None]*.1+180
    assert not propose(rgb)[0]


def test_unstable_ocr_word_not_added():
    def engine(image,**kwargs):
        return [([[5,5],[50,5],[50,20],[5,20]],'A' if image.shape[0]<180 else 'B',.99)],None
    label,audit=observe_text(np.full((100,100,3),255,np.uint8),[0,0,100,100],engine)
    assert label is None


def test_low_confidence_part_of_same_line_is_not_silently_removed():
    def engine(image,**kwargs):
        s=image.shape[0]/100
        return [(np.array([[5,5],[30,5],[30,20],[5,20]])*s,'Good',.99),
                (np.array([[35,5],[70,5],[70,20],[35,20]])*s,'Bad',.5)],None
    label,audit=observe_text(np.full((100,100,3),255,np.uint8),[0,0,100,100],engine)
    assert label is None


def test_confident_title_kept_but_later_fragments_do_not_skip_unknown_line():
    def engine(image,**kwargs):
        s=image.shape[0]/100
        return [(np.array([[5,y],[70,y],[70,y+15],[5,y+15]])*s,text,confidence)
                for y,text,confidence in [(5,'Title',.99),(30,'Unknown',.5),(55,'Fragment',.99)]],None
    label,audit=observe_text(np.full((100,100,3),255,np.uint8),[0,0,100,100],engine)
    assert label=='Title'
