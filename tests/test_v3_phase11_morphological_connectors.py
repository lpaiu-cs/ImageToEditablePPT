"""Phase 11: morphological connector extraction as the live provider path."""
from __future__ import annotations

import numpy as np

from image_to_editable_ppt.ml.annotation_schema import AnnotationBBox, AnnotationNode
from image_to_editable_ppt.ml.morphological_connectors import (
    _arrowhead_end,
    _orthogonalize,
    morphological_connectors,
)
from image_to_editable_ppt.v3.core.enums import ConnectorKind, NodeKind, PortOwnerKind


def _two_box_image_with_connector(*, arrow: bool):
    """White 200x120 image: two boxes joined by a horizontal line; optional arrowhead
    triangle at the right box (so direction is recoverable)."""
    import cv2

    img = np.full((120, 200, 3), 255, dtype=np.uint8)
    cv2.rectangle(img, (20, 40), (70, 80), (0, 0, 0), 2)   # left node
    cv2.rectangle(img, (130, 40), (180, 80), (0, 0, 0), 2)  # right node
    cv2.line(img, (70, 60), (130, 60), (0, 0, 0), 2)        # connector
    if arrow:
        cv2.fillPoly(img, [np.array([(130, 60), (118, 53), (118, 67)])], (0, 0, 0))  # arrowhead at right
    nodes = (
        AnnotationNode(id="node:0", kind=NodeKind.BOX, bbox=AnnotationBBox(20, 40, 70, 80), confidence=0.9),
        AnnotationNode(id="node:1", kind=NodeKind.BOX, bbox=AnnotationBBox(130, 40, 180, 80), confidence=0.9),
    )
    return img, nodes


def test_morphological_connectors_recovers_edge_between_two_nodes():
    img, nodes = _two_box_image_with_connector(arrow=False)
    connectors, ports = morphological_connectors(img, nodes, image_id="t")
    assert len(connectors) == 1
    connector = connectors[0]
    owners = {connector.start_endpoint.owner_id, connector.end_endpoint.owner_id}
    assert owners == {"node:0", "node:1"}
    assert connector.start_endpoint.owner_kind is PortOwnerKind.NODE
    # two ports (one per endpoint), each owned by a node
    assert len(ports) == 2
    assert {p.owner_id for p in ports} == {"node:0", "node:1"}


def test_morphological_connectors_orients_by_arrowhead():
    img, nodes = _two_box_image_with_connector(arrow=True)
    connectors, _ = morphological_connectors(img, nodes, image_id="t")
    assert len(connectors) == 1
    connector = connectors[0]
    # arrowhead is at the right node -> directed edge ending at node:1
    assert connector.arrowhead_end is True
    assert connector.kind is ConnectorKind.ARROW
    assert connector.end_endpoint.owner_id == "node:1"


def test_morphological_connectors_undirected_without_arrowhead():
    img, nodes = _two_box_image_with_connector(arrow=False)
    connectors, _ = morphological_connectors(img, nodes, image_id="t")
    connector = connectors[0]
    # no arrowhead evidence -> honest plain line, not a guessed direction
    assert connector.arrowhead_end is False
    assert connector.kind is ConnectorKind.LINE


def test_morphological_connectors_needs_two_nodes():
    img, nodes = _two_box_image_with_connector(arrow=False)
    assert morphological_connectors(img, nodes[:1], image_id="t") == ((), ())


def test_arrowhead_end_picks_denser_tip():
    gray = np.full((60, 120), 255, dtype=np.uint8)
    gray[28:32, 10:100] = 0            # shaft
    gray[20:40, 95:105] = 0            # dense blob (arrowhead) at the right tip
    assert _arrowhead_end(gray, [(10.0, 30.0), (100.0, 30.0)], None, None) == "end"
    assert _arrowhead_end(gray, [(100.0, 30.0), (10.0, 30.0)], None, None) == "start"


def test_arrowhead_end_returns_none_when_symmetric():
    gray = np.full((60, 120), 255, dtype=np.uint8)
    gray[28:32, 10:100] = 0            # plain shaft, no arrowhead
    assert _arrowhead_end(gray, [(10.0, 30.0), (100.0, 30.0)], None, None) is None


def test_orthogonalize_snaps_near_axis_and_keeps_diagonal():
    # near-horizontal wobble -> flat
    snapped = _orthogonalize([(0.0, 10.0), (100.0, 12.0)])
    assert abs(snapped[0][1] - snapped[-1][1]) < 0.5
    # a real diagonal is preserved
    diagonal = _orthogonalize([(0.0, 0.0), (100.0, 100.0)])
    assert abs(diagonal[-1][1] - diagonal[0][1]) > 50


def test_provider_honors_requested_strategy_without_silent_fallback():
    """Requesting 'relation' with no relation checkpoint must NOT silently run the
    segmenter (which would corrupt strategy experiments): it warns and emits no
    connectors even though a segmenter checkpoint is present."""
    import warnings

    from image_to_editable_ppt.ml.slide_ir_provider import MLSlideIRProvider

    provider = MLSlideIRProvider(
        detector_checkpoint="unused.ckpt",
        connector_checkpoint="segmenter.ckpt",  # present, but must not be used
        connector_strategy="relation",
        relation_checkpoint=None,  # requested strategy's checkpoint is missing
    )
    img, nodes = _two_box_image_with_connector(arrow=False)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        connectors, ports = provider._recover_connectors(img, nodes, ())

    assert connectors == () and ports == ()  # no segmenter substitution
    assert any("relation" in str(w.message) for w in caught)


def test_provider_morphological_strategy_recovers_connectors():
    """The default strategy runs the morphological extractor (no checkpoints needed)."""
    from image_to_editable_ppt.ml.slide_ir_provider import MLSlideIRProvider

    provider = MLSlideIRProvider(detector_checkpoint="unused.ckpt", connector_strategy="morphological")
    img, nodes = _two_box_image_with_connector(arrow=True)
    connectors, ports = provider._recover_connectors(img, nodes, ())
    assert len(connectors) == 1
    assert connectors[0].arrowhead_end is True
