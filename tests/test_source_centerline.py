import cv2
import numpy as np
import pytest

from image_to_editable_ppt.research.source_centerline import fit_observed_line, segment_hits_box


def pixels_for(path, scale=1):
    mask = np.zeros((round(240*scale), round(240*scale)), np.uint8)
    p = np.rint(np.asarray(path)*scale).astype(np.int32)
    cv2.polylines(mask, [p], False, 1, max(1, round(3*scale)))
    yy, xx = np.where(mask)
    return np.column_stack([xx, yy])


CASES = [
    ([(35, 50), (175, 50)], [[10, 40, 30, 60], [180, 40, 200, 60]], [[30, 50], [180, 50]]),
    ([(50, 35), (50, 175)], [[40, 10, 60, 30], [40, 180, 60, 200]], [[50, 30], [50, 180]]),
    ([(35, 35), (175, 175)], [[10, 10, 30, 30], [180, 180, 200, 200]], [[30, 30], [180, 180]]),
    ([(35, 175), (175, 35)], [[10, 180, 30, 200], [180, 10, 200, 30]], [[30, 180], [180, 30]]),
]


@pytest.mark.parametrize('case', CASES)
@pytest.mark.parametrize('scale', [.75, 1., 1.5])
@pytest.mark.parametrize('reverse', [False, True])
def test_clean_source_lines(case, scale, reverse):
    path, boxes, endpoints = case
    boxes, endpoints = np.array(boxes)*scale, np.array(endpoints)*scale
    if reverse:
        boxes, endpoints = boxes[::-1], endpoints[::-1]
    result, audit = fit_observed_line(pixels_for(path, scale), boxes, endpoints, scale=scale)
    assert result is not None, audit
    assert audit['decision'] == 'refined'
    for p, expected in zip(result, endpoints, strict=True):
        assert [p.x, p.y] == pytest.approx(expected, abs=.8)


@pytest.mark.parametrize('mode', ['empty', 'short', 'gap', 'elbow', 'curve', 'parallel',
                                  'miss', 'move', 'extension', 'third'])
def test_negative_controls_abstain(mode):
    path, boxes, endpoints = CASES[0]
    points = pixels_for(path)
    others = []
    if mode == 'empty': points = np.empty((0, 2))
    elif mode == 'short': points = pixels_for([(90, 50), (100, 50)])
    elif mode == 'gap': points = points[(points[:, 0] < 85) | (points[:, 0] > 105)]
    elif mode == 'elbow': points = pixels_for([(35, 50), (110, 50), (110, 100), (175, 100)])
    elif mode == 'curve': points = pixels_for([(35, 50), (60, 65), (100, 80), (140, 65), (175, 50)])
    elif mode == 'parallel': points = np.concatenate([points+[0, -8], points+[0, 8]])
    elif mode == 'miss': boxes = [[10, 65, 30, 80], boxes[1]]
    elif mode == 'move': endpoints = [[30, 59], endpoints[1]]
    elif mode == 'extension': points = pixels_for([(55, 50), (155, 50)])
    elif mode == 'third': others = [[90, 45, 100, 55]]
    result, audit = fit_observed_line(points, boxes, np.array(endpoints), scale=1, other_boxes=others)
    assert result is None, (mode, audit)


def test_segment_bounds_not_infinite_line():
    assert segment_hits_box(np.array([10, 10]), np.array([50, 50]), [20, 20, 30, 30])
    assert not segment_hits_box(np.array([10, 10]), np.array([50, 50]), [60, 60, 80, 80])
