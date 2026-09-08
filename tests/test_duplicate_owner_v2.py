from copy import deepcopy
import numpy as np
import pytest
from image_to_editable_ppt.research.duplicate_owner_v2 import observe_owners_v2


def owner():
    return dict(id='a',semantic_kind='label_anchor',bbox_xyxy=[100,100,120,120],confidence=.8)


@pytest.mark.parametrize('field',['label','ocr','connector','annotation','expected_id'])
def test_whitelist(field):
    o=owner();o[field]='forbidden'
    with pytest.raises(ValueError):observe_owners_v2(np.full((360,640,3),255,np.uint8),[o])


@pytest.mark.parametrize('failure',['nan','negative','zero','duplicate'])
def test_bad_owner(failure):
    o=owner();os=[o]
    if failure=='nan':o['bbox_xyxy'][0]=float('nan')
    if failure=='negative':o['bbox_xyxy'][0]=-1
    if failure=='zero':o['bbox_xyxy'][2]=100
    if failure=='duplicate':os.append(deepcopy(o))
    with pytest.raises(ValueError):observe_owners_v2(np.full((360,640,3),255,np.uint8),os)


def test_crop_frame_requires_context():
    with pytest.raises(ValueError,match='missing_frame_context'):
        observe_owners_v2(np.full((100,100,3),255,np.uint8),[],frame={'origin_xy':[0,0]})


def test_noop_preserves_original_without_io(monkeypatch):
    rgb=np.full((360,640,3),255,np.uint8);os=[owner()]
    def denied(*a,**k):raise AssertionError('file access')
    monkeypatch.setattr('builtins.open',denied)
    for arm in ('V2-O','V2-S'):
        kept,audit,_=observe_owners_v2(rgb,os,arm=arm)
        assert kept==os and not audit['suppressed_ids']
