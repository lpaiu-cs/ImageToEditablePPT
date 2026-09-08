from itertools import permutations
import cv2
import numpy as np
import pytest
from image_to_editable_ppt.region import tracing
from image_to_editable_ppt.v3.core.enums import NodeKind, PortOwnerKind
from image_to_editable_ppt.v3.core.types import BBox
from image_to_editable_ppt.v3.emit.models import EmitShapePrimitive


@pytest.mark.parametrize('mode',['arrows','plain','mixed','bent'])
def test_hub_first_search_is_order_invariant_and_keeps_negative_gates(mode,monkeypatch):
    mask=np.zeros((320,440),np.uint8);root=(20,160);ends=((410,40),(410,280))
    for i,p in enumerate(ends):
        start=root
        if mode=='bent':
            start=(180,p[1]);cv2.line(mask,root,(180,160),1,2);cv2.line(mask,(180,160),start,1,2)
        if mode=='plain' or (mode=='mixed' and i==0):cv2.line(mask,start,p,1,2)
        else:cv2.arrowedLine(mask,start,p,1,2,tipLength=.035)
    contacts=[(EmitShapePrimitive(name,PortOwnerKind.NODE,NodeKind.BOX,BBox(*box),1),point)
        for name,box,point in [('hub',(0,140,15,180),root),
            ('top',(415,20,439,60),ends[0]),('bottom',(415,260,439,300),ends[1])]]
    original=tracing.shortest;calls=[]
    def observed(mask,start,end):
        calls.append((start,end));return original(mask,start,end)
    monkeypatch.setattr(tracing,'shortest',observed)
    for ordered in permutations(contacts):
        calls.clear()
        result=tracing.straight_fanout(mask,ordered,2,directed_search=True)
        assert bool(result)==(mode=='arrows')
        if result:
            assert {(a.id,b.id) for a,b,_,_ in result}=={('hub','top'),('hub','bottom')}
            assert all((root,end) in calls for end in ends)
