import numpy as np
import torch
from image_to_editable_ppt.research import candidate_validity as cv


def test_dedup_preserves_full_and_nested_candidates():
    rows=[dict(id='parent',view='full',bbox=[0,0,100,100]),dict(id='child',view='full',bbox=[20,20,40,40]),
        dict(id='duplicate',view='tile0',bbox=[1,1,99,99]),dict(id='new',view='tile1',bbox=[110,0,130,20])]
    kept,crops=cv.merge_views(rows,torch.arange(4)[:,None])
    assert [o['id'] for o in kept]==['parent','child','new'] and crops[:,0].tolist()==[0,1,3]
    assert cv.supervision(rows,[rows[0],rows[1]]).tolist()==[1,1,1,0]
    assert cv.supervision([dict(bbox=[50,0,150,100])],[rows[0]]).tolist()==[-1]
    near_full=dict(id='inner-ring',view='full',bbox=[2,2,98,98])
    assert len(cv.merge_views([rows[0],near_full],torch.zeros(2,1))[0])==2


def test_tiles_map_to_source_and_reject_internal_cut_edges(monkeypatch):
    def fake(model,rgb):
        h,w=rgb.shape[:2]
        return [dict(id='inner',bbox=[10,10,30,30],kind=1),dict(id='cut',bbox=[w-10,10,w,30],kind=1)],torch.zeros(2,2,64,64)
    monkeypatch.setattr(cv,'view_candidates',fake)
    views=cv.propose(None,np.zeros((100,200,3),np.uint8))
    assert any(o['bbox']==[90,50,110,70] for o in views['multiscale'][0])
    assert not any(o['id']=='tile0:cut' for o in views['multiscale'][0])
    assert all(o in views['multiscale'][0] for o in views['full'][0])
