from __future__ import annotations

from dataclasses import replace
import math

from .config import PipelineConfig
from .ir import Element, Point, PolylineGeometry


def repair_elements(elements: list[Element], config: PipelineConfig) -> list[Element]:
    repaired = elements[:]
    repaired = merge_collinear_lines(repaired, config)
    return repaired


def merge_collinear_lines(elements: list[Element], config: PipelineConfig) -> list[Element]:
    merged: list[Element] = []
    used = set()
    for idx, element in enumerate(elements):
        if idx in used:
            continue
        if element.kind not in {"line", "arrow"} or len(element.geometry.points) != 2:
            merged.append(element)
            continue
        current = element
        for other_idx in range(idx + 1, len(elements)):
            if other_idx in used:
                continue
            other = elements[other_idx]
            if other.kind != current.kind or len(other.geometry.points) != 2:
                continue
            candidate = try_merge_lines(current, other, config)
            if candidate is None:
                continue
            used.add(other_idx)
            current = candidate
        merged.append(current)
    return merged


def try_merge_lines(first: Element, second: Element, config: PipelineConfig) -> Element | None:
    p1, p2 = first.geometry.points
    q1, q2 = second.geometry.points
    if not segments_collinear(p1, p2, q1, q2, tolerance=config.stroke_alignment_tolerance * 1.2):
        return None
    all_points = [p1, p2, q1, q2]
    if abs(p1.x - p2.x) >= abs(p1.y - p2.y):
        all_points.sort(key=lambda point: point.x)
    else:
        all_points.sort(key=lambda point: point.y)
    if gap_between_points(all_points[1], all_points[2]) > config.stroke_merge_gap * 1.6:
        return None
    geometry = PolylineGeometry(points=(all_points[0], all_points[-1]))
    confidence = min(0.98, max(first.confidence, second.confidence) + 0.03)
    return replace(
        first,
        geometry=geometry,
        source_region=geometry.bbox,
        inferred=True,
        confidence=confidence,
    )


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
