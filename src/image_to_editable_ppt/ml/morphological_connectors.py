"""Morphological connectors -> annotation candidates (the live connector path).

Real-figure measurement (2026-07-04): the pure relation model (run-rel8) and the
learned segmenter both under-recover connectors on real paper figures and place
edges by a geometry prior, while ``extract_connectors_morphological`` — classical
ink-component tracing — recovers essentially every drawn connector along its
actual route. So the live provider path builds connectors from the morphological
extractor. This module adapts its ``ClassicalEdge`` output into the same
``(AnnotationConnectorCandidate, AnnotationPort)`` shape the segmenter path emits,
so the downstream adapter/emit pipeline is unchanged, and adds two refinements:

- direction: a conservative classical arrowhead check at each end (the extractor
  is direction-agnostic; it orders endpoints by index, not by the drawn arrow);
- route cleanup: near-axis segments snapped to orthogonal so the editable PPT
  connector is a clean elbow rather than the pixel-jagged traced path.

Both refinements only fire when the evidence is clear; otherwise the connector
stays undirected / keeps its traced route (correctness over prettiness).
"""
from __future__ import annotations

from typing import Sequence

import numpy as np

from image_to_editable_ppt.ml.annotation_schema import (
    AnnotationBBox,
    AnnotationConnectorCandidate,
    AnnotationConnectorEndpoint,
    AnnotationNode,
    AnnotationPoint,
    AnnotationPort,
)
from image_to_editable_ppt.ml.classical_connectors import ClassicalEdge, extract_connectors_morphological
from image_to_editable_ppt.ml.connector_segmenter import _port, _side_toward
from image_to_editable_ppt.v3.core.enums import ConnectorKind, PortOwnerKind


def morphological_connectors(
    image: np.ndarray,
    nodes: Sequence[AnnotationNode],
    containers: Sequence[object] = (),
    *,
    image_id: str,
    orient: bool = True,
    orthogonal: bool = True,
) -> tuple[tuple[AnnotationConnectorCandidate, ...], tuple[AnnotationPort, ...]]:
    """Connector candidates + ports from the morphological extractor."""
    node_list = list(nodes)
    if len(node_list) < 2:
        return (), ()
    edges = extract_connectors_morphological(image, node_list, list(containers))
    if not edges:
        return (), ()

    import cv2

    rgb = np.asarray(image)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY) if rgb.ndim == 3 else rgb

    connectors: list[AnnotationConnectorCandidate] = []
    ports: list[AnnotationPort] = []
    for index, edge in enumerate(edges):
        start_node, end_node = node_list[edge.source], node_list[edge.target]
        polyline = [(float(x), float(y)) for x, y in edge.polyline]
        if len(polyline) < 2:
            continue

        head = _arrowhead_end(gray, polyline, start_node.bbox, end_node.bbox) if orient else None
        if head == "start":
            # Arrow points back at the source end: the edge runs end -> start.
            start_node, end_node = end_node, start_node
            polyline = polyline[::-1]
        directed = head is not None

        if orthogonal:
            polyline = _orthogonalize(polyline)

        start_pt = AnnotationPoint(*polyline[0])
        end_pt = AnnotationPoint(*polyline[-1])
        start_center = _center(end_node.bbox)  # side faces the partner node
        end_center = _center(start_node.bbox)
        start_side = _side_toward(start_node, start_center)
        end_side = _side_toward(end_node, end_center)

        connector_id = f"connector:{image_id}:{index}"
        connectors.append(
            AnnotationConnectorCandidate(
                id=connector_id,
                kind=ConnectorKind.ARROW if directed else ConnectorKind.LINE,
                bbox=_polyline_bbox(polyline),
                confidence=1.0,
                source_evidence_id=f"evidence:{connector_id}",
                path_points=tuple(AnnotationPoint(x, y) for x, y in polyline),
                start_endpoint=AnnotationConnectorEndpoint(
                    point=start_pt, owner_id=start_node.id, owner_kind=PortOwnerKind.NODE, side=start_side,
                ),
                end_endpoint=AnnotationConnectorEndpoint(
                    point=end_pt, owner_id=end_node.id, owner_kind=PortOwnerKind.NODE, side=end_side,
                ),
                arrowhead_end=directed,
                source="morphological",
                provenance=("morphological:ink_component",) + (("morphological:arrowhead",) if directed else ()),
            )
        )
        ports.append(_port(start_node.id, image_id, index, "start", start_side, start_pt))
        ports.append(_port(end_node.id, image_id, index, "end", end_side, end_pt))
    return tuple(connectors), tuple(ports)


def _center(bbox) -> tuple[float, float]:
    return ((bbox.x0 + bbox.x1) / 2.0, (bbox.y0 + bbox.y1) / 2.0)


def _polyline_bbox(polyline: list[tuple[float, float]], *, pad: float = 3.0) -> AnnotationBBox:
    xs = [p[0] for p in polyline]
    ys = [p[1] for p in polyline]
    return AnnotationBBox(x0=min(xs) - pad, y0=min(ys) - pad, x1=max(xs) + pad, y1=max(ys) + pad)


def _arrowhead_end(
    gray: np.ndarray,
    polyline: list[tuple[float, float]],
    box_start,
    box_end,
    *,
    ink_threshold: int = 140,
    radius: int = 9,
    min_excess: float = 8.0,
    ratio: float = 1.5,
) -> str | None:
    """Which end (if any) carries an arrowhead, from ink mass at the two tips.

    An arrowhead is a triangular ink cluster wider than the ~2px shaft, so it packs
    more dark pixels into a small disc at that tip than the plain end does. Only
    call a direction when one tip clearly out-masses the other (absolute and ratio
    margins); otherwise return None and let the connector stay undirected — a guess
    at direction is worse than an honest plain line.
    """
    start_ink = _tip_ink(gray, polyline[0], ink_threshold=ink_threshold, radius=radius)
    end_ink = _tip_ink(gray, polyline[-1], ink_threshold=ink_threshold, radius=radius)
    if end_ink >= start_ink * ratio and end_ink - start_ink >= min_excess:
        return "end"
    if start_ink >= end_ink * ratio and start_ink - end_ink >= min_excess:
        return "start"
    return None


def _tip_ink(gray: np.ndarray, point: tuple[float, float], *, ink_threshold: int, radius: int) -> float:
    h, w = gray.shape[:2]
    cx, cy = int(round(point[0])), int(round(point[1]))
    x0, x1 = max(0, cx - radius), min(w, cx + radius + 1)
    y0, y1 = max(0, cy - radius), min(h, cy + radius + 1)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    window = gray[y0:y1, x0:x1]
    return float((window < ink_threshold).sum())


def _orthogonalize(polyline: list[tuple[float, float]], *, axis_tol: float = 0.34) -> list[tuple[float, float]]:
    """Snap near-axis segments to exactly horizontal/vertical, keeping corners.

    The traced route follows ink pixel-by-pixel, so straight runs come back
    slightly wobbly. For each segment within ``axis_tol`` of an axis (|minor| <=
    tol*|major|), align it; corners between an aligned H and V segment then meet
    cleanly. Diagonal segments (a genuine slanted connector) are left untouched.
    """
    if len(polyline) < 2:
        return polyline
    pts = [list(p) for p in polyline]
    for i in range(len(pts) - 1):
        ax, ay = pts[i]
        bx, by = pts[i + 1]
        dx, dy = abs(bx - ax), abs(by - ay)
        if dx >= dy and dy <= axis_tol * dx:  # near-horizontal -> shared y
            y = (ay + by) / 2.0
            pts[i][1] = pts[i + 1][1] = y
        elif dy > dx and dx <= axis_tol * dy:  # near-vertical -> shared x
            x = (ax + bx) / 2.0
            pts[i][0] = pts[i + 1][0] = x
    # Drop points that became coincident/collinear after snapping.
    cleaned: list[tuple[float, float]] = [(pts[0][0], pts[0][1])]
    for x, y in pts[1:]:
        if abs(x - cleaned[-1][0]) < 0.5 and abs(y - cleaned[-1][1]) < 0.5:
            continue
        cleaned.append((x, y))
    return cleaned if len(cleaned) >= 2 else [tuple(pts[0]), tuple(pts[-1])]
