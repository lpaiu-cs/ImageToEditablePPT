import cv2
import numpy as np
import pytest
from image_to_editable_ppt.research.closed_rect_proposals import propose_union


@pytest.mark.parametrize('gap,expected',[(0,1),(1,1),(2,0),(5,0),(20,0)])
def test_one_pixel_neighbour_does_not_fill_large_open_borders(gap,expected):
    rgb=np.full((360,640,3),255,np.uint8)
    cv2.rectangle(rgb,(50,40),(270,140),(0,0,0),1)
    rgb[38:44,130:130+gap]=255
    old,_=propose_union(rgb,pixel_agreement=True)
    new,_=propose_union(rgb,pixel_agreement=True,boundary_gaps=True)
    assert len(new)==expected
    assert [c['bbox'] for c in new[:len(old)]]==[c['bbox'] for c in old]
    for c in new[len(old):]:assert c['raw_support_max_distance']<=np.sqrt(2)+1e-6


def test_gap_arm_does_not_promote_circle_or_text():
    rgb=np.full((360,640,3),255,np.uint8)
    cv2.ellipse(rgb,(160,90),(110,50),0,0,360,(0,0,0),1)
    cv2.putText(rgb,'DATA',(340,110),cv2.FONT_HERSHEY_SIMPLEX,2,(0,0,0),2)
    assert not propose_union(rgb,boundary_gaps=True)[0]
