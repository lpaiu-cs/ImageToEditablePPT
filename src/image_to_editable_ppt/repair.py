from __future__ import annotations

from dataclasses import dataclass, replace
import math

import numpy as np

from .config import PipelineConfig
from .ir import Element, Point, PolylineGeometry
from .preprocess import ProcessedImage
from .style import color_distance


@dataclass(slots=True, frozen=True)
class GapEvidence:
    score: int
    has_occluder: bool
    has_conflict: bool


def repair_elements(
    elements: list[Element],
    processed: ProcessedImage,
    config: PipelineConfig,
) -> list[Element]:
    return merge_collinear_lines(elements, processed, config)


def merge_collinear_lines(
    elements: list[Element],
    processed: ProcessedImage,
    config: PipelineConfig,
) -> list[Element]:
    merged: list[Element] = []
    used = set()
    for idx, element in enumerate(elements):
        if idx in used:
            continue
        if element.kind != "line" or not is_two_point_line(element):
            merged.append(element)
            continue
        current = element
        for other_idx in range(idx + 1, len(elements)):
            if other_idx in used:
                continue
            other = elements[other_idx]
            if other.kind != "line" or not is_two_point_line(other):
                continue
            candidate = try_merge_lines(current, other, processed, config)
            if candidate is None:
                continue
            used.add(other_idx)
            current = candidate
        merged.append(current)
    return merged


def try_merge_lines(
    first: Element,
    second: Element,
    processed: ProcessedImage,
    config: PipelineConfig,
) -> Element | None:
    if first.id.count("-") > 1 or second.id.count("-") > 1:
        return None
    p1, p2 = first.geometry.points
    q1, q2 = second.geometry.points
    if not segments_collinear(p1, p2, q1, q2, tolerance=config.stroke_alignment_tolerance * 1.2):
        return None
    if direction_similarity(p1, p2, q1, q2) < 0.97:
        return None
    near_first, near_second, far_first, far_second = nearest_endpoints(p1, p2, q1, q2)
    gap = gap_between_points(near_first, near_second)
    if gap > config.stroke_merge_gap * 1.6:
        return None
    evidence = evaluate_line_gap(first, second, near_first, near_second, processed, config)
    if evidence.has_conflict or evidence.score < config.repair_min_score:
        return None
    merged_geometry = order_merged_geometry(far_first, far_second)
    confidence = min(0.99, max(first.confidence, second.confidence) + 0.02 + 0.01 * max(0, evidence.score - config.repair_min_score))
    return replace(
        first,
        geometry=merged_geometry,
        source_region=merged_geometry.bbox,
        inferred=True,
        confidence=confidence,
    )


def evaluate_line_gap(
    first: Element,
    second: Element,
    near_first: Point,
    near_second: Point,
    processed: ProcessedImage,
    config: PipelineConfig,
) -> GapEvidence:
    score = 0
    if segments_collinear(
        first.geometry.points[0],
        first.geometry.points[1],
        second.geometry.points[0],
        second.geometry.points[1],
        tolerance=config.stroke_alignment_tolerance * 1.2,
    ):
        score += 2
    if direction_similarity(*first.geometry.points, *second.geometry.points) >= 0.985:
        score += 1
    width_ratio = min(first.stroke.width, second.stroke.width) / max(first.stroke.width, second.stroke.width)
    if width_ratio >= 0.68:
        score += 1
    if color_distance(first.stroke.color, second.stroke.color) <= config.repair_color_distance:
        score += 1
    darkness_delta = abs(
        sample_darkness(processed.gray, near_first, radius=max(2, int(round(first.stroke.width * 1.5))))
        - sample_darkness(processed.gray, near_second, radius=max(2, int(round(second.stroke.width * 1.5))))
    )
    if darkness_delta <= config.repair_darkness_delta:
        score += 1
    orientation = dominant_orientation(near_first, near_second)
    has_occluder, has_conflict = inspect_gap_region(
        processed.foreground_mask,
        near_first,
        near_second,
        width=max(first.stroke.width, second.stroke.width),
        orientation=orientation,
        config=config,
    )
    micro_gap = gap_between_points(near_first, near_second) <= max(2.0, max(first.stroke.width, second.stroke.width) * 1.5)
    if micro_gap or has_occluder:
        score += 1
    if has_conflict:
        score -= 3
    return GapEvidence(score=score, has_occluder=has_occluder, has_conflict=has_conflict)


def inspect_gap_region(
    foreground_mask: np.ndarray,
    start: Point,
    end: Point,
    *,
    width: float,
    orientation: str,
    config: PipelineConfig,
) -> tuple[bool, bool]:
    band = max(2, int(round(width * 1.6)))
    trim = max(2, int(round(width * 2.5)))
    x0 = max(0, int(math.floor(min(start.x, end.x))) - band)
    x1 = min(foreground_mask.shape[1], int(math.ceil(max(start.x, end.x))) + band + 1)
    y0 = max(0, int(math.floor(min(start.y, end.y))) - band)
    y1 = min(foreground_mask.shape[0], int(math.ceil(max(start.y, end.y))) + band + 1)
    if x1 <= x0 or y1 <= y0:
        return False, False
    window = foreground_mask[y0:y1, x0:x1]
    if orientation == "horizontal":
        inner = window[:, trim:-trim] if window.shape[1] > trim * 2 else window
    else:
        inner = window[trim:-trim, :] if window.shape[0] > trim * 2 else window
    fill_ratio = float(inner.mean()) if inner.size else 0.0
    if fill_ratio <= config.repair_occluder_fill_ratio:
        return False, False
    if orientation == "horizontal":
        cross_ratio = float(np.max(inner.sum(axis=0)) / max(1, inner.shape[0])) if inner.size else 0.0
    else:
        cross_ratio = float(np.max(inner.sum(axis=1)) / max(1, inner.shape[1])) if inner.size else 0.0
    has_conflict = fill_ratio >= config.repair_conflict_fill_ratio or cross_ratio >= 0.84
    has_occluder = (
        config.repair_occluder_fill_ratio <= fill_ratio <= config.repair_conflict_fill_ratio
        and cross_ratio < 0.84
    )
    return has_occluder, has_conflict


def order_merged_geometry(start: Point, end: Point) -> PolylineGeometry:
    if abs(start.x - end.x) >= abs(start.y - end.y):
        points = (start, end) if start.x <= end.x else (end, start)
    else:
        points = (start, end) if start.y <= end.y else (end, start)
    return PolylineGeometry(points=points)


def nearest_endpoints(
    p1: Point,
    p2: Point,
    q1: Point,
    q2: Point,
) -> tuple[Point, Point, Point, Point]:
    pairs = [
        (gap_between_points(p1, q1), p1, q1, p2, q2),
        (gap_between_points(p1, q2), p1, q2, p2, q1),
        (gap_between_points(p2, q1), p2, q1, p1, q2),
        (gap_between_points(p2, q2), p2, q2, p1, q1),
    ]
    _, near_first, near_second, far_first, far_second = min(pairs, key=lambda item: item[0])
    return near_first, near_second, far_first, far_second


def is_two_point_line(element: Element) -> bool:
    return isinstance(element.geometry, PolylineGeometry) and len(element.geometry.points) == 2


def direction_similarity(p1: Point, p2: Point, q1: Point, q2: Point) -> float:
    v1 = normalize_vector(p2.x - p1.x, p2.y - p1.y)
    v2 = normalize_vector(q2.x - q1.x, q2.y - q1.y)
    return abs(v1[0] * v2[0] + v1[1] * v2[1])


def normalize_vector(dx: float, dy: float) -> tuple[float, float]:
    magnitude = math.hypot(dx, dy)
    if magnitude == 0:
        return (0.0, 0.0)
    return (dx / magnitude, dy / magnitude)


def dominant_orientation(first: Point, second: Point) -> str:
    return "horizontal" if abs(first.x - second.x) >= abs(first.y - second.y) else "vertical"


def sample_darkness(gray: np.ndarray, point: Point, radius: int) -> float:
    x0 = max(0, int(round(point.x)) - radius)
    x1 = min(gray.shape[1], int(round(point.x)) + radius + 1)
    y0 = max(0, int(round(point.y)) - radius)
    y1 = min(gray.shape[0], int(round(point.y)) + radius + 1)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    return float(255.0 - np.median(gray[y0:y1, x0:x1]))


def segments_collinear(p1: Point, p2: Point, q1: Point, q2: Point, tolerance: float) -> bool:
    return (
        point_line_distance(q1, p1, p2) <= tolerance
        and point_line_distance(q2, p1, p2) <= tolerance
        and point_line_distance(p1, q1, q2) <= tolerance
        and point_line_distance(p2, q1, q2) <= tolerance
    )


def point_line_distance(point: Point, start: Point, end: Point) -> float:
    dx = end.x - start.x
    dy = end.y - start.y
    if dx == 0 and dy == 0:
        return math.hypot(point.x - start.x, point.y - start.y)
    numerator = abs(dy * point.x - dx * point.y + end.x * start.y - end.y * start.x)
    denominator = math.hypot(dx, dy)
    return numerator / denominator


def gap_between_points(first: Point, second: Point) -> float:
    return math.hypot(second.x - first.x, second.y - first.y)
