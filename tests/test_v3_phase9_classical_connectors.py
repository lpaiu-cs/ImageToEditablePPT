from __future__ import annotations

from image_to_editable_ppt.ml.classical_connectors import (
    _Box,
    filter_connector_segments,
)


def test_filter_keeps_inter_node_segment():
    # two boxes with a horizontal gap; a stroke spanning the gap is a connector
    a, b = _Box(10, 40, 30, 60), _Box(80, 40, 100, 60)
    seg = (30.0, 50.0, 80.0, 50.0)  # between the boxes
    assert filter_connector_segments([seg], [a, b]) == [seg]


def test_filter_drops_box_outline_segment():
    a = _Box(10, 40, 60, 80)
    top_edge = (10.0, 40.0, 60.0, 40.0)  # runs along the box's top edge
    left_edge = (10.0, 40.0, 10.0, 80.0)
    assert filter_connector_segments([top_edge, left_edge], [a]) == []


def test_filter_drops_segment_inside_node():
    a = _Box(10, 40, 90, 80)
    inside = (30.0, 60.0, 70.0, 62.0)  # a text stroke inside the box
    assert filter_connector_segments([inside], [a]) == []


def test_filter_drops_too_short_segments():
    a, b = _Box(10, 40, 30, 60), _Box(80, 40, 100, 60)
    tiny = (45.0, 50.0, 50.0, 50.0)  # 5px, below min_length
    assert filter_connector_segments([tiny], [a, b]) == []


def test_morphological_extractor_links_two_boxes_via_a_drawn_line():
    import pytest

    pytest.importorskip("cv2")
    import numpy as np

    from image_to_editable_ppt.ml.classical_connectors import _Box, extract_connectors_morphological

    img = np.full((200, 300, 3), 255, np.uint8)
    a, b = _Box(20, 90, 70, 130), _Box(230, 90, 280, 130)
    # a black connector stroke from box a's right edge to box b's left edge
    img[108:112, 70:230] = 0
    edges = extract_connectors_morphological(img, [a, b])
    assert len(edges) == 1
    assert {edges[0].source, edges[0].target} == {0, 1}


def test_detect_box_outlines_finds_a_drawn_rectangle():
    import pytest

    pytest.importorskip("cv2")
    import numpy as np

    from image_to_editable_ppt.ml.classical_connectors import detect_box_outlines

    img = np.full((200, 300), 255, np.uint8)
    img[50:150, 80:220] = 255
    import cv2

    cv2.rectangle(img, (80, 50), (220, 150), 0, 2)  # a drawn box outline
    rects = detect_box_outlines(img)
    assert any(abs(r.x0 - 80) < 6 and abs(r.x1 - 220) < 6 and abs(r.y0 - 50) < 6 and abs(r.y1 - 150) < 6 for r in rects)
