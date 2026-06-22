from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("torch")

from image_to_editable_ppt.ml.relation_model import (
    CAND_DIM,
    FEATURE_DIM,
    GEOM_DIM,
    LINE_DIM,
    PATH_DIM,
    _Box,
    compute_node_components,
    pair_features,
    path_features,
    segment_line_features,
)


def _boxes():
    # two boxes side by side with a horizontal gap between them
    return _Box(10, 40, 30, 60), _Box(70, 40, 90, 60)


def test_feature_dims_match():
    assert FEATURE_DIM == GEOM_DIM + LINE_DIM + PATH_DIM + CAND_DIM
    bi, bj = _boxes()
    feats = pair_features(
        np.zeros((100, 100), np.uint8), np.zeros((100, 100), np.uint8), bi, bj, width=100, height=100
    )
    assert len(feats) == FEATURE_DIM


def test_path_connectivity_links_nodes_sharing_a_stroke():
    bi, bj = _boxes()
    line = np.zeros((100, 100), np.uint8)
    line[48:52, 28:73] = 1  # one stroke bridging the two boxes
    node_labels, fanout = compute_node_components(line, [bi, bj])
    assert path_features(node_labels[0], node_labels[1], fanout)[0] == 1.0
    # an empty mask shares no component
    nl, fo = compute_node_components(np.zeros((100, 100), np.uint8), [bi, bj])
    assert path_features(nl[0], nl[1], fo)[0] == 0.0


def test_line_coverage_high_when_stroke_present():
    bi, bj = _boxes()
    line = np.zeros((100, 100), np.uint8)
    # draw a segmented stroke along the gap between the two boxes (y=50, x in 30..70)
    line[48:52, 30:71] = 1
    feats = segment_line_features(line, np.zeros((100, 100), np.uint8), bi, bj)
    assert feats[0] > 0.6  # coverage


def test_line_coverage_low_when_no_stroke():
    bi, bj = _boxes()
    feats = segment_line_features(np.zeros((100, 100), np.uint8), np.zeros((100, 100), np.uint8), bi, bj)
    assert feats[0] == 0.0  # coverage


def test_arrowhead_feature_carries_direction():
    bi, bj = _boxes()
    line = np.zeros((100, 100), np.uint8)
    line[48:52, 30:71] = 1
    arrow = np.zeros((100, 100), np.uint8)
    arrow[45:55, 62:70] = 1  # arrowhead near the j (right) end
    feats = segment_line_features(line, arrow, bi, bj)
    arrow_i, arrow_j = feats[3], feats[4]
    assert arrow_j > arrow_i  # arrowhead at j -> edge points i->j
