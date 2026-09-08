import cv2
import numpy as np
import pytest
from image_to_editable_ppt.research.source_texture_guard import inspect_texture


@pytest.mark.parametrize('scale',[1,2])
@pytest.mark.parametrize('mode',['flat','text','gradient','photo','photo_caption'])
def test_texture_veto_reads_full_source_including_nested_photo(scale,mode):
    rgb=np.full((360*scale,640*scale,3),255,np.uint8)
    contour=np.array([[[50,40]],[[300,40]],[[300,220]],[[50,220]]],np.int32)*scale
    if mode=='text':cv2.putText(rgb,'Diagram',(70*scale,140*scale),cv2.FONT_HERSHEY_SIMPLEX,scale,(0,0,0),2*scale)
    if mode=='gradient':
        rgb[40*scale:220*scale,50*scale:300*scale]=np.linspace(190,255,250*scale,dtype=np.uint8)[None,:,None]
    if mode in ('photo','photo_caption'):
        top=80 if mode=='photo_caption' else 45
        rgb[top*scale:215*scale,55*scale:295*scale]=np.random.default_rng(59).integers(20,235,((215-top)*scale,240*scale,3),dtype=np.uint8)
        if mode=='photo_caption':cv2.putText(rgb,'Photo',(70*scale,65*scale),cv2.FONT_HERSHEY_SIMPLEX,.5*scale,(0,0,0),scale)
    before=rgb.copy()
    result=inspect_texture(rgb,dict(bbox=[50*scale,40*scale,300*scale,220*scale],contour=contour))
    assert result['eligible']==(mode not in ('photo','photo_caption')),result
    assert np.array_equal(before,rgb)


def test_caption_text_exclusion_never_hides_its_photographic_child():
    rgb=np.full((360,640,3),255,np.uint8)
    rgb[80:215,55:295]=np.random.default_rng(59).integers(20,235,(135,240,3),dtype=np.uint8)
    contour=np.array([[[50,40]],[[300,40]],[[300,220]],[[50,220]]],np.int32)
    text={'accepted':[{'words':[dict(text='PHOTOID',bbox=[20,5,170,30])]}]}
    result=inspect_texture(rgb,dict(bbox=[50,40,300,220],contour=contour),text)
    assert not result['eligible']


def test_many_two_color_antialias_levels_are_not_chromatic_texture():
    noise=np.random.default_rng(83).integers(0,256,(360,640),dtype=np.uint8)
    rgb=np.repeat(noise[:,:,None],3,axis=2)
    contour=np.array([[[50,40]],[[300,40]],[[300,220]],[[50,220]]],np.int32)
    result=inspect_texture(rgb,dict(bbox=[50,40,300,220],contour=contour))
    assert result['eligible']  # Also documents the grayscale-photo blind spot.
