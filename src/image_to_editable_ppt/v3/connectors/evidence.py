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
            # Short inter-row arrows in paper figures can be only ~10% of the
            # image height. A //9 vote threshold dropped them even though they
            # cleared minLineLength; //15 recovers them while later node/container
            # geometry filters reject box borders.
            threshold=max(12, min(canvas.image.shape[:2]) // 15),
            minLineLength=max(12, min(canvas.image.shape[:2]) // 14),
            maxLineGap=6,
        )
        if line_segments is None:
            return ()
        # HoughLinesP returns (N, 1, 4) on most OpenCV builds but (N, 4) on some;
        # normalise so the `[:, 0, :]` indexing below is valid either way.
        line_segments = np.asarray(line_segments)
        if line_segments.ndim == 2:
            line_segments = line_segments[:, None, :]
        all_nodes = tuple(node for instance in instances for node in instance.nodes)
        all_containers = tuple(container for instance in instances for container in instance.containers)
        arrow_signal_mask = _mask_node_ink(mask, all_nodes)
        arrowhead_hints = _find_arrowhead_hints(arrow_signal_mask, line_segments)
        evidence_by_key: dict[tuple[tuple[int, int], tuple[int, int]], ConnectorEvidence] = {}

        for segment in line_segments[:, 0, :]:
            x0, y0, x1, y1 = (int(value) for value in segment)
            start = Point(float(x0), float(y0))
            end = Point(float(x1), float(y1))
            orientation = _classify_orientation(start, end)
            if orientation not in {ConnectorOrientation.HORIZONTAL, ConnectorOrientation.VERTICAL}:
                continue
            if _is_container_border_segment(start, end, orientation=orientation, containers=all_containers):
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
                mask=arrow_signal_mask,
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


def _mask_node_ink(mask: np.ndarray, nodes: tuple[DiagramNode, ...]) -> np.ndarray:
    masked = mask.copy()
    height, width = masked.shape[:2]
    for node in nodes:
        # Rounded borders and shadows can spill ~2 px beyond the contour bbox.
        # A wider exclusion starts erasing arrow tips in short inter-row gaps.
        x0 = max(0, int(math.floor(node.bbox.x0)) - 2)
        y0 = max(0, int(math.floor(node.bbox.y0)) - 2)
        x1 = min(width, int(math.ceil(node.bbox.x1)) + 3)
        y1 = min(height, int(math.ceil(node.bbox.y1)) + 3)
        if x1 > x0 and y1 > y0:
            masked[y0:y1, x0:x1] = 0
    return masked


def _is_container_border_segment(
    start: Point,
    end: Point,
    *,
    orientation: ConnectorOrientation,
    containers: tuple[DiagramContainer, ...],
) -> bool:
    """Reject long Hough segments that trace a container's outer border.

    Rounded container sides sit slightly inside the bounding-box extrema, so the
    tolerance scales with container size. Short lines near an edge remain valid
    connector evidence; only a segment spanning much of one side is excluded.
    """
    for container in containers:
        bbox = container.bbox
        tolerance = max(8.0, min(20.0, min(bbox.width, bbox.height) * 0.055))
        if orientation is ConnectorOrientation.VERTICAL:
            side_distance = min(abs(start.x - bbox.x0), abs(start.x - bbox.x1), abs(end.x - bbox.x0), abs(end.x - bbox.x1))
            coverage = abs(end.y - start.y) / max(1.0, bbox.height)
            midpoint = (start.y + end.y) / 2.0
            if side_distance <= tolerance and coverage >= 0.45 and bbox.y0 <= midpoint <= bbox.y1:
                return True
        elif orientation is ConnectorOrientation.HORIZONTAL:
            side_distance = min(abs(start.y - bbox.y0), abs(start.y - bbox.y1), abs(end.y - bbox.y0), abs(end.y - bbox.y1))
            coverage = abs(end.x - start.x) / max(1.0, bbox.width)
            midpoint = (start.x + end.x) / 2.0
            if side_distance <= tolerance and coverage >= 0.45 and bbox.x0 <= midpoint <= bbox.x1:
                return True
    return False


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
    radius = 10
    x0 = max(0, x - radius)
    x1 = min(width, x + radius + 1)
    y0 = max(0, y - radius)
    y1 = min(height, y + radius + 1)
    patch = mask[y0:y1, x0:x1]
    if patch.size == 0:
        return False
    if orientation is ConnectorOrientation.HORIZONTAL:
        occupied_rows = np.flatnonzero(np.any(patch > 0, axis=1))
        return occupied_rows.size >= 2 and int(occupied_rows[-1] - occupied_rows[0] + 1) >= 6
    if orientation is ConnectorOrientation.VERTICAL:
        occupied_columns = np.flatnonzero(np.any(patch > 0, axis=0))
        return occupied_columns.size >= 2 and int(occupied_columns[-1] - occupied_columns[0] + 1) >= 6
    return False
