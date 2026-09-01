from __future__ import annotations

import cv2
import numpy as np

from image_to_editable_ppt.ml.annotation_schema import AnnotationBBox, AnnotationNode
from image_to_editable_ppt.ml.visual_geometry import detect_visual_geometry, reconcile_with_visual_geometry
from image_to_editable_ppt.v3.core.enums import NodeKind


def test_closed_outline_requires_four_observed_sides_and_ignores_curved_noise() -> None:
    image = np.full((180, 400, 3), 255, dtype=np.uint8)
    for y in (10, 75, 140):
        cv2.rectangle(image, (60, y), (280, y + 30), (0, 0, 0), 2)
    cv2.ellipse(image, (305, 60), (35, 45), 0, -80, 80, (0, 0, 0), 3)

    geometry = detect_visual_geometry(image)

    assert [candidate.bbox for candidate in geometry.nodes] == [
        (59, 9, 282, 42),
        (59, 74, 282, 107),
        (59, 139, 282, 172),
    ]
    assert geometry.containers == ()


def test_uniform_fill_opening_separates_nodes_from_thin_connectors() -> None:
    image = np.full((300, 800, 3), 255, dtype=np.uint8)
    fill = (217, 217, 217)
    for x0, x1 in ((40, 180), (230, 430), (480, 650)):
        cv2.rectangle(image, (x0, 80), (x1, 190), fill, -1)
    cv2.arrowedLine(image, (180, 135), (230, 135), fill, 2, tipLength=0.3)
    cv2.arrowedLine(image, (430, 135), (480, 135), fill, 2, tipLength=0.3)

    geometry = detect_visual_geometry(image)

    assert len(geometry.nodes) == 3
    assert all(candidate.source == "uniform_fill" for candidate in geometry.nodes)


def test_reconciliation_snaps_split_ml_boxes_to_one_observed_box() -> None:
    image = np.full((180, 400, 3), 255, dtype=np.uint8)
    for y in (10, 75, 140):
        cv2.rectangle(image, (60, y), (280, y + 30), (0, 0, 0), 2)
    ml_nodes = (
        AnnotationNode("node:0", NodeKind.BOX, AnnotationBBox(50, 5, 300, 45), 0.99),
        AnnotationNode("node:1", NodeKind.BOX, AnnotationBBox(60, 72, 180, 110), 0.95),
        AnnotationNode("node:2", NodeKind.BOX, AnnotationBBox(170, 72, 290, 110), 0.90),
        AnnotationNode("node:3", NodeKind.BOX, AnnotationBBox(55, 135, 295, 178), 0.99),
    )

    nodes, containers, used = reconcile_with_visual_geometry(
        image,
        ml_nodes,
        (),
        image_id="sample",
    )

    assert used is True
    assert len(nodes) == 3
    assert containers == ()
    assert [(node.bbox.x0, node.bbox.y0, node.bbox.x1, node.bbox.y1) for node in nodes] == [
        (59.0, 9.0, 282.0, 42.0),
        (59.0, 74.0, 282.0, 107.0),
        (59.0, 139.0, 282.0, 172.0),
    ]


def test_small_document_icon_is_below_visual_structure_floor() -> None:
    image = np.full((1000, 1600, 3), 255, dtype=np.uint8)
    cv2.rectangle(image, (200, 200), (500, 340), (0, 0, 0), 3)
    cv2.rectangle(image, (600, 200), (900, 340), (0, 0, 0), 3)
    cv2.rectangle(image, (200, 600), (275, 685), (0, 0, 0), 4)

    geometry = detect_visual_geometry(image)

    assert len(geometry.nodes) == 2
    assert all(candidate.area > 30_000 for candidate in geometry.nodes)


def test_nested_outline_is_container_even_with_one_recovered_child() -> None:
    image = np.full((400, 600, 3), 255, dtype=np.uint8)
    cv2.rectangle(image, (20, 20), (580, 250), (0, 0, 0), 3)
    cv2.rectangle(image, (180, 90), (420, 190), (0, 0, 0), 3)

    geometry = detect_visual_geometry(image)

    assert len(geometry.containers) == 1
    assert len(geometry.nodes) == 1
    assert geometry.containers[0].area > geometry.nodes[0].area


def test_header_divider_marks_empty_titled_panel_as_container() -> None:
    image = np.full((400, 600, 3), 255, dtype=np.uint8)
    cv2.rectangle(image, (20, 20), (580, 250), (0, 0, 0), 3)
    cv2.line(image, (22, 72), (578, 72), (0, 0, 0), 3)

    geometry = detect_visual_geometry(image)

    assert len(geometry.containers) == 1
    assert geometry.nodes == ()


def test_large_closed_ellipses_become_editable_ellipse_nodes() -> None:
    image = np.full((320, 640, 3), 255, dtype=np.uint8)
    cv2.ellipse(image, (170, 160), (100, 55), 0, 0, 360, (0, 0, 0), 3)
    cv2.ellipse(image, (470, 160), (100, 55), 0, 0, 360, (0, 0, 0), 3)

    geometry = detect_visual_geometry(image)
    nodes, _, used = reconcile_with_visual_geometry(image, (), (), image_id="ellipses")

    assert len(geometry.nodes) == 2
    assert all(candidate.source == "closed_ellipse" for candidate in geometry.nodes)
    assert used is True
    assert all(node.kind is NodeKind.ELLIPSE for node in nodes)


def test_multiple_titled_panels_are_coherent_without_inner_nodes() -> None:
    image = np.full((500, 700, 3), 255, dtype=np.uint8)
    for y0, y1 in ((20, 210), (270, 460)):
        cv2.rectangle(image, (20, y0), (680, y1), (0, 0, 0), 3)
        cv2.line(image, (22, y0 + 45), (678, y0 + 45), (0, 0, 0), 3)

    nodes, containers, used = reconcile_with_visual_geometry(image, (), (), image_id="panels")

    assert used is True
    assert nodes == ()
    assert len(containers) == 2


def test_repeated_small_wide_boxes_are_recovered_only_inside_confirmed_panel() -> None:
    image = np.full((600, 900, 3), 255, dtype=np.uint8)
    cv2.rectangle(image, (20, 20), (880, 580), (0, 0, 0), 3)
    cv2.line(image, (22, 90), (878, 90), (0, 0, 0), 3)
    for x0, y0 in ((100, 170), (260, 170), (420, 170), (260, 300), (420, 300)):
        cv2.rectangle(image, (x0, y0), (x0 + 105, y0 + 25), (0, 0, 0), 2)
    # The same small outline outside a titled panel remains below the global
    # structure floor and must not become an isolated diagram node.
    cv2.rectangle(image, (730, 5), (835, 30), (0, 0, 0), 2)

    geometry = detect_visual_geometry(image)

    assert len(geometry.containers) == 1
    assert len(geometry.nodes) == 5
    assert all(candidate.source == "panel_closed_outline" for candidate in geometry.nodes)
