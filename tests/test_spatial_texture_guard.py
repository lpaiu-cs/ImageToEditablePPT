import cv2
import numpy as np
import pytest
from image_to_editable_ppt.research.spatial_texture_guard import spatial_tile,inspect_spatial_texture
from image_to_editable_ppt.research.spatial_texture_guard import stable_texture_words
from copy import deepcopy


def test_texture_words_need_three_confident_matching_observations_without_mutating_label():
    word=dict(text='Later row',bbox=[2,20,40,30],confidence=.99)
    audit=dict(accepted=[],spatial_ocr=dict(arms=[[deepcopy(word)] for _ in range(3)]))
    before=deepcopy(audit)
    assert len(stable_texture_words(audit))==1 and audit==before
    audit['spatial_ocr']['arms'][2][0]['confidence']=.97
    assert not stable_texture_words(audit)
    audit['spatial_ocr']['arms'][2][0]=dict(word,bbox=[50,50,80,60])
    assert not stable_texture_words(audit)
    audit['spatial_ocr']['arms'][2][0]=dict(word,text='Different')
    assert not stable_texture_words(audit)


def test_later_source_row_needs_fixed_confidence_and_geometry_verdict():
    row=dict(bbox=[1,20,80,30],reason='stable_source_row',observations=[dict(text='Text',confidence=.99) for _ in range(3)])
    audit=dict(source_rows=dict(bands=[row]),accepted=[])
    assert stable_texture_words(audit)[0]['bbox']==row['bbox']
    row['reason']='non_text_row_geometry'
    assert not stable_texture_words(audit)


@pytest.mark.parametrize('mode',['flat','linear','radial','box'])
@pytest.mark.parametrize('scale',[1,2])
def test_flat_gradient_and_sparse_edges_are_not_dense(mode,scale):
    side=32*scale;y,x=np.mgrid[:side,:side]
    values=np.full((side,side),180.)
    if mode=='linear':values=70+140*x/(side-1)
    if mode=='radial':values=70+100*np.hypot(x-side/2,y-side/2)/side
    rgb=np.repeat(values.astype(np.uint8)[:,:,None],3,axis=2)
    if mode=='box':cv2.rectangle(rgb,(5*scale,5*scale),(25*scale,25*scale),(0,0,0),scale)
    assert not spatial_tile(rgb,np.ones((side,side),np.uint8),scale)['dense']


@pytest.mark.parametrize('channels',[1,3])
def test_gray_and_rgb_noise_are_both_dense(channels):
    rng=np.random.default_rng(1911);rgb=rng.integers(30,230,(40,40,channels),dtype=np.uint8)
    if channels==1:rgb=np.repeat(rgb,3,axis=2)
    assert spatial_tile(rgb,np.ones((40,40),np.uint8),1)['dense']
    assert spatial_tile(rgb,np.ones((40,40),np.uint8),1,palette_guard=True)['dense']


def test_palette_guard_explains_concentrated_ink_and_background_without_changing_v1():
    rng=np.random.default_rng(1912);gray=np.full((40,40),255,np.uint8)
    gray.ravel()[::5]=rng.integers(10,230,320,dtype=np.uint8)
    rgb=np.repeat(gray[:,:,None],3,axis=2);mask=np.ones(gray.shape,np.uint8)
    assert spatial_tile(rgb,mask,1)['dense']
    assert not spatial_tile(rgb,mask,1,palette_guard=True)['dense']


def test_trusted_word_mask_is_not_replaced_by_whole_child_exclusion():
    rgb=np.full((360,640,3),255,np.uint8);rng=np.random.default_rng(1911)
    rgb[90:220,100:300]=np.repeat(rng.integers(30,230,(130,200,1),dtype=np.uint8),3,axis=2)
    contour=np.array([[[80,50]],[[320,50]],[[320,250]],[[80,250]]],np.int32)
    candidate=dict(bbox=[80,50,321,251],contour=contour)
    text=dict(accepted=[dict(words=[dict(bbox=[30,10,100,30])])])
    before=rgb.copy();result=inspect_spatial_texture(rgb,candidate,text)
    assert not result['eligible'] and np.array_equal(before,rgb)
