import cv2
import numpy as np
import pytest

from image_to_editable_ppt.research.source_centerline_v2 import fit_observed_line, segment_hits_box


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


def raster_endpoints(path, boxes, scale):
    # Independent analytic clipping of the integer points given to the rasterizer.
    q = np.rint(np.asarray(path)*scale)
    direction = q[1]-q[0]
    result = []
    for i, box in enumerate(boxes):
        lo, hi = -float('inf'), float('inf')
        for axis in (0, 1):
            if direction[axis] == 0:
                assert box[axis] <= q[0, axis] <= box[axis+2]
            else:
                a, b = sorted([(box[axis]-q[0, axis])/direction[axis],
                               (box[axis+2]-q[0, axis])/direction[axis]])
                lo, hi = max(lo, a), min(hi, b)
        assert lo <= hi
        result.append(q[0]+(hi if i == 0 else lo)*direction)
    return result


@pytest.mark.parametrize('case', CASES)
@pytest.mark.parametrize('scale', [.75, 1., 1.5])
@pytest.mark.parametrize('reverse', [False, True])
def test_clean_source_lines(case, scale, reverse):
    path, boxes, endpoints = case
    boxes, endpoints = np.array(boxes)*scale, np.array(endpoints)*scale
    expected_points = raster_endpoints(path, boxes, scale)
    if reverse:
        boxes, endpoints = boxes[::-1], endpoints[::-1]
        expected_points.reverse()
    result, audit = fit_observed_line(pixels_for(path, scale), boxes, endpoints, scale=scale)
    assert result is not None, audit
    assert audit['decision'] == 'refined'
    for p, expected in zip(result, expected_points, strict=True):
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



@pytest.mark.parametrize('gapped', [False, True])
def test_physical_pixel_support(gapped):
    from image_to_editable_ppt.research.source_centerline_v2 import pixel_cell_support
    positions = np.arange(100, dtype=float)
    if gapped:
        positions = positions[(positions < 40) | (positions > 60)]
    coverage, gap = pixel_cell_support(positions, np.array([1., 0.]))
    if gapped:
        assert coverage < .9 and gap > 2
    else:
        assert coverage == pytest.approx(1.) and gap == 0


@pytest.mark.parametrize('mode', ['eligible', 'ordinary', 'directed', 'multi', 'fanout', 'other_source'])
def test_wrapper_changes_only_path_within_scope(monkeypatch, mode):
    from dataclasses import replace
    import image_to_editable_ppt.research.source_centerline_v2 as module
    from image_to_editable_ppt.v3.core.enums import NodeKind, PortOwnerKind, ConnectorKind
    from image_to_editable_ppt.v3.core.types import BBox, ImageSize, Point
    from image_to_editable_ppt.v3.emit.models import EmitScene, EmitShapePrimitive, EmitConnectorPrimitive
    shapes = tuple(EmitShapePrimitive(k, PortOwnerKind.NODE, NodeKind.LABEL_ANCHOR,
        BBox(*b), .9, label=k) for k,b in [('a',[10,40,30,60]),('b',[180,40,200,60])])
    edge = EmitConnectorPrimitive('e', ConnectorKind.LINE, .8, 'a', PortOwnerKind.NODE,
        'b', PortOwnerKind.NODE, 'p0','p1',path_points=(Point(30,51),Point(90,49),Point(180,51)),
        source='r3_stroke_trace')
    contacts = ['a','b']
    if mode == 'ordinary': shapes = (replace(shapes[0],shape_kind=NodeKind.BOX),shapes[1])
    if mode == 'directed': edge = replace(edge,arrowhead_end=True)
    if mode == 'other_source': edge = replace(edge,source='r5_straight_fanout')
    if mode == 'multi': contacts.append('c')
    edges = (edge,) if mode != 'fanout' else (edge,replace(edge,id='e2'))
    scene = EmitScene(ImageSize(240,240),shapes=shapes,connectors=edges)
    audit = {'components':[dict(connector_id=e.id,component=1,owners=contacts) for e in edges]}
    mask = np.zeros((240,240),np.uint8)
    mask[50,35:176] = 1
    monkeypatch.setattr(module,'trace_scene',lambda *a,**k:(scene,audit,mask))
    monkeypatch.setattr(module,'stroke_mask',lambda *a:mask)
    calls = []
    def fit(*a,**k):
        calls.append(True)
        return (Point(30,50),Point(180,50)),dict(decision='refined')
    monkeypatch.setattr(module,'fit_observed_line',fit)
    updated, original, evidence = module.trace_with_centerlines(scene,np.zeros((240,240,3),np.uint8))
    assert original is scene and updated.shapes == shapes
    if mode == 'eligible':
        assert len(calls) == 1
        assert updated.connectors == (replace(edge,path_points=(Point(30,50),Point(180,50))),)
    else:
        assert not calls and updated == scene
