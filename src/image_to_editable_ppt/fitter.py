from __future__ import annotations

from dataclasses import dataclass
import math
from statistics import median

import numpy as np

from .config import PipelineConfig
from .ir import BBox, BoxGeometry, Element, Point, PolylineGeometry, StrokeStyle, FillStyle
from .style import estimate_fill_color, sample_bbox_border_colors


@dataclass(slots=True)
class Stroke:
    orientation: str
    x0: float
    y0: float
    x1: float
    y1: float
    thickness: float
    inferred: bool = False

    @property
    def center_x(self) -> float:
        return (self.x0 + self.x1) / 2.0

    @property
    def center_y(self) -> float:
        return (self.y0 + self.y1) / 2.0

    @property
    def length(self) -> float:
        if self.orientation == "horizontal":
            return self.x1 - self.x0
        return self.y1 - self.y0


def extract_strokes(mask: np.ndarray, orientation: str, config: PipelineConfig) -> list[Stroke]:
    if orientation not in {"horizontal", "vertical"}:
        raise ValueError("orientation must be horizontal or vertical")
    primary = mask if orientation == "horizontal" else mask.T
    runs: list[tuple[int, int, int]] = []
    for offset, row in enumerate(primary):
        in_run = False
        start = 0
        for idx, value in enumerate(row):
            if value and not in_run:
                start = idx
                in_run = True
            elif not value and in_run:
                if idx - start >= config.min_stroke_length:
                    runs.append((offset, start, idx))
                in_run = False
        if in_run and row.size - start >= config.min_stroke_length:
            runs.append((offset, start, row.size))
    strokes: list[Stroke] = []
    for offset, start, end in runs:
        if orientation == "horizontal":
            strokes.append(
                Stroke(
                    orientation=orientation,
                    x0=float(start),
                    y0=float(offset),
                    x1=float(end),
                    y1=float(offset + 1),
                    thickness=1.0,
                )
            )
        else:
            strokes.append(
                Stroke(
                    orientation=orientation,
                    x0=float(offset),
                    y0=float(start),
                    x1=float(offset + 1),
                    y1=float(end),
                    thickness=1.0,
                )
            )
    return merge_parallel_strokes(strokes, config)


def merge_parallel_strokes(strokes: list[Stroke], config: PipelineConfig) -> list[Stroke]:
    if not strokes:
        return []
    if strokes[0].orientation == "horizontal":
        strokes = sorted(strokes, key=lambda stroke: (stroke.y0, stroke.x0))
        merged: list[Stroke] = []
        for stroke in strokes:
            if not merged:
                merged.append(stroke)
                continue
            prev = merged[-1]
            same_band = abs(prev.center_y - stroke.center_y) <= config.stroke_alignment_tolerance
            close_edges = (
                abs(prev.x0 - stroke.x0) <= config.stroke_alignment_tolerance
                and abs(prev.x1 - stroke.x1) <= config.stroke_alignment_tolerance
            )
            if same_band and close_edges:
                merged[-1] = Stroke(
                    orientation="horizontal",
                    x0=min(prev.x0, stroke.x0),
                    y0=min(prev.y0, stroke.y0),
                    x1=max(prev.x1, stroke.x1),
                    y1=max(prev.y1, stroke.y1),
                    thickness=max(prev.y1, stroke.y1) - min(prev.y0, stroke.y0),
                    inferred=prev.inferred or stroke.inferred,
                )
            else:
                merged.append(stroke)
        return merge_collinear_gaps(merged, config)
    strokes = sorted(strokes, key=lambda stroke: (stroke.x0, stroke.y0))
    merged = []
    for stroke in strokes:
        if not merged:
            merged.append(stroke)
            continue
        prev = merged[-1]
        same_band = abs(prev.center_x - stroke.center_x) <= config.stroke_alignment_tolerance
        close_edges = (
            abs(prev.y0 - stroke.y0) <= config.stroke_alignment_tolerance
            and abs(prev.y1 - stroke.y1) <= config.stroke_alignment_tolerance
        )
        if same_band and close_edges:
            merged[-1] = Stroke(
                orientation="vertical",
                x0=min(prev.x0, stroke.x0),
                y0=min(prev.y0, stroke.y0),
                x1=max(prev.x1, stroke.x1),
                y1=max(prev.y1, stroke.y1),
                thickness=max(prev.x1, stroke.x1) - min(prev.x0, stroke.x0),
                inferred=prev.inferred or stroke.inferred,
            )
        else:
            merged.append(stroke)
    return merge_collinear_gaps(merged, config)


def merge_collinear_gaps(strokes: list[Stroke], config: PipelineConfig) -> list[Stroke]:
    if not strokes:
        return []
    orientation = strokes[0].orientation
    strokes = sorted(
        strokes,
        key=lambda stroke: (stroke.center_y, stroke.x0) if orientation == "horizontal" else (stroke.center_x, stroke.y0),
    )
    merged: list[Stroke] = []
    for stroke in strokes:
        if not merged:
            merged.append(stroke)
            continue
        prev = merged[-1]
        if orientation == "horizontal":
            aligned = abs(prev.center_y - stroke.center_y) <= config.stroke_alignment_tolerance
            gap = stroke.x0 - prev.x1
            if aligned and 0 <= gap <= config.stroke_merge_gap:
                merged[-1] = Stroke(
                    orientation="horizontal",
                    x0=prev.x0,
                    y0=min(prev.y0, stroke.y0),
                    x1=stroke.x1,
                    y1=max(prev.y1, stroke.y1),
                    thickness=max(prev.thickness, stroke.thickness),
                    inferred=True,
                )
                continue
        else:
            aligned = abs(prev.center_x - stroke.center_x) <= config.stroke_alignment_tolerance
            gap = stroke.y0 - prev.y1
            if aligned and 0 <= gap <= config.stroke_merge_gap:
                merged[-1] = Stroke(
                    orientation="vertical",
                    x0=min(prev.x0, stroke.x0),
                    y0=prev.y0,
                    x1=max(prev.x1, stroke.x1),
                    y1=stroke.y1,
                    thickness=max(prev.thickness, stroke.thickness),
                    inferred=True,
                )
                continue
        merged.append(stroke)
    return merged


def fit_boxes(
    horizontal: list[Stroke],
    vertical: list[Stroke],
    *,
    boundary_mask: np.ndarray,
    array: np.ndarray,
    background_color: tuple[int, int, int],
    config: PipelineConfig,
) -> list[Element]:
    candidates: list[Element] = []
    for top in horizontal:
        for bottom in horizontal:
            if bottom.center_y <= top.center_y + config.min_box_size:
                continue
            if abs(top.x0 - bottom.x0) > config.stroke_merge_gap:
                continue
            if abs(top.x1 - bottom.x1) > config.stroke_merge_gap:
                continue
            left = best_vertical_for_box(vertical, x_target=min(top.x0, bottom.x0), y0=top.center_y, y1=bottom.center_y, config=config)
            right = best_vertical_for_box(vertical, x_target=max(top.x1, bottom.x1), y0=top.center_y, y1=bottom.center_y, config=config)
            if left is None or right is None:
                continue
            bbox = BBox(
                min(left.center_x, top.x0, bottom.x0),
                min(top.center_y, left.y0, right.y0),
                max(right.center_x, top.x1, bottom.x1),
                max(bottom.center_y, left.y1, right.y1),
            )
            if bbox.width < config.min_box_size or bbox.height < config.min_box_size:
                continue
            supports = side_supports(boundary_mask, bbox, top, right, bottom, left)
            if min(supports.values()) < config.min_side_support:
                continue
            average_support = sum(supports.values()) / len(supports)
            if average_support < config.min_box_support:
                continue
            stroke_width = float(median([top.thickness, bottom.thickness, left.thickness, right.thickness]))
            stroke_color = sample_bbox_border_colors(array, bbox, stroke_width)
            fill_enabled, fill_color = estimate_fill_color(
                array=array,
                bbox=bbox,
                stroke_width=stroke_width,
                background_color=background_color,
                delta_threshold=config.fill_delta_threshold,
            )
            rounded = is_rounded_rectangle(top, right, bottom, left, bbox)
            inferred = any(stroke.inferred for stroke in (top, right, bottom, left))
            confidence = min(0.98, 0.70 + average_support * 0.25 + (0.03 if inferred else 0.0))
            candidates.append(
                Element(
                    id=f"box-{len(candidates) + 1}",
                    kind="rounded_rect" if rounded else "rect",
                    geometry=BoxGeometry(
                        bbox=bbox,
                        corner_radius=max(6.0, min(bbox.width, bbox.height) * 0.12) if rounded else 0.0,
                    ),
                    stroke=StrokeStyle(color=stroke_color, width=stroke_width),
                    fill=FillStyle(enabled=fill_enabled, color=fill_color),
                    text=None,
                    confidence=confidence,
                    source_region=bbox,
                    inferred=inferred,
                )
            )
    deduped: list[Element] = []
    for candidate in sorted(candidates, key=lambda element: element.confidence, reverse=True):
        if any(candidate.bbox.iou(existing.bbox) >= 0.85 for existing in deduped):
            continue
        deduped.append(candidate)
    return deduped


def fit_linear_component(
    pixels: np.ndarray,
    array: np.ndarray,
    bbox: BBox,
    config: PipelineConfig,
    *,
    element_id: str,
) -> Element | None:
    points = np.column_stack((pixels[:, 1].astype(np.float32), pixels[:, 0].astype(np.float32)))
    if len(points) < config.min_component_area:
        return None
    centroid = points.mean(axis=0)
    centered = points - centroid
    if centered.shape[0] < 2:
        return None
    covariance = np.cov(centered, rowvar=False)
    eigvals, eigvecs = np.linalg.eigh(covariance)
    major = eigvecs[:, int(np.argmax(eigvals))]
    minor = np.array([-major[1], major[0]], dtype=np.float32)
    major_proj = centered @ major
    minor_proj = centered @ minor
    length = float(major_proj.max() - major_proj.min() + 1.0)
    orth_error = float(np.sqrt(np.mean(minor_proj**2)))
    approx_width = max(1.0, float(np.percentile(np.abs(minor_proj), 80) * 2.0 + 1.0))
    aspect = length / max(1.0, approx_width)
    if aspect < config.min_line_aspect_ratio or orth_error > config.max_straight_orth_error:
        return None
    bins = np.linspace(major_proj.min(), major_proj.max(), num=11)
    widths: list[float] = []
    for start, end in zip(bins[:-1], bins[1:], strict=True):
        band = np.abs(major_proj - (start + end) / 2.0) <= max(1.0, (end - start) / 2.0)
        if not band.any():
            widths.append(0.0)
            continue
        widths.append(float(np.percentile(np.abs(minor_proj[band]), 85) * 2.0 + 1.0))
    core_width = median(width for width in widths[2:-2] if width > 0) if any(width > 0 for width in widths[2:-2]) else approx_width
    start_widen = max(widths[:2]) / max(1.0, core_width)
    end_widen = max(widths[-2:]) / max(1.0, core_width)
    start = centroid + major * major_proj.min()
    end = centroid + major * major_proj.max()
    stroke_color = tuple(int(channel) for channel in np.median(array[pixels[:, 0], pixels[:, 1], :], axis=0))
    if max(start_widen, end_widen) >= config.min_arrow_widen_ratio and abs(start_widen - end_widen) > 0.25:
        start_point = Point(float(end[0]), float(end[1])) if start_widen > end_widen else Point(float(start[0]), float(start[1]))
        end_point = Point(float(start[0]), float(start[1])) if start_widen > end_widen else Point(float(end[0]), float(end[1]))
        confidence = min(0.95, 0.78 + min(max(start_widen, end_widen), 3.0) * 0.06)
        return Element(
            id=element_id,
            kind="arrow",
            geometry=PolylineGeometry(points=(start_point, end_point)),
            stroke=StrokeStyle(color=stroke_color, width=max(1.0, approx_width * 0.7)),
            fill=FillStyle(enabled=False, color=None),
            text=None,
            confidence=confidence,
            source_region=bbox,
            inferred=False,
        )
    start_point = Point(float(start[0]), float(start[1]))
    end_point = Point(float(end[0]), float(end[1]))
    confidence = min(0.96, 0.76 + min(aspect, 8.0) * 0.03 - min(orth_error, 4.0) * 0.01)
    return Element(
        id=element_id,
        kind="line",
        geometry=PolylineGeometry(points=(start_point, end_point)),
        stroke=StrokeStyle(color=stroke_color, width=max(1.0, approx_width * 0.7)),
        fill=FillStyle(enabled=False, color=None),
        text=None,
        confidence=confidence,
        source_region=bbox,
        inferred=False,
    )


def fit_orthogonal_connector(
    pixels: np.ndarray,
    array: np.ndarray,
    bbox: BBox,
    config: PipelineConfig,
    *,
    element_id: str,
) -> Element | None:
    ys = pixels[:, 0]
    xs = pixels[:, 1]
    row_values, row_counts = np.unique(ys, return_counts=True)
    col_values, col_counts = np.unique(xs, return_counts=True)
    dominant_y = int(row_values[int(np.argmax(row_counts))])
    dominant_x = int(col_values[int(np.argmax(col_counts))])
    band = max(1, int(round(math.sqrt(len(pixels)) / 10.0)))
    coverage = (
        (np.abs(ys - dominant_y) <= band) | (np.abs(xs - dominant_x) <= band)
    ).mean()
    if coverage < config.orthogonal_cover_threshold:
        return None
    left_extent = xs[ys == dominant_y].min(initial=dominant_x)
    right_extent = xs[ys == dominant_y].max(initial=dominant_x)
    top_extent = ys[xs == dominant_x].min(initial=dominant_y)
    bottom_extent = ys[xs == dominant_x].max(initial=dominant_y)
    horizontal_len = max(dominant_x - left_extent, right_extent - dominant_x)
    vertical_len = max(dominant_y - top_extent, bottom_extent - dominant_y)
    if horizontal_len < config.min_stroke_length or vertical_len < config.min_stroke_length:
        return None
    horizontal_candidates = [
        (Point(float(left_extent), float(dominant_y)), abs(dominant_x - left_extent)),
        (Point(float(right_extent), float(dominant_y)), abs(right_extent - dominant_x)),
    ]
    vertical_candidates = [
        (Point(float(dominant_x), float(top_extent)), abs(dominant_y - top_extent)),
        (Point(float(dominant_x), float(bottom_extent)), abs(bottom_extent - dominant_y)),
    ]
    horizontal_endpoint = max(horizontal_candidates, key=lambda item: item[1])[0]
    vertical_endpoint = max(vertical_candidates, key=lambda item: item[1])[0]
    stroke_color = tuple(int(channel) for channel in np.median(array[pixels[:, 0], pixels[:, 1], :], axis=0))
    points = (horizontal_endpoint, Point(float(dominant_x), float(dominant_y)), vertical_endpoint)
    return Element(
        id=element_id,
        kind="orthogonal_connector",
        geometry=PolylineGeometry(points=points),
        stroke=StrokeStyle(color=stroke_color, width=max(1.0, band * 1.5)),
        fill=FillStyle(enabled=False, color=None),
        text=None,
        confidence=min(0.94, 0.75 + coverage * 0.2),
        source_region=bbox,
        inferred=False,
    )


def best_vertical_for_box(
    vertical: list[Stroke],
    *,
    x_target: float,
    y0: float,
    y1: float,
    config: PipelineConfig,
) -> Stroke | None:
    candidates = []
    for stroke in vertical:
        if abs(stroke.center_x - x_target) > config.stroke_merge_gap:
            continue
        coverage = min(stroke.y1, y1) - max(stroke.y0, y0)
        if coverage < (y1 - y0) * 0.55:
            continue
        candidates.append((coverage, stroke))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], -abs(item[1].center_x - x_target)), reverse=True)
    return candidates[0][1]


def side_supports(
    boundary_mask: np.ndarray,
    bbox: BBox,
    top: Stroke,
    right: Stroke,
    bottom: Stroke,
    left: Stroke,
) -> dict[str, float]:
    return {
        "top": line_support(boundary_mask, bbox.x0, bbox.x1, top.center_y, "horizontal", top.thickness),
        "bottom": line_support(boundary_mask, bbox.x0, bbox.x1, bottom.center_y, "horizontal", bottom.thickness),
        "left": line_support(boundary_mask, bbox.y0, bbox.y1, left.center_x, "vertical", left.thickness),
        "right": line_support(boundary_mask, bbox.y0, bbox.y1, right.center_x, "vertical", right.thickness),
    }


def line_support(
    mask: np.ndarray,
    start: float,
    end: float,
    fixed: float,
    orientation: str,
    thickness: float,
) -> float:
    margin = max(1, int(round(thickness)))
    if orientation == "horizontal":
        x0 = max(0, int(math.floor(start)))
        x1 = min(mask.shape[1], int(math.ceil(end)))
        y0 = max(0, int(round(fixed)) - margin)
        y1 = min(mask.shape[0], int(round(fixed)) + margin + 1)
        if x1 <= x0 or y1 <= y0:
            return 0.0
        band = mask[y0:y1, x0:x1]
        if band.size == 0:
            return 0.0
        return float(np.any(band, axis=0).mean())
    y0 = max(0, int(math.floor(start)))
    y1 = min(mask.shape[0], int(math.ceil(end)))
    x0 = max(0, int(round(fixed)) - margin)
    x1 = min(mask.shape[1], int(round(fixed)) + margin + 1)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    band = mask[y0:y1, x0:x1]
    if band.size == 0:
        return 0.0
    return float(np.any(band, axis=1).mean())


def is_rounded_rectangle(top: Stroke, right: Stroke, bottom: Stroke, left: Stroke, bbox: BBox) -> bool:
    tolerance = max(2.0, min(bbox.width, bbox.height) * 0.08)
    return (
        top.x0 > bbox.x0 + tolerance
        and top.x1 < bbox.x1 - tolerance
        and bottom.x0 > bbox.x0 + tolerance
        and bottom.x1 < bbox.x1 - tolerance
        and left.y0 > bbox.y0 + tolerance
        and left.y1 < bbox.y1 - tolerance
        and right.y0 > bbox.y0 + tolerance
        and right.y1 < bbox.y1 - tolerance
    )
