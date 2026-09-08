from copy import deepcopy

import numpy as np
import pytest

from image_to_editable_ppt.research.duplicate_owner_observations import observe_owners


def scene():
    rgb=np.full((360,640,3),255,np.uint8)
    owners=[dict(id='opaque',semantic_kind='label_anchor',bbox_xyxy=[300,150,320,170],confidence=.7)]
    return rgb,owners


@pytest.mark.parametrize('change', ['label','connector','gt','nan','outside','duplicate','score','missing'])
def test_input_boundary(change):
    rgb,owners=scene()
    if change in ('label','connector','gt'):owners[0][change]='forbidden'
    elif change=='nan':owners[0]['bbox_xyxy'][0]=float('nan')
    elif change=='outside':owners[0]['bbox_xyxy'][0]=-1
    elif change=='duplicate':owners.append(deepcopy(owners[0]))
    elif change=='score':owners[0]['confidence']=float('inf')
    else:del owners[0]['semantic_kind']
    with pytest.raises(ValueError):observe_owners(rgb,owners)


def test_noop_preserves_all_fields_and_nonanchors(monkeypatch):
    rgb,owners=scene();owners.append(dict(id='ordinary',semantic_kind='box',bbox_xyxy=[300,150,320,170],confidence=.99))
    before=deepcopy(owners)
    def denied(*args,**kwargs):raise AssertionError('observer attempted file read')
    monkeypatch.setattr('builtins.open',denied)
    for arm in ('D-O','D-S'):
        kept,audit,masks=observe_owners(rgb,owners,arm=arm)
        assert kept==owners==before
        assert audit['unchanged_nonanchors']==['ordinary']
        assert audit['clusters']==[] and not masks


def test_blank_tie_and_opaque_id_renaming():
    rgb,owners=scene();owners.append(dict(owners[0],id='second',confidence=.1))
    result,audit,_=observe_owners(rgb,owners,arm='D-S')
    assert result==owners and not audit['suppressed_ids']
    renamed=[dict(o,id=str(100-i)) for i,o in enumerate(owners)]
    result,renamed_audit,_=observe_owners(rgb,renamed,arm='D-S')
    assert result==renamed and not renamed_audit['suppressed_ids']


@pytest.mark.parametrize('bad', [np.zeros((3,3),np.uint8),np.zeros((3,3,3),float)])
def test_invalid_rgb(bad):
    with pytest.raises(ValueError):observe_owners(bad,[])
