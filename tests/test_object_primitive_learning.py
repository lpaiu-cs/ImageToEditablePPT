import numpy as np
import pytest
import torch
from image_to_editable_ppt.research.object_primitive_learning import candidate_crops,object_classifier,classify_candidates


def test_object_bbox_does_not_shrink_with_class_confidence():
    p=np.zeros((7,40,64),np.float32);p[0]=1
    p[0,10:30,10:40]=0;p[1:7,10:30,10:40]=1/6
    rgb=np.full((200,320,3),255,np.uint8)
    objects,crops=candidate_crops(rgb,p)
    assert len(objects)==1 and objects[0]['bbox']==[50.,50.,200.,150.]
    assert crops.shape==(1,2,64,64) and crops.min()>=0 and crops.max()<=1
    torch.set_num_threads(1);model=object_classifier().eval()
    predicted=classify_candidates(model,objects,crops)
    assert predicted[0]['bbox']==objects[0]['bbox'] and 1<=predicted[0]['kind']<=6
    assert candidate_crops(rgb,np.stack([np.ones((40,64)),*([np.zeros((40,64))]*6)]).astype(np.float32))[1].shape==(0,2,64,64)
    with pytest.raises(ValueError):candidate_crops(rgb[:,:,0],p)
    with pytest.raises(ValueError):candidate_crops(rgb,p*np.nan)
