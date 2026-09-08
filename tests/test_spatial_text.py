from copy import deepcopy
import numpy as np
import pytest
from image_to_editable_ppt.research.spatial_text import select_text


def word(text='CP',confidence=.99,box=(20,20,40,30)):
    a,b,c,d=box
    return dict(text=text,confidence=confidence,polygon=[[a,b],[c,b],[c,d],[a,d]])


@pytest.mark.parametrize('mode',['clean','extra_outside','low','disagree','move','partial','multiple','extra_inside','rotated','no_observation'])
def test_spatial_word_contract(mode):
    rgb=np.full((100,100,3),255,np.uint8)
    observations=[dict(words=[word()],scale=3),dict(words=[word()],scale=4.5)]
    if mode=='low':observations[0]['words'][0]['confidence']=.94
    if mode=='disagree':observations[0]['words'][0]['text']='PP'
    if mode=='move':observations[0]['words'][0]=word(box=(22,20,48,30))
    if mode=='partial':observations[0]['words'][0]=word(box=(5,20,40,30))
    if mode=='multiple':observations[0]['words'].append(word(text='dog'))
    if mode=='extra_inside':observations[0]['words'].append(word('1',.6,(43,20,45,30)))
    if mode=='extra_outside':observations[0]['words'].append(word('dog',.99,(60,20,80,30)))
    if mode=='rotated':observations[0]['words'][0]['polygon']=[[20,20],[40,25],[40,35],[20,30]]
    if mode=='no_observation':observations=[]
    label,audit=select_text(rgb,[10,10,50,40],observations)
    assert (label=='CP') if mode in ('clean','extra_outside') else label is None


def test_low_snippet_requires_original_long_stroke():
    rgb=np.full((360,360,3),255,np.uint8);rgb[10:111,44]=0
    rows=[dict(words=[word(),word('1',.6,(43,32,45,39))],scale=scale) for scale in (3,4.5)]
    assert select_text(rgb,[10,10,50,40],rows)[0]=='CP'
    rgb[:]=255;rgb[35,44]=0
    assert select_text(rgb,[10,10,50,40],rows)[0] is None
