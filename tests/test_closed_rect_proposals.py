import cv2
import numpy as np
import pytest

from image_to_editable_ppt.research.closed_rect_proposals import propose,propose_union,observe_text
from image_to_editable_ppt.research.closed_rect_proposals import pixel_cell_agreement


@pytest.mark.parametrize('a,b,expected',[
    ([313,169,403,229],[313,169,402,228],True),
    ([0,0,30,50],[1,1,29,49],True),
    ([0,0,1000,1000],[0,0,1002,1000],False),
    ([0,0,30,50],[0,0,28,50],False),
])
def test_boundary_cell_error_does_not_depend_on_object_area(a,b,expected):
    assert pixel_cell_agreement(a,b)==expected


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


def test_explicit_inner_boundary_policy_keeps_real_inner_without_merging():
    rgb=np.full((360,640,3),255,np.uint8)
    cv2.rectangle(rgb,(50,40),(270,140),(0,0,0),1)
    cv2.rectangle(rgb,(54,44),(266,136),(0,0,0),1)
    selected,audit=propose(rgb,inner_boundaries=True)
    assert len(selected)==1
    x,y,x1,y1=selected[0]['bbox']
    assert x>=53 and y>=43 and x1<=268 and y1<=138
    assert audit['inner_boundaries']


def test_overlapping_ocr_windows_cannot_repeat_a_source_glyph():
    def engine(image,**kwargs):
        s=image.shape[0]/100
        return [(np.array([[a,5],[b,5],[b,20],[a,20]])*s,text,.99)
                for a,b,text in [(5,65,'Section 3'),(55,85,'3.4')]],None
    label,audit=observe_text(np.full((100,100,3),255,np.uint8),[0,0,100,100],engine)
    assert label is None
    assert all(arm[0]['overlapping_words'] for arm in audit['lines'])


def test_whole_line_reads_one_observed_window_instead_of_joining_fragments():
    def engine(image,**kwargs):
        if kwargs.get('use_det') is False:return [['Section 3.4',.99]],None
        s=image.shape[0]/100
        return [(np.array([[a,5],[b,5],[b,20],[a,20]])*s,text,.99)
                for a,b,text in [(5,65,'Section 3'),(55,85,'3.4')]],None
    label,audit=observe_text(np.full((100,100,3),255,np.uint8),[0,0,100,100],engine,whole_lines=True)
    assert label=='Section 3.4'
    assert all(arm[0]['whole_line_observation']['text']=='Section 3.4' for arm in audit['lines'])


def test_whole_line_disagreement_is_not_majority_voted():
    count=[0]
    def engine(image,**kwargs):
        if kwargs.get('use_det') is False:
            count[0]+=1
            return [['Wrong' if count[0]==1 else 'Right',.99]],None
        s=image.shape[0]/100
        return [(np.array([[a,5],[b,5],[b,20],[a,20]])*s,text,.99)
                for a,b,text in [(5,65,'Section 3'),(55,85,'3.4')]],None
    assert observe_text(np.full((100,100,3),255,np.uint8),[0,0,100,100],engine,whole_lines=True)[0] is None


def test_inner_boundary_policy_does_not_merge_overlapping_distinct_boxes():
    rgb=np.full((360,640,3),255,np.uint8)
    cv2.rectangle(rgb,(50,40),(270,140),(0,0,0),1)
    cv2.rectangle(rgb,(57,45),(277,145),(0,0,0),1)
    selected,_=propose(rgb,inner_boundaries=True)
    # No selected boundary may pretend to encompass both original boxes.
    assert all(c['bbox'] != [49,39,279,147] for c in selected)


@pytest.mark.parametrize('scale',[1,2,3])
def test_dark_closed_boundary_alternative_preserves_observed_hole(scale):
    rgb=np.full((360*scale,640*scale,3),255,np.uint8)
    cv2.rectangle(rgb,(50*scale,40*scale),(270*scale,140*scale),(195,220,180),-1)
    cv2.rectangle(rgb,(50*scale,40*scale),(270*scale,140*scale),(0,0,0),scale)
    selected,audit=propose(rgb,dark_boundaries=True)
    assert len(selected)==1
    assert audit['thresholds']==[130,170]
    rgb[35*scale:45*scale,130*scale:150*scale]=255
    assert not propose(rgb,dark_boundaries=True)[0]


@pytest.mark.parametrize('scale',[1,2,3])
def test_portrait_closed_box_uses_same_rotated_size_contract(scale):
    rgb=np.full((360*scale,640*scale,3),255,np.uint8)
    cv2.rectangle(rgb,(50*scale,40*scale),(90*scale,300*scale),(0,0,0),scale)
    assert not propose(rgb,dark_boundaries=True)[0]
    selected,audit=propose(rgb,dark_boundaries=True,portrait_boxes=True)
    assert len(selected)==1
    assert audit['portrait_boxes']
    rgb[150*scale:160*scale,45*scale:55*scale]=255
    assert not propose(rgb,dark_boundaries=True,portrait_boxes=True)[0]


def test_union_returns_observed_boxes_and_not_a_new_average_geometry():
    rgb=np.full((360,640,3),255,np.uint8)
    cv2.rectangle(rgb,(50,40),(270,140),(0,0,0),2)
    cv2.rectangle(rgb,(350,40),(550,140),(190,190,190),1)
    selected,audit=propose_union(rgb)
    observed=propose(rgb,inner_boundaries=True)[0]+propose(rgb,dark_boundaries=True)[0]
    assert len(selected)==2
    assert all(any(c['bbox']==o['bbox'] and np.array_equal(c['contour'],o['contour']) for o in observed) for c in selected)
    assert len({tuple(c['bbox']) for c in selected})==len(selected)
