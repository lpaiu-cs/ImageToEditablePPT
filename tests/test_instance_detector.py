import numpy as np
import pytest
import torch
from image_to_editable_ppt.research.instance_detector import image_tensor,target,decode


def test_rgb_target_and_decode_keep_nested_instances():
    assert image_tensor(np.zeros((30,40,3),np.uint8)).shape==(3,30,40)
    objects=[dict(kind=2,bbox=[0,0,40,30]),dict(kind=1,bbox=[10,10,20,20])]
    batch=target(objects,(40,30));prediction=dict(boxes=batch['boxes'],labels=batch['labels'],scores=torch.tensor([.99,.8]))
    assert len(decode(prediction,(40,30),.5))==2
    assert len(decode(prediction,(40,30),.9))==1
    assert target([],(40,30))['boxes'].shape==(0,4)
    with pytest.raises(ValueError):target([dict(kind=1,bbox=[0,0,41,30])],(40,30))
    with pytest.raises(ValueError):image_tensor(np.zeros((30,40,3),float))
