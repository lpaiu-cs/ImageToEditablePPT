import cv2
import numpy as np
import pytest
from image_to_editable_ppt.research.closed_rect_proposals import propose_union


@pytest.mark.parametrize('kind',['square','portrait_compact','landscape_compact','circle','diamond','open','tiny'])
def test_compact_hole_without_relaxing_closure_or_size(kind):
    rgb=np.full((360,600,3),255,np.uint8)
    if kind=='circle':cv2.circle(rgb,(250,170),60,(0,0,0),2)
    elif kind=='diamond':cv2.polylines(rgb,[np.array([(250,110),(310,170),(250,230),(190,170)])],True,(0,0,0),2)
    else:
        end=(310,230) if kind in ('square','open') else (300,230) if kind=='portrait_compact' else (310,220) if kind=='landscape_compact' else (210,130)
        cv2.rectangle(rgb,(190,110),end,(0,0,0),2)
        if kind=='open':rgb[105:115,245:255]=255
    old,_=propose_union(rgb,portrait_boxes=True,pixel_agreement=True)
    new,_=propose_union(rgb,portrait_boxes=True,pixel_agreement=True,compact_boxes=True)
    assert not old
    assert len(new)==(1 if kind in ('square','portrait_compact','landscape_compact') else 0)
