from __future__ import annotations

from dataclasses import dataclass
import math

import cv2
import numpy as np

from image_to_editable_ppt.v3.app.config import V3Config
from image_to_editable_ppt.v3.core.enums import ConnectorKind, ConnectorOrientation
from image_to_editable_ppt.v3.core.types import BBox, Point
from image_to_editable_ppt.v3.ir.models import ConnectorEvidence, DiagramContainer, DiagramInstance, DiagramNode, ResidualStructuralCanvas


@dataclass(slots=True, frozen=True)
class OrthogonalConnectorEvidenceExtractor:
    def extract(
        self,
        canvas: ResidualStructuralCanvas,
        *,
        instances: tuple[DiagramInstance, ...],
        config: V3Config,
    ) -> tuple[ConnectorEvidence, ...]:
        del config
        if not instances:
            return ()

        mask = _ink_mask(canvas.image)
        line_segments = cv2.HoughLinesP(
            mask,
            rho=1,
            theta=np.pi / 180.0,
            threshold=max(12, min(canvas.image.shape[:2]) // 9),
            minLineLength=max(12, min(canvas.image.shape[:2]) // 14),
            maxLineGap=6,
        )
        if line_segments is None:
            return ()
        arrowhead_hints = _find_arrowhead_hints(mask, line_segments)

        all_nodes = tuple(node for instance in instances for node in instance.nodes)
        all_containers = tuple(container for instance in instances for container in instance.containers)
        evidence_by_key: dict[tuple[tuple[int, int], tuple[int, int]], ConnectorEvidence] = {}

        for segment in line_segments[:, 0, :]:
            x0, y0, x1, y1 = (int(value) for value in segment)
            start = Point(float(x0), float(y0))
            end = Point(float(x1), float(y1))
            orientation = _classify_orientation(start, end)
            if orientation not in {ConnectorOrientation.HORIZONTAL, ConnectorOrientation.VERTICAL}:
                continue

            start_nodes = _nearby_node_ids(start, all_nodes)
            end_nodes = _nearby_node_ids(end, all_nodes)
            if start_nodes and end_nodes and set(start_nodes) == set(end_nodes):
                continue

            midpoint = Point((start.x + end.x) / 2.0, (start.y + end.y) / 2.0)
            if any(node.bbox.contains_point(midpoint) for node in all_nodes) and len(set(start_nodes) | set(end_nodes)) <= 1:
                continue

            arrowhead_start, arrowhead_end = _detect_arrowheads(
                start,
                end,
                arrowhead_hints,
                mask=mask,
                orientation=orientation,
            )
            nearby_container_ids = _nearby_container_ids(_segment_bbox(start, end), all_containers)
            length = math.hypot(end.x - start.x, end.y - start.y)
            confidence = min(
                0.95,
                0.34
                + min(0.32, length / 160.0)
                + (0.1 if start_nodes else 0.0)
                + (0.1 if end_nodes else 0.0)
                + (0.08 if arrowhead_start or arrowhead_end else 0.0),
            )
            kind = ConnectorKind.ARROW if arrowhead_start or arrowhead_end else (
                ConnectorKind.ORTHOGONAL if orientation in {ConnectorOrientation.HORIZONTAL, ConnectorOrientation.VERTICAL} else ConnectorKind.LINE
            )
            evidence = ConnectorEvidence(
                id=f"connector_evidence:{len(evidence_by_key) + 1}",
                kind=kind,
                orientation=orientation,
                bbox=_segment_bbox(start, end),
                confidence=confidence,
                path_points=(start, end),
                arrowhead_start=arrowhead_start,
                arrowhead_end=arrowhead_end,
                start_nearby_node_ids=start_nodes,
                end_nearby_node_ids=end_nodes,
                nearby_container_ids=nearby_container_ids,
                source="phase4_connector_hough_lines",
                provenance=(
                    "branch:structural_canvas",
                    "signal:hough_lines_p",
                    "signal:arrowhead_contour",
                ),
            )
            key = _segment_key(start, end)
            current = evidence_by_key.get(key)
            if current is None or evidence.confidence > current.confidence:
                evidence_by_key[key] = evidence

        ordered = sorted(
            evidence_by_key.values(),
            key=lambda item: (item.bbox.y0, item.bbox.x0, item.bbox.y1, item.bbox.x1),
        )
        return tuple(
            ConnectorEvidence(
                id=f"connector_evidence:{index}",
                kind=item.kind,
                orientation=item.orientation,
                bbox=item.bbox,
                confidence=item.confidence,
                path_points=item.path_points,
                arrowhead_start=item.arrowhead_start,
                arrowhead_end=item.arrowhead_end,
                start_nearby_node_ids=item.start_nearby_node_ids,
                end_nearby_node_ids=item.end_nearby_node_ids,
                nearby_container_ids=item.nearby_container_ids,
                source=item.source,
                provenance=item.provenance,
            )
            for index, item in enumerate(ordered, start=1)
        )


def extract_connector_evidence(
    canvas: ResidualStructuralCanvas,
    *,
    instances: tuple[DiagramInstance, ...],
    config: V3Config,
) -> tuple[ConnectorEvidence, ...]:
    return OrthogonalConnectorEvidenceExtractor().extract(canvas, instances=instances, config=config)


def _ink_mask(image: np.ndarray) -> np.ndarray:
    _, threshold = cv2.threshold(image, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    return threshold


def _segment_key(start: Point, end: Point) -> tuple[tuple[int, int], tuple[int, int]]:
    left = (int(round(start.x / 4.0)), int(round(start.y / 4.0)))
    right = (int(round(end.x / 4.0)), int(round(end.y / 4.0)))
    return tuple(sorted((left, right)))  # type: ignore[return-value]


def _classify_orientation(start: Point, end: Point) -> ConnectorOrientation:
    dx = abs(end.x - start.x)
    dy = abs(end.y - start.y)
    if dx <= 2.0 and dy <= 2.0:
        return ConnectorOrientation.UNKNOWN
    if dy <= 2.5:
        return ConnectorOrientation.HORIZONTAL
    if dx <= 2.5:
        return ConnectorOrientation.VERTICAL
    if dx > 0.0 and dy > 0.0:
        return ConnectorOrientation.DIAGONAL
    return ConnectorOrientation.UNKNOWN


def _segment_bbox(start: Point, end: Point) -> BBox:
    return BBox(
        min(start.x, end.x),
        min(start.y, end.y),
        max(start.x, end.x) + 1.0,
        max(start.y, end.y) + 1.0,
    )


def _nearby_node_ids(point: Point, nodes: tuple[DiagramNode, ...]) -> tuple[str, ...]:
    matches = [
        node.id
        for node in nodes
        if _point_to_bbox_distance(point, node.bbox) <= 8.0
    ]
    return tuple(sorted(set(matches)))


def _nearby_container_ids(bbox: BBox, containers: tuple[DiagramContainer, ...]) -> tuple[str, ...]:
    matches = [
        container.id
        for container in containers
        if container.bbox.expand(8.0).overlaps(bbox)
    ]
    return tuple(sorted(set(matches)))


def _point_to_bbox_distance(point: Point, bbox: BBox) -> float:
    dx = max(bbox.x0 - point.x, 0.0, point.x - bbox.x1)
    dy = max(bbox.y0 - point.y, 0.0, point.y - bbox.y1)
    return math.hypot(dx, dy)


def _find_arrowhead_hints(mask: np.ndarray, line_segments: np.ndarray) -> tuple[Point, ...]:
    contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    hints: list[Point] = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < 10.0 or area > 240.0:
            continue
        perimeter = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.16 * perimeter, True)
        if len(approx) != 3:
            continue
        moments = cv2.moments(contour)
        if moments["m00"] == 0.0:
            continue
        hints.append(Point(float(moments["m10"] / moments["m00"]), float(moments["m01"] / moments["m00"])))
    for segment in line_segments[:, 0, :]:
        x0, y0, x1, y1 = (int(value) for value in segment)
        start = Point(float(x0), float(y0))
        end = Point(float(x1), float(y1))
        orientation = _classify_orientation(start, end)
        length = math.hypot(end.x - start.x, end.y - start.y)
        if orientation is not ConnectorOrientation.DIAGONAL or length < 6.0 or length > 24.0:
            continue
        hints.extend((start, end))
    return tuple(hints)


def _detect_arrowheads(
    start: Point,
    end: Point,
    hints: tuple[Point, ...],
    *,
    mask: np.ndarray,
    orientation: ConnectorOrientation,
) -> tuple[bool, bool]:
    arrow_start = any(math.hypot(hint.x - start.x, hint.y - start.y) <= 12.0 for hint in hints) or _endpoint_arrow_signal(
        mask,
        endpoint=start,
        anchor=end,
        orientation=orientation,
    )
    arrow_end = any(math.hypot(hint.x - end.x, hint.y - end.y) <= 12.0 for hint in hints) or _endpoint_arrow_signal(
        mask,
        endpoint=end,
        anchor=start,
        orientation=orientation,
    )
    return arrow_start, arrow_end


def _endpoint_arrow_signal(
    mask: np.ndarray,
    *,
    endpoint: Point,
    anchor: Point,
    orientation: ConnectorOrientation,
) -> bool:
    x = int(round(endpoint.x))
    y = int(round(endpoint.y))
    height, width = mask.shape[:2]
    radius = 7
    if orientation is ConnectorOrientation.HORIZONTAL:
        direction = 1 if endpoint.x >= anchor.x else -1
        x0 = max(0, x + 1 if direction > 0 else x - radius)
        x1 = min(width, x + radius + 1 if direction > 0 else x)
        y0 = max(0, y - radius)
        y1 = min(height, y + radius + 1)
        patch = mask[y0:y1, x0:x1]
        if patch.size == 0:
            return False
        mid = y - y0
        upper = int(np.count_nonzero(patch[:mid, :]))
        lower = int(np.count_nonzero(patch[mid + 1 :, :]))
        return upper >= 3 and lower >= 3
    if orientation is ConnectorOrientation.VERTICAL:
        direction = 1 if endpoint.y >= anchor.y else -1
        x0 = max(0, x - radius)
        x1 = min(width, x + radius + 1)
        y0 = max(0, y + 1 if direction > 0 else y - radius)
        y1 = min(height, y + radius + 1 if direction > 0 else y)
        patch = mask[y0:y1, x0:x1]
        if patch.size == 0:
            return False
        mid = x - x0
        left = int(np.count_nonzero(patch[:, :mid]))
        right = int(np.count_nonzero(patch[:, mid + 1 :]))
        return left >= 3 and right >= 3
    return False
