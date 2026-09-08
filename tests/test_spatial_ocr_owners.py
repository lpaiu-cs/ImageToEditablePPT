from copy import deepcopy
import cv2
import numpy as np
import pytest
from image_to_editable_ppt.research.spatial_ocr_owners import select_cluster


def fixture():
    rgb=np.full((360,640,3),255,np.uint8)
    for x in (100,111,122):
        cv2.rectangle(rgb,(x,90),(x+2,104),(0,0,0),-1)
        cv2.rectangle(rgb,(x,90),(x+7,92),(0,0,0),-1)
    word=dict(polygon=[[98,88],[133,88],[133,107],[98,107]],text='PPP',confidence=.99)
    c=dict(crop=[94,84,138,114],owners=[dict(id='full',bbox=[97,87,134,108]),
        dict(id='cut',bbox=[98,91,134,110])],observations=[dict(words=[deepcopy(word)]),dict(words=[deepcopy(word)])])
    return rgb,c


def test_positive_and_no_input_mutation():
    rgb,c=fixture();before=deepcopy(c);old=rgb.copy()
    chosen,audit=select_cluster(rgb,c)
    assert chosen=='full',audit
    assert c==before and np.array_equal(old,rgb)


@pytest.mark.parametrize('mode',['tie','separate_word','low_conf_word','partial','weak','dot','low_conf_only','scale_text','scale_space','rotated'])
def test_negative_evidence_preserves(mode):
    rgb,c=fixture()
    if mode=='tie':c['owners'][1]['bbox']=c['owners'][0]['bbox'].copy()
    if mode=='partial':c['owners'][1]['bbox'][0]=115
    if mode in ('weak','dot'):
        rgb[109,135]=230 if mode=='weak' else 0
        c['owners'][1]['bbox'][2]=137
    if mode in ('separate_word','low_conf_word'):
        cv2.rectangle(rgb,(105,110),(110,112),(0,0,0),-1)
        w=dict(polygon=[[103,108],[113,108],[113,114],[103,114]],text='X',confidence=.99 if mode=='separate_word' else .7)
        for o in c['observations']:o['words'].append(deepcopy(w))
    if mode=='low_conf_only':
        for o in c['observations']:o['words'][0]['confidence']=.8
    if mode=='scale_text':c['observations'][1]['words'][0]['text']='PP'
    if mode=='scale_space':c['observations'][1]['words'][0]['polygon']=[[50,40],[85,40],[85,59],[50,59]]
    if mode=='rotated':
        for o in c['observations']:o['words'][0]['polygon'][1][1]+=12
    winner,audit=select_cluster(rgb,c)
    assert winner is None,(mode,audit)


@pytest.mark.parametrize('move',[0,1,10])
@pytest.mark.parametrize('reverse',[False,True])
def test_translation_order_and_opaque_id(move,reverse):
    rgb,c=fixture()
    rgb=np.roll(rgb,move,axis=1)
    for o in c['owners']:
        o['id']='renamed-'+o['id'];o['bbox'][0]+=move;o['bbox'][2]+=move
    c['crop'][0]+=move;c['crop'][2]+=move
    for obs in c['observations']:
        for word in obs['words']:
            for p in word['polygon']:p[0]+=move
    if reverse:c['owners'].reverse()
    winner,audit=select_cluster(rgb,c)
    assert winner=='renamed-full',audit


def test_long_observed_line_can_explain_extra_ocr_snippet():
    rgb,c=fixture()
    cv2.line(rgb,(117,110),(117,210),(0,0,0),1)
    c['owners'][1]['bbox'][3]=116;c['crop'][3]=119
    w=dict(polygon=[[115,109],[119,109],[119,119],[115,119]],text='1',confidence=.7)
    for o in c['observations']:o['words'].append(deepcopy(w))
    chosen,audit=select_cluster(rgb,c)
    assert chosen=='full',audit
