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


def test_node_snaps_to_drawn_rectangle_so_interior_text_is_not_a_connector():
    """The real failure the user caught: a node whose detector box hugs the text is
    smaller than the drawn rectangle, so the interior text the box misses leaks out as
    a fake connector. The honest fix is to snap the node to its drawn rectangle (the
    detector owns *which* box, the classical rectangle owns *where*); filling the full
    rectangle erases the whole interior. No node-vs-panel classification is involved."""
    import pytest

    pytest.importorskip("cv2")
    import cv2
    import numpy as np

    from image_to_editable_ppt.ml.classical_connectors import (
        _Box,
        _snap_nodes_to_outlines,
        detect_box_outlines,
        extract_connectors_morphological,
    )

    img = np.full((200, 400, 3), 255, np.uint8)
    cv2.rectangle(img, (150, 80), (250, 120), 0, 2)  # the true (drawn) node box
    img[88:92, 160:240] = 0  # top text line (the detector box covers this)
    img[106:110, 160:240] = 0  # bottom text line (the detector box misses this)
    n = _Box(158, 84, 242, 98)  # detector box hugs only the top line
    # Two nodes flank the box, so any leaked horizontal stroke would bridge them.
    a, b = _Box(120, 100, 148, 116), _Box(252, 100, 280, 116)

    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    # The node snaps out to the full drawn rectangle (geometry from the classical rect).
    snapped = _snap_nodes_to_outlines([n], detect_box_outlines(gray))[0]
    assert snapped.y1 > 115 and snapped.x1 > 245  # grew down/right to the drawn box

    # ...so the bottom text line below the detector box is not read as a connector.
    edges = extract_connectors_morphological(img, [n, a, b])
    assert all({e.source, e.target} != {1, 2} for e in edges)


def test_nodes_inside_a_panel_do_not_snap_to_it():
    """A container around ellipse/text nodes has no inner rectangle, so it reads as a
    leaf. Nodes inside it must NOT snap to the panel — otherwise the panel gets filled
    and the connectors routed inside it are erased (the graph-with-container case)."""
    from image_to_editable_ppt.ml.classical_connectors import _Box, _snap_nodes_to_outlines

    panel = _Box(40, 40, 360, 200)
    a, b = _Box(70, 90, 150, 150), _Box(240, 90, 320, 150)  # two nodes inside the panel
    # Each node is fully inside the panel, but the panel also holds the other node, so
    # neither snaps: the result is the original detector boxes unchanged.
    assert _snap_nodes_to_outlines([a, b], [panel]) == [a, b]
    # A node whose own drawn rectangle bounds it alone still snaps.
    own = _Box(72, 92, 148, 148)
    assert _snap_nodes_to_outlines([a], [own]) == [own]


def test_overlapping_fragments_still_snap_to_their_shared_rectangle():
    """Detector over-segmentation (two overlapping boxes for one drawn box) must still
    snap both to that box, so its interior text is erased — overlap, not size, tells a
    fragmented node box apart from a panel of separate nodes."""
    from image_to_editable_ppt.ml.classical_connectors import _Box, _snap_nodes_to_outlines

    drawn = _Box(150, 80, 250, 120)
    f1, f2 = _Box(158, 86, 215, 100), _Box(190, 92, 242, 110)  # overlapping fragments
    assert _snap_nodes_to_outlines([f1, f2], [drawn]) == [drawn, drawn]


def test_edge_offset_zero_at_edge_midpoint_half_at_corner():
    """edge_off is a learned feature: ~0 when an endpoint lands at an edge midpoint
    (where real connectors attach), ~0.5 at a corner (where braces/decorations touch)."""
    from image_to_editable_ppt.ml.classical_connectors import _Box, _edge_offset

    b = _Box(100, 100, 200, 140)
    assert _edge_offset((96, 120), b) < 0.1  # beside the left-edge midpoint -> central
    assert _edge_offset((150, 96), b) < 0.1  # above the top-edge midpoint -> central
    assert _edge_offset((96, 102), b) > 0.4  # near the top-left corner -> off-centre


def test_panel_outline_is_not_a_snap_target():
    """A rectangle drawn around other boxes is a panel: a node inside must NOT snap to
    it (that would fill the panel and erase its inner connectors). Leaf-vs-panel is the
    drawn-nesting fact, not a size threshold."""
    import pytest

    pytest.importorskip("cv2")
    import numpy as np

    from image_to_editable_ppt.ml.classical_connectors import _Box, _leaf_outlines

    panel = _Box(40, 40, 360, 200)
    inner_a, inner_b = _Box(60, 70, 160, 150), _Box(220, 70, 330, 150)
    leaves = _leaf_outlines([panel, inner_a, inner_b])
    assert panel not in leaves
    assert inner_a in leaves and inner_b in leaves


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
