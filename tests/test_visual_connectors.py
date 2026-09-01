from __future__ import annotations

import cv2
import numpy as np

from image_to_editable_ppt.ml.annotation_schema import AnnotationBBox, AnnotationContainer, AnnotationNode
from image_to_editable_ppt.ml.visual_connectors import visual_connectors
from image_to_editable_ppt.v3.core.enums import (
    ConnectorKind,
    ContainerKind,
    NodeKind,
    PortOwnerKind,
    PortSide,
)


def _node(index: int, x0: int, y0: int, x1: int, y1: int) -> AnnotationNode:
    return AnnotationNode(
        id=f"node:test:{index}",
        kind=NodeKind.BOX,
        bbox=AnnotationBBox(float(x0), float(y0), float(x1), float(y1)),
        confidence=1.0,
        source="test",
    )


def _container(index: int, x0: int, y0: int, x1: int, y1: int) -> AnnotationContainer:
    return AnnotationContainer(
        id=f"container:test:{index}",
        kind=ContainerKind.FLOW_CLUSTER,
        bbox=AnnotationBBox(float(x0), float(y0), float(x1), float(y1)),
        confidence=1.0,
        source="test",
    )


def test_keeps_direct_vertical_arrows_and_omits_external_curve() -> None:
    image = np.full((220, 320, 3), 255, dtype=np.uint8)
    nodes = [_node(0, 70, 10, 250, 55), _node(1, 70, 90, 250, 135), _node(2, 70, 170, 250, 215)]
    for node in nodes:
        box = node.bbox
        cv2.rectangle(image, (int(box.x0), int(box.y0)), (int(box.x1), int(box.y1)), (0, 0, 0), 2)
    cv2.arrowedLine(image, (160, 55), (160, 90), (0, 0, 0), 2, tipLength=0.28)
    cv2.arrowedLine(image, (160, 135), (160, 170), (0, 0, 0), 2, tipLength=0.28)
    cv2.ellipse(image, (270, 74), (25, 24), -10, -75, 80, (0, 0, 0), 2)

    connectors, _ = visual_connectors(image, nodes, image_id="test")

    assert len(connectors) == 2
    assert all(connector.kind is ConnectorKind.ARROW for connector in connectors)
    assert all(connector.start_endpoint.side is PortSide.BOTTOM for connector in connectors)
    assert all(connector.end_endpoint.side is PortSide.TOP for connector in connectors)


def test_recovers_both_horizontal_directions_from_arrowhead_width() -> None:
    image = np.full((130, 430, 3), 255, dtype=np.uint8)
    nodes = [_node(0, 10, 20, 100, 110), _node(1, 170, 20, 260, 110), _node(2, 330, 20, 420, 110)]
    for node in nodes:
        box = node.bbox
        cv2.rectangle(image, (int(box.x0), int(box.y0)), (int(box.x1), int(box.y1)), (210, 210, 210), -1)
    cv2.arrowedLine(image, (100, 65), (170, 65), (110, 110, 110), 8, tipLength=0.30)
    cv2.arrowedLine(image, (330, 65), (260, 65), (110, 110, 110), 8, tipLength=0.30)

    connectors, _ = visual_connectors(image, nodes, image_id="test")

    assert len(connectors) == 2
    assert connectors[0].start_endpoint.owner_id == nodes[0].id
    assert connectors[0].end_endpoint.owner_id == nodes[1].id
    assert connectors[1].start_endpoint.owner_id == nodes[2].id
    assert connectors[1].end_endpoint.owner_id == nodes[1].id


def test_does_not_promote_disconnected_gap_text_or_panel_border() -> None:
    image = np.full((180, 300, 3), 255, dtype=np.uint8)
    nodes = [_node(0, 10, 20, 90, 100), _node(1, 210, 20, 290, 100)]
    cv2.putText(image, "label", (110, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1)
    cv2.line(image, (0, 115), (299, 115), (0, 0, 0), 4)

    connectors, _ = visual_connectors(image, nodes, image_id="test")

    assert connectors == ()


def test_vertical_arrow_survives_crossing_panel_rules() -> None:
    image = np.full((230, 220, 3), 255, dtype=np.uint8)
    nodes = [_node(0, 60, 10, 200, 70), _node(1, 60, 170, 200, 225)]
    cv2.arrowedLine(image, (150, 70), (150, 170), (100, 100, 100), 5, tipLength=0.22)
    cv2.line(image, (0, 95), (219, 95), (90, 90, 90), 5)
    cv2.line(image, (0, 135), (219, 135), (90, 90, 90), 5)

    connectors, _ = visual_connectors(image, nodes, image_id="test")

    assert len(connectors) == 1
    assert connectors[0].kind is ConnectorKind.ARROW
    assert connectors[0].start_endpoint.owner_id == nodes[0].id
    assert connectors[0].end_endpoint.owner_id == nodes[1].id


def test_container_bridge_uses_open_lane_beside_intervening_panel() -> None:
    image = np.full((500, 600, 3), 255, dtype=np.uint8)
    containers = [
        _container(0, 20, 20, 400, 100),
        _container(1, 100, 180, 300, 300),
        _container(2, 20, 400, 550, 480),
    ]
    for container in containers:
        box = container.bbox
        cv2.rectangle(image, (int(box.x0), int(box.y0)), (int(box.x1), int(box.y1)), (0, 0, 0), 2)
    cv2.arrowedLine(image, (55, 100), (55, 400), (0, 0, 0), 4, tipLength=0.08)

    connectors, ports = visual_connectors(image, (), containers=containers, image_id="test")

    assert len(connectors) == 1
    assert connectors[0].start_endpoint.owner_id == containers[0].id
    assert connectors[0].end_endpoint.owner_id == containers[2].id
    assert connectors[0].start_endpoint.owner_kind is PortOwnerKind.CONTAINER
    assert connectors[0].end_endpoint.owner_kind is PortOwnerKind.CONTAINER
    assert all(port.owner_kind is PortOwnerKind.CONTAINER for port in ports)


def test_container_bridge_does_not_bypass_intervening_node() -> None:
    image = np.full((500, 600, 3), 255, dtype=np.uint8)
    containers = [_container(0, 20, 20, 400, 100), _container(1, 20, 400, 550, 480)]
    blocker = _node(0, 35, 180, 75, 300)
    for owner in (*containers, blocker):
        box = owner.bbox
        cv2.rectangle(image, (int(box.x0), int(box.y0)), (int(box.x1), int(box.y1)), (0, 0, 0), 2)
    cv2.arrowedLine(image, (55, 100), (55, 400), (0, 0, 0), 4, tipLength=0.08)

    connectors, _ = visual_connectors(image, (blocker,), containers=containers, image_id="test")

    assert connectors == ()
