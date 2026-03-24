from __future__ import annotations

from dataclasses import dataclass
import math

from .config import PipelineConfig
from .detector import RefinedNode
from .ir import BBox, BoxGeometry, Element, FillStyle, Point, PolylineGeometry, StrokeStyle, TextPayload
from .vlm_parser import VLMEdge


@dataclass(slots=True, frozen=True)
class Anchor:
    side: str
    point: Point


def generate_connections(
    nodes: list[RefinedNode],
    edges: list[VLMEdge],
    config: PipelineConfig,
) -> list[Element]:
    node_map = {node.id: node for node in nodes}
    elements: list[Element] = []
    next_index = 1
    for edge in edges:
        source = node_map.get(edge.source)
        target = node_map.get(edge.target)
        if source is None or target is None:
            continue
        start, end = choose_anchor_pair(source.exact_bbox, target.exact_bbox)
        points = orthogonal_route(
            start=start,
            end=end,
            source_bbox=source.exact_bbox,
            target_bbox=target.exact_bbox,
            margin=max(config.router_margin, min(source.exact_bbox.width, source.exact_bbox.height) * 0.14),
        )
        stroke = StrokeStyle(
            color=pick_edge_color(source, target),
            width=max(source.stroke_width, target.stroke_width, 2.0),
            dash_style="dash" if edge.type == "dashed_arrow" else "solid",
        )
        kind = "arrow" if "arrow" in edge.type else ("line" if len(points) == 2 else "orthogonal_connector")
        geometry = PolylineGeometry(points=tuple(points))
        source_region = geometry.bbox
        elements.append(
            Element(
                id=f"edge-{next_index}",
                kind=kind,
                geometry=geometry,
                stroke=stroke,
                fill=FillStyle(enabled=False, color=None),
                text=None,
                confidence=min(source.confidence, target.confidence, 0.92),
                source_region=source_region,
                inferred=True,
            )
        )
        if edge.label:
            label_bbox = label_geometry(points, edge.label, config)
            elements.append(
                Element(
                    id=f"edge-label-{next_index}",
                    kind="text",
                    geometry=BoxGeometry(label_bbox),
                    stroke=StrokeStyle(color=stroke.color, width=0.0),
                    fill=FillStyle(enabled=False, color=None),
                    text=TextPayload(content=edge.label, alignment="center", confidence=0.93),
                    confidence=0.93,
                    source_region=label_bbox,
                    inferred=True,
                )
            )
        next_index += 1
    return elements


def choose_anchor_pair(source_bbox: BBox, target_bbox: BBox) -> tuple[Anchor, Anchor]:
    source_anchors = anchors_for_bbox(source_bbox)
    target_anchors = anchors_for_bbox(target_bbox)
    best: tuple[float, Anchor, Anchor] | None = None
    for source_anchor in source_anchors:
        for target_anchor in target_anchors:
            score = anchor_pair_score(source_anchor, target_anchor)
            if best is None or score < best[0]:
                best = (score, source_anchor, target_anchor)
    if best is None:
        return source_anchors[0], target_anchors[0]
    return best[1], best[2]


def anchors_for_bbox(bbox: BBox) -> list[Anchor]:
    center = bbox.center
    return [
        Anchor("left", Point(bbox.x0, center.y)),
        Anchor("right", Point(bbox.x1, center.y)),
        Anchor("top", Point(center.x, bbox.y0)),
        Anchor("bottom", Point(center.x, bbox.y1)),
    ]


def anchor_pair_score(source: Anchor, target: Anchor) -> float:
    manhattan = abs(source.point.x - target.point.x) + abs(source.point.y - target.point.y)
    side_penalty = 0.0
    if source.side == target.side:
        side_penalty += 24.0
    if (source.side in {"left", "right"}) != (target.side in {"left", "right"}):
        side_penalty += 8.0
    return manhattan + side_penalty


def orthogonal_route(
    *,
    start: Anchor,
    end: Anchor,
    source_bbox: BBox,
    target_bbox: BBox,
    margin: float,
) -> list[Point]:
    start_exit = project_outward(start.point, start.side, margin)
    end_exit = project_outward(end.point, end.side, margin)
    points = [start.point, start_exit]
    if same_axis(start_exit, end_exit):
        points.append(end_exit)
    elif start.side in {"left", "right"} and end.side in {"left", "right"}:
        mid_x = (start_exit.x + end_exit.x) / 2.0
        points.extend([Point(mid_x, start_exit.y), Point(mid_x, end_exit.y), end_exit])
    elif start.side in {"top", "bottom"} and end.side in {"top", "bottom"}:
        mid_y = (start_exit.y + end_exit.y) / 2.0
        points.extend([Point(start_exit.x, mid_y), Point(end_exit.x, mid_y), end_exit])
    else:
        bend = Point(end_exit.x, start_exit.y)
        if intersects_bbox(bend, source_bbox) or intersects_bbox(bend, target_bbox):
            bend = Point(start_exit.x, end_exit.y)
        points.extend([bend, end_exit])
    points.append(end.point)
    return collapse_collinear_points(points)


def project_outward(point: Point, side: str, margin: float) -> Point:
    if side == "left":
        return Point(point.x - margin, point.y)
    if side == "right":
        return Point(point.x + margin, point.y)
    if side == "top":
        return Point(point.x, point.y - margin)
    return Point(point.x, point.y + margin)


def same_axis(first: Point, second: Point) -> bool:
    return math.isclose(first.x, second.x, abs_tol=1e-3) or math.isclose(first.y, second.y, abs_tol=1e-3)


def collapse_collinear_points(points: list[Point]) -> list[Point]:
    if not points:
        return []
    deduped = [points[0]]
    for point in points[1:]:
        if not same_position(deduped[-1], point):
            deduped.append(point)
    if len(deduped) <= 2:
        return deduped
    collapsed = [deduped[0]]
    for point in deduped[1:-1]:
        if len(collapsed) < 2:
            collapsed.append(point)
            continue
        if is_collinear(collapsed[-2], collapsed[-1], point):
            collapsed[-1] = point
        else:
            collapsed.append(point)
    collapsed.append(deduped[-1])
    return collapsed


def same_position(first: Point, second: Point) -> bool:
    return math.isclose(first.x, second.x, abs_tol=1e-3) and math.isclose(first.y, second.y, abs_tol=1e-3)


def is_collinear(first: Point, second: Point, third: Point) -> bool:
    return (
        math.isclose(first.x, second.x, abs_tol=1e-3) and math.isclose(second.x, third.x, abs_tol=1e-3)
    ) or (
        math.isclose(first.y, second.y, abs_tol=1e-3) and math.isclose(second.y, third.y, abs_tol=1e-3)
    )


def intersects_bbox(point: Point, bbox: BBox) -> bool:
    return bbox.x0 <= point.x <= bbox.x1 and bbox.y0 <= point.y <= bbox.y1


def label_geometry(points: list[Point], label: str, config: PipelineConfig) -> BBox:
    midpoint = midpoint_along_route(points)
    width = max(48.0, len(label) * config.edge_label_char_width)
    height = max(20.0, config.edge_label_height)
    x0 = max(0.0, midpoint.x - width / 2.0)
    y0 = max(0.0, midpoint.y - config.edge_label_offset - height)
    return BBox(x0, y0, x0 + width, y0 + height)


def midpoint_along_route(points: list[Point]) -> Point:
    if len(points) < 2:
        return points[0]
    segment_lengths = [distance(a, b) for a, b in zip(points[:-1], points[1:], strict=True)]
    target = sum(segment_lengths) / 2.0
    traversed = 0.0
    for (start, end), length in zip(zip(points[:-1], points[1:], strict=True), segment_lengths, strict=True):
        if traversed + length >= target and length > 0:
            ratio = (target - traversed) / length
            return Point(start.x + (end.x - start.x) * ratio, start.y + (end.y - start.y) * ratio)
        traversed += length
    return points[-1]


def distance(first: Point, second: Point) -> float:
    return math.hypot(second.x - first.x, second.y - first.y)


def pick_edge_color(source: RefinedNode, target: RefinedNode) -> tuple[int, int, int]:
    darker_source = sum(source.stroke_color)
    darker_target = sum(target.stroke_color)
    return source.stroke_color if darker_source <= darker_target else target.stroke_color
