from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import math
from statistics import median
from typing import TYPE_CHECKING

import numpy as np

from .config import PipelineConfig
from .ir import BBox, BoxGeometry, Element, Point, PolylineGeometry, StrokeStyle, FillStyle
from .preprocess import ScaleContext, build_boundary_mask
from .style import color_distance, estimate_fill_color, sample_bbox_border_colors

if TYPE_CHECKING:
    from .filtering import ComponentFeatures


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


def extract_strokes(
    mask: np.ndarray,
    orientation: str,
    config: PipelineConfig,
    *,
    array: np.ndarray | None = None,
    gray: np.ndarray | None = None,
    min_length: int | None = None,
    allow_gap_merge: bool = True,
) -> list[Stroke]:
    if orientation not in {"horizontal", "vertical"}:
        raise ValueError("orientation must be horizontal or vertical")
    primary = mask if orientation == "horizontal" else mask.T
    min_run_length = config.min_stroke_length if min_length is None else min_length
    runs: list[tuple[int, int, int]] = []
    for offset, row in enumerate(primary):
        in_run = False
        start = 0
        for idx, value in enumerate(row):
            if value and not in_run:
                start = idx
                in_run = True
            elif not value and in_run:
                if idx - start >= min_run_length:
                    runs.append((offset, start, idx))
                in_run = False
        if in_run and row.size - start >= min_run_length:
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
    return merge_parallel_strokes(
        strokes,
        config,
        mask=mask,
        array=array,
        gray=gray,
        allow_gap_merge=allow_gap_merge,
    )


def merge_parallel_strokes(
    strokes: list[Stroke],
    config: PipelineConfig,
    *,
    mask: np.ndarray,
    array: np.ndarray | None,
    gray: np.ndarray | None,
    allow_gap_merge: bool,
) -> list[Stroke]:
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
        return merge_collinear_gaps(merged, config, mask=mask, array=array, gray=gray) if allow_gap_merge else merged
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
    return merge_collinear_gaps(merged, config, mask=mask, array=array, gray=gray) if allow_gap_merge else merged


def merge_collinear_gaps(
    strokes: list[Stroke],
    config: PipelineConfig,
    *,
    mask: np.ndarray,
    array: np.ndarray | None,
    gray: np.ndarray | None,
) -> list[Stroke]:
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
            if aligned and 0 <= gap <= config.stroke_merge_gap and should_merge_strokes(
                prev,
                stroke,
                mask=mask,
                array=array,
                gray=gray,
                config=config,
            ):
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
            if aligned and 0 <= gap <= config.stroke_merge_gap and should_merge_strokes(
                prev,
                stroke,
                mask=mask,
                array=array,
                gray=gray,
                config=config,
            ):
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


def should_merge_strokes(
    first: Stroke,
    second: Stroke,
    *,
    mask: np.ndarray,
    array: np.ndarray | None,
    gray: np.ndarray | None,
    config: PipelineConfig,
) -> bool:
    if array is None or gray is None:
        return False
    score = 0
    if first.orientation == second.orientation:
        score += 2
    if first.orientation == "horizontal":
        aligned = abs(first.center_y - second.center_y) <= config.stroke_alignment_tolerance
        gap = second.x0 - first.x1
    else:
        aligned = abs(first.center_x - second.center_x) <= config.stroke_alignment_tolerance
        gap = second.y0 - first.y1
    if not aligned or gap < 0 or gap > config.stroke_merge_gap:
        return False
    score += 1
    width_ratio = min(first.thickness, second.thickness) / max(first.thickness, second.thickness)
    if width_ratio >= 0.68:
        score += 1
    first_color = sample_stroke_color(array, first)
    second_color = sample_stroke_color(array, second)
    if color_distance(first_color, second_color) <= config.repair_color_distance:
        score += 1
    first_darkness = sample_stroke_darkness(gray, first)
    second_darkness = sample_stroke_darkness(gray, second)
    if abs(first_darkness - second_darkness) <= config.repair_darkness_delta:
        score += 1
    has_occluder, has_conflict = inspect_stroke_gap(mask, first, second, config)
    micro_gap = gap <= max(2.0, max(first.thickness, second.thickness) * 1.5)
    if micro_gap or has_occluder:
        score += 1
    if has_conflict:
        score -= 3
    return not has_conflict and score >= config.repair_min_score


def sample_stroke_color(array: np.ndarray, stroke: Stroke) -> tuple[int, int, int]:
    x0 = max(0, int(math.floor(stroke.x0)))
    y0 = max(0, int(math.floor(stroke.y0)))
    x1 = min(array.shape[1], int(math.ceil(stroke.x1)))
    y1 = min(array.shape[0], int(math.ceil(stroke.y1)))
    if x1 <= x0 or y1 <= y0:
        return (0, 0, 0)
    sample = array[y0:y1, x0:x1, :].reshape(-1, 3)
    return tuple(int(channel) for channel in np.median(sample, axis=0))


def sample_stroke_darkness(gray: np.ndarray, stroke: Stroke) -> float:
    x0 = max(0, int(math.floor(stroke.x0)))
    y0 = max(0, int(math.floor(stroke.y0)))
    x1 = min(gray.shape[1], int(math.ceil(stroke.x1)))
    y1 = min(gray.shape[0], int(math.ceil(stroke.y1)))
    if x1 <= x0 or y1 <= y0:
        return 0.0
    return float(255.0 - np.median(gray[y0:y1, x0:x1]))


def inspect_stroke_gap(
    mask: np.ndarray,
    first: Stroke,
    second: Stroke,
    config: PipelineConfig,
) -> tuple[bool, bool]:
    band = max(2, int(round(max(first.thickness, second.thickness) * 1.6)))
    trim = max(2, int(round(max(first.thickness, second.thickness) * 2.5)))
    if first.orientation == "horizontal":
        x0 = max(0, int(math.floor(first.x1)) - 1)
        x1 = min(mask.shape[1], int(math.ceil(second.x0)) + 1)
        y0 = max(0, int(round((first.center_y + second.center_y) / 2.0)) - band)
        y1 = min(mask.shape[0], int(round((first.center_y + second.center_y) / 2.0)) + band + 1)
        if x1 <= x0 or y1 <= y0:
            return False, False
        window = mask[y0:y1, x0:x1]
        inner = window[:, trim:-trim] if window.shape[1] > trim * 2 else window
        fill_ratio = float(inner.mean()) if inner.size else 0.0
        cross_ratio = float(np.max(inner.sum(axis=0)) / max(1, inner.shape[0])) if inner.size else 0.0
    else:
        x0 = max(0, int(round((first.center_x + second.center_x) / 2.0)) - band)
        x1 = min(mask.shape[1], int(round((first.center_x + second.center_x) / 2.0)) + band + 1)
        y0 = max(0, int(math.floor(first.y1)) - 1)
        y1 = min(mask.shape[0], int(math.ceil(second.y0)) + 1)
        if x1 <= x0 or y1 <= y0:
            return False, False
        window = mask[y0:y1, x0:x1]
        inner = window[trim:-trim, :] if window.shape[0] > trim * 2 else window
        fill_ratio = float(inner.mean()) if inner.size else 0.0
        cross_ratio = float(np.max(inner.sum(axis=1)) / max(1, inner.shape[1])) if inner.size else 0.0
    if fill_ratio <= config.repair_occluder_fill_ratio:
        return False, False
    has_conflict = fill_ratio >= config.repair_conflict_fill_ratio or cross_ratio >= 0.84
    has_occluder = (
        config.repair_occluder_fill_ratio <= fill_ratio <= config.repair_conflict_fill_ratio
        and cross_ratio < 0.84
    )
    return has_occluder, has_conflict


def fit_boxes(
    horizontal: list[Stroke],
    vertical: list[Stroke],
    *,
    boundary_mask: np.ndarray,
    array: np.ndarray,
    detail_mask: np.ndarray,
    background_color: tuple[int, int, int],
    config: PipelineConfig,
    scale: ScaleContext,
) -> list[Element]:
    candidates: list[Element] = []
    for top in horizontal:
        for bottom in horizontal:
            if bottom.center_y <= top.center_y + scale.min_box_size:
                continue
            edge_tolerance = config.stroke_merge_gap
            if top.inferred or bottom.inferred:
                edge_tolerance += max(4, int(round(scale.estimated_stroke_width * 3.0)))
            if abs(top.x0 - bottom.x0) > edge_tolerance:
                continue
            if abs(top.x1 - bottom.x1) > edge_tolerance:
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
            if bbox.width < scale.min_box_size or bbox.height < scale.min_box_size:
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
                homogeneity_threshold=config.fill_homogeneity_threshold,
                detail_mask=detail_mask,
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
        if any(boxes_equivalent(candidate, existing) for existing in deduped):
            continue
        deduped.append(candidate)
    return deduped


def boxes_equivalent(first: Element, second: Element) -> bool:
    if first.bbox.iou(second.bbox) >= 0.85:
        return True
    center_dx = abs(first.bbox.center.x - second.bbox.center.x)
    center_dy = abs(first.bbox.center.y - second.bbox.center.y)
    width_ratio = min(first.bbox.width, second.bbox.width) / max(1.0, max(first.bbox.width, second.bbox.width))
    height_ratio = min(first.bbox.height, second.bbox.height) / max(1.0, max(first.bbox.height, second.bbox.height))
    stroke_margin = max(first.stroke.width, second.stroke.width) * 4.0 + 2.0
    return (
        center_dx <= stroke_margin
        and center_dy <= stroke_margin
        and width_ratio >= 0.72
        and height_ratio >= 0.72
    )


def fit_linear_component(
    pixels: np.ndarray,
    array: np.ndarray,
    bbox: BBox,
    config: PipelineConfig,
    *,
    element_id: str,
    scale: ScaleContext | None = None,
    features: ComponentFeatures | None = None,
) -> Element | None:
    points = np.column_stack((pixels[:, 1].astype(np.float32), pixels[:, 0].astype(np.float32)))
    min_component_area = scale.min_component_area if scale is not None else config.min_component_area
    min_linear_length = scale.min_linear_length if scale is not None else max(
        config.min_stroke_length,
        int(round(max(array.shape[0], array.shape[1]) * config.min_relative_line_length)),
    )
    if len(points) < min_component_area:
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
    if aspect < config.min_line_aspect_ratio:
        return None
    bins = np.linspace(major_proj.min(), major_proj.max(), num=11)
    widths: list[float] = []
    occupancy = []
    for start, end in zip(bins[:-1], bins[1:], strict=True):
        band = np.abs(major_proj - (start + end) / 2.0) <= max(1.0, (end - start) / 2.0)
        if not band.any():
            widths.append(0.0)
            occupancy.append(0.0)
            continue
        widths.append(float(np.percentile(np.abs(minor_proj[band]), 85) * 2.0 + 1.0))
        occupancy.append(1.0)
    core_width = median(width for width in widths[2:-2] if width > 0) if any(width > 0 for width in widths[2:-2]) else approx_width
    continuity = float(np.mean(occupancy)) if occupancy else 0.0
    if length < min_linear_length:
        return None
    start_widen = max(widths[:2]) / max(1.0, core_width)
    end_widen = max(widths[-2:]) / max(1.0, core_width)
    if start_widen >= end_widen:
        inner_widen = max(widths[2:4]) / max(1.0, core_width) if len(widths) >= 4 else 0.0
    else:
        inner_widen = max(widths[-4:-2]) / max(1.0, core_width) if len(widths) >= 4 else 0.0
    arrow_candidate = (
        max(start_widen, end_widen) >= config.min_arrow_widen_ratio
        and abs(start_widen - end_widen) > 0.25
        and inner_widen <= 1.95
    )
    straight_orth_limit = max(config.max_straight_orth_error, approx_width * (0.8 if arrow_candidate else 0.55))
    if orth_error > straight_orth_limit:
        return None
    if continuity < 0.82:
        return None
    if features is not None:
        if features.near_structure_count == 0 and length < min_linear_length * 1.5:
            return None
        if not arrow_candidate and features.branchiness > 0.45:
            return None
    start = centroid + major * major_proj.min()
    end = centroid + major * major_proj.max()
    stroke_color = sample_component_stroke_color(array, pixels)
    if arrow_candidate:
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
    scale: ScaleContext | None = None,
    features: ComponentFeatures | None = None,
) -> Element | None:
    local_mask_full = component_mask(pixels, bbox)
    local_mask = build_boundary_mask(local_mask_full)
    min_stroke_length = scale.min_stroke_length if scale is not None else config.min_stroke_length
    min_linear_length = scale.min_linear_length if scale is not None else max(
        config.min_stroke_length,
        int(round(max(array.shape[0], array.shape[1]) * config.min_relative_line_length)),
    )
    min_length = max(8, config.connector_min_segment_length // 2, min_stroke_length // 3)
    horizontal = extract_strokes(
        local_mask,
        "horizontal",
        config,
        min_length=min_length,
        allow_gap_merge=False,
    )
    vertical = extract_strokes(
        local_mask,
        "vertical",
        config,
        min_length=min_length,
        allow_gap_merge=False,
    )
    local_points, band = orthogonal_chain_points(horizontal, vertical, config)
    if local_points is None:
        horizontal = projection_strokes(local_mask_full, "horizontal", min_length=min_length)
        vertical = projection_strokes(local_mask_full, "vertical", min_length=min_length)
        if not horizontal or not vertical:
            return None
        local_points, band = orthogonal_chain_points(horizontal, vertical, config)
        if local_points is None:
            local_points, band = projection_chain_fallback(horizontal, vertical)
    if local_points is None:
        return None
    coverage = connector_pixel_coverage(local_mask_full, local_points, band=band)
    if coverage < config.connector_min_coverage:
        return None
    path_length = polyline_length(local_points)
    if path_length < min_linear_length * 1.1:
        return None
    if features is not None:
        if features.near_structure_count == 0 and path_length < min_linear_length * 1.5:
            return None
        if features.density > 0.48:
            return None
    global_points = tuple(Point(point.x + bbox.x0, point.y + bbox.y0) for point in local_points)
    stroke_color = sample_component_stroke_color(array, pixels)
    return Element(
        id=element_id,
        kind="orthogonal_connector",
        geometry=PolylineGeometry(points=global_points),
        stroke=StrokeStyle(color=stroke_color, width=max(1.0, band * 1.5)),
        fill=FillStyle(enabled=False, color=None),
        text=None,
        confidence=min(0.96, 0.72 + coverage * 0.24 + min(len(global_points), 5) * 0.01),
        source_region=bbox,
        inferred=False,
    )


def component_mask(pixels: np.ndarray, bbox: BBox) -> np.ndarray:
    width = max(1, int(math.ceil(bbox.width)))
    height = max(1, int(math.ceil(bbox.height)))
    mask = np.zeros((height, width), dtype=bool)
    xs = pixels[:, 1] - int(math.floor(bbox.x0))
    ys = pixels[:, 0] - int(math.floor(bbox.y0))
    mask[ys, xs] = True
    return mask


def projection_strokes(mask: np.ndarray, orientation: str, *, min_length: int) -> list[Stroke]:
    if orientation == "horizontal":
        profile = mask.sum(axis=1)
        threshold = max(min_length * 2, int(round(mask.shape[1] * 0.30)))
        strokes: list[Stroke] = []
        for start, end in profile_bands(profile, threshold=threshold):
            band = mask[start:end, :]
            x_profile = band.sum(axis=0)
            x_threshold = max(1, band.shape[0] // 2)
            for x0, x1 in profile_bands(x_profile, threshold=x_threshold):
                if x1 - x0 < min_length:
                    continue
                strokes.append(
                    Stroke(
                        orientation="horizontal",
                        x0=float(x0),
                        y0=float(start),
                        x1=float(x1),
                        y1=float(end),
                        thickness=float(end - start),
                    )
                )
        return strokes
    profile = mask.sum(axis=0)
    threshold = max(min_length * 2, int(round(mask.shape[0] * 0.28)))
    strokes = []
    for start, end in profile_bands(profile, threshold=threshold):
        band = mask[:, start:end]
        y_profile = band.sum(axis=1)
        y_threshold = max(1, band.shape[1] // 2)
        for y0, y1 in profile_bands(y_profile, threshold=y_threshold):
            if y1 - y0 < min_length:
                continue
            strokes.append(
                Stroke(
                    orientation="vertical",
                    x0=float(start),
                    y0=float(y0),
                    x1=float(end),
                    y1=float(y1),
                    thickness=float(end - start),
                )
            )
    return strokes


def profile_bands(profile: np.ndarray, *, threshold: int) -> list[tuple[int, int]]:
    bands: list[tuple[int, int]] = []
    start: int | None = None
    for index, value in enumerate(profile.tolist()):
        if value >= threshold and start is None:
            start = index
        elif value < threshold and start is not None:
            bands.append((start, index))
            start = None
    if start is not None:
        bands.append((start, len(profile)))
    return bands


def projection_chain_fallback(
    horizontal: list[Stroke],
    vertical: list[Stroke],
) -> tuple[tuple[Point, ...] | None, int]:
    if len(horizontal) != 2 or len(vertical) < 2:
        return None, 0
    horizontal = sorted(horizontal, key=lambda stroke: stroke.center_y)
    vertical = sorted(vertical, key=lambda stroke: stroke.center_x)
    top, bottom = horizontal
    trunk = next(
        (
            stroke
            for stroke in vertical
            if stroke.y0 <= top.center_y <= stroke.y1 and stroke.y0 <= bottom.center_y <= stroke.y1
        ),
        None,
    )
    branch = next(
        (
            stroke
            for stroke in vertical
            if stroke is not trunk and stroke.center_x > (trunk.center_x if trunk is not None else -1)
            and stroke.y0 <= bottom.center_y <= stroke.y1
        ),
        None,
    )
    if trunk is None or branch is None:
        return None, 0
    path = (
        Point(float(top.x0), float(top.center_y)),
        Point(float(trunk.center_x), float(top.center_y)),
        Point(float(trunk.center_x), float(bottom.center_y)),
        Point(float(branch.center_x), float(bottom.center_y)),
        Point(float(bottom.x1), float(bottom.center_y)),
    )
    return path, max(1, int(round(median([top.thickness, bottom.thickness, trunk.thickness, branch.thickness]))))


def fit_branchy_component_lines(
    pixels: np.ndarray,
    array: np.ndarray,
    bbox: BBox,
    config: PipelineConfig,
    *,
    element_prefix: str,
    scale: ScaleContext | None = None,
    structural_elements: list[Element] | None = None,
) -> list[Element]:
    local_mask = component_mask(pixels, bbox)
    min_linear_length = scale.min_linear_length if scale is not None else max(
        config.min_stroke_length,
        int(round(max(array.shape[0], array.shape[1]) * config.min_relative_line_length)),
    )
    min_projection_length = max(8, min_linear_length // 3)
    horizontals = projection_strokes(local_mask, "horizontal", min_length=min_projection_length)
    verticals = projection_strokes(local_mask, "vertical", min_length=min_projection_length)
    segments: list[Stroke] = []
    horizontal_blockers = [
        stroke
        for stroke in verticals
        if stroke.thickness >= max(6.0, (scale.estimated_stroke_width if scale is not None else 2.0) * 2.0)
    ]
    vertical_blockers = [
        stroke
        for stroke in horizontals
        if stroke.thickness >= max(6.0, (scale.estimated_stroke_width if scale is not None else 2.0) * 2.0)
    ]
    for stroke in horizontals:
        segments.extend(split_stroke_by_blockers(stroke, horizontal_blockers))
    for stroke in verticals:
        segments.extend(split_stroke_by_blockers(stroke, vertical_blockers))
    color = sample_component_stroke_color(array, pixels)
    deduped: list[Element] = []
    for index, stroke in enumerate(sorted(segments, key=lambda segment: segment.length, reverse=True), start=1):
        if stroke.length < min_linear_length:
            continue
        geometry = stroke_to_polyline(stroke, bbox)
        if structural_elements and segment_is_captured_by_box(geometry.points[0], geometry.points[-1], structural_elements, scale):
            continue
        element = Element(
            id=f"{element_prefix}-{index}",
            kind="line",
            geometry=geometry,
            stroke=StrokeStyle(color=color, width=max(1.0, stroke.thickness * 0.8)),
            fill=FillStyle(enabled=False, color=None),
            text=None,
            confidence=min(0.88, 0.70 + min(stroke.length / max(1.0, min_linear_length), 3.0) * 0.05),
            source_region=geometry.bbox,
            inferred=False,
        )
        if any(element.bbox.iou(existing.bbox) >= 0.72 for existing in deduped):
            continue
        deduped.append(element)
        if len(deduped) >= 3:
            break
    return deduped


def split_stroke_by_blockers(stroke: Stroke, blockers: list[Stroke]) -> list[Stroke]:
    if stroke.orientation == "horizontal":
        blocked = sorted(
            (
                (max(stroke.x0, blocker.x0), min(stroke.x1, blocker.x1))
                for blocker in blockers
                if blocker.y0 <= stroke.center_y <= blocker.y1 and blocker.x0 < stroke.x1 and blocker.x1 > stroke.x0
            ),
            key=lambda item: item[0],
        )
        return horizontal_segments_from_intervals(stroke, blocked)
    blocked = sorted(
        (
            (max(stroke.y0, blocker.y0), min(stroke.y1, blocker.y1))
            for blocker in blockers
            if blocker.x0 <= stroke.center_x <= blocker.x1 and blocker.y0 < stroke.y1 and blocker.y1 > stroke.y0
        ),
        key=lambda item: item[0],
    )
    return vertical_segments_from_intervals(stroke, blocked)


def horizontal_segments_from_intervals(stroke: Stroke, intervals: list[tuple[float, float]]) -> list[Stroke]:
    segments: list[Stroke] = []
    cursor = stroke.x0
    for start, end in intervals:
        if start - cursor >= 1.0:
            segments.append(
                Stroke(
                    orientation="horizontal",
                    x0=cursor,
                    y0=stroke.y0,
                    x1=start,
                    y1=stroke.y1,
                    thickness=stroke.thickness,
                )
            )
        cursor = max(cursor, end)
    if stroke.x1 - cursor >= 1.0:
        segments.append(
            Stroke(
                orientation="horizontal",
                x0=cursor,
                y0=stroke.y0,
                x1=stroke.x1,
                y1=stroke.y1,
                thickness=stroke.thickness,
            )
        )
    return segments


def vertical_segments_from_intervals(stroke: Stroke, intervals: list[tuple[float, float]]) -> list[Stroke]:
    segments: list[Stroke] = []
    cursor = stroke.y0
    for start, end in intervals:
        if start - cursor >= 1.0:
            segments.append(
                Stroke(
                    orientation="vertical",
                    x0=stroke.x0,
                    y0=cursor,
                    x1=stroke.x1,
                    y1=start,
                    thickness=stroke.thickness,
                )
            )
        cursor = max(cursor, end)
    if stroke.y1 - cursor >= 1.0:
        segments.append(
            Stroke(
                orientation="vertical",
                x0=stroke.x0,
                y0=cursor,
                x1=stroke.x1,
                y1=stroke.y1,
                thickness=stroke.thickness,
            )
        )
    return segments


def stroke_to_polyline(stroke: Stroke, bbox: BBox) -> PolylineGeometry:
    if stroke.orientation == "horizontal":
        return PolylineGeometry(
            points=(
                Point(float(stroke.x0 + bbox.x0), float(stroke.center_y + bbox.y0)),
                Point(float(stroke.x1 + bbox.x0), float(stroke.center_y + bbox.y0)),
            )
        )
    return PolylineGeometry(
        points=(
            Point(float(stroke.center_x + bbox.x0), float(stroke.y0 + bbox.y0)),
            Point(float(stroke.center_x + bbox.x0), float(stroke.y1 + bbox.y0)),
        )
    )


def segment_is_captured_by_box(
    start: Point,
    end: Point,
    structural_elements: list[Element],
    scale: ScaleContext | None,
) -> bool:
    margin = max(4.0, (scale.estimated_stroke_width if scale is not None else 2.0) * 3.0)
    for element in structural_elements:
        if element.kind not in {"rect", "rounded_rect"}:
            continue
        expanded = element.bbox.expand(margin)
        if expanded.contains_point(start) and expanded.contains_point(end):
            return True
    return False


def sample_component_stroke_color(array: np.ndarray, pixels: np.ndarray) -> tuple[int, int, int]:
    sample = array[pixels[:, 0], pixels[:, 1], :].astype(np.float32)
    if sample.size == 0:
        return (0, 0, 0)
    luminance = sample @ np.asarray([0.2126, 0.7152, 0.0722], dtype=np.float32)
    cutoff = float(np.percentile(luminance, 35))
    focused = sample[luminance <= cutoff]
    if focused.size == 0:
        focused = sample
    median_color = np.median(focused, axis=0)
    return tuple(int(round(channel)) for channel in median_color)


def orthogonal_chain_points(
    horizontal: list[Stroke],
    vertical: list[Stroke],
    config: PipelineConfig,
) -> tuple[tuple[Point, ...] | None, int]:
    adjacency: dict[tuple[int, int], set[tuple[int, int]]] = defaultdict(set)
    edge_count = 0
    band = max(1, int(round(median([stroke.thickness for stroke in horizontal + vertical]))))
    for stroke in horizontal:
        nodes = horizontal_segment_nodes(stroke, vertical, config)
        edge_count += add_segment_edges(adjacency, nodes, axis="x")
    for stroke in vertical:
        nodes = vertical_segment_nodes(stroke, horizontal, config)
        edge_count += add_segment_edges(adjacency, nodes, axis="y")
    if not adjacency:
        return None, band
    endpoints = [node for node, neighbors in adjacency.items() if len(neighbors) == 1]
    if len(endpoints) != 2:
        return None, band
    if any(len(neighbors) > 2 for neighbors in adjacency.values()):
        return None, band
    path = walk_simple_path(adjacency, endpoints[0], endpoints[1])
    if path is None:
        return None, band
    compressed = compress_path(path)
    if len(compressed) < 3:
        return None, band
    if len(compressed) - 1 > config.connector_max_segments:
        return None, band
    return tuple(Point(float(x), float(y)) for x, y in compressed), band


def horizontal_segment_nodes(
    stroke: Stroke,
    vertical: list[Stroke],
    config: PipelineConfig,
) -> list[tuple[int, int]]:
    y = int(round(stroke.center_y))
    endpoint_margin = max(1, int(round(stroke.thickness / 2.0)))
    nodes = [
        (int(round(stroke.x0 + endpoint_margin)), y),
        (int(round(stroke.x1 - endpoint_margin)), y),
    ]
    for other in vertical:
        x = int(round(other.center_x))
        if stroke.x0 - config.stroke_alignment_tolerance <= x <= stroke.x1 + config.stroke_alignment_tolerance and other.y0 - config.stroke_alignment_tolerance <= y <= other.y1 + config.stroke_alignment_tolerance:
            nodes.append((x, y))
    return dedupe_sorted_nodes(nodes, axis="x", tolerance=max(2, int(round(stroke.thickness))))


def vertical_segment_nodes(
    stroke: Stroke,
    horizontal: list[Stroke],
    config: PipelineConfig,
) -> list[tuple[int, int]]:
    x = int(round(stroke.center_x))
    endpoint_margin = max(1, int(round(stroke.thickness / 2.0)))
    nodes = [
        (x, int(round(stroke.y0 + endpoint_margin))),
        (x, int(round(stroke.y1 - endpoint_margin))),
    ]
    for other in horizontal:
        y = int(round(other.center_y))
        if stroke.y0 - config.stroke_alignment_tolerance <= y <= stroke.y1 + config.stroke_alignment_tolerance and other.x0 - config.stroke_alignment_tolerance <= x <= other.x1 + config.stroke_alignment_tolerance:
            nodes.append((x, y))
    return dedupe_sorted_nodes(nodes, axis="y", tolerance=max(2, int(round(stroke.thickness))))


def dedupe_sorted_nodes(
    nodes: list[tuple[int, int]],
    *,
    axis: str,
    tolerance: int,
) -> list[tuple[int, int]]:
    index = 0 if axis == "x" else 1
    ordered = sorted(set(nodes), key=lambda node: (node[index], node[1 - index]))
    collapsed: list[tuple[int, int]] = []
    for node in ordered:
        if not collapsed:
            collapsed.append(node)
            continue
        previous = collapsed[-1]
        if abs(node[index] - previous[index]) <= tolerance and abs(node[1 - index] - previous[1 - index]) <= tolerance:
            collapsed[-1] = (
                int(round((previous[0] + node[0]) / 2.0)),
                int(round((previous[1] + node[1]) / 2.0)),
            )
            continue
        collapsed.append(node)
    return collapsed


def add_segment_edges(
    adjacency: dict[tuple[int, int], set[tuple[int, int]]],
    nodes: list[tuple[int, int]],
    *,
    axis: str,
) -> int:
    if len(nodes) < 2:
        return 0
    edge_count = 0
    for start, end in zip(nodes[:-1], nodes[1:], strict=True):
        if start == end:
            continue
        adjacency[start].add(end)
        adjacency[end].add(start)
        edge_count += 1
    return edge_count


def walk_simple_path(
    adjacency: dict[tuple[int, int], set[tuple[int, int]]],
    start: tuple[int, int],
    end: tuple[int, int],
) -> list[tuple[int, int]] | None:
    path = [start]
    previous: tuple[int, int] | None = None
    current = start
    while current != end:
        candidates = [node for node in adjacency[current] if node != previous]
        if len(candidates) != 1:
            return None
        previous = current
        current = candidates[0]
        path.append(current)
        if len(path) > len(adjacency) + 1:
            return None
    return path


def compress_path(path: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if len(path) <= 2:
        return path
    compressed = [path[0]]
    for idx in range(1, len(path) - 1):
        prev = compressed[-1]
        current = path[idx]
        nxt = path[idx + 1]
        prev_dir = (int(math.copysign(1, current[0] - prev[0])) if current[0] != prev[0] else 0, int(math.copysign(1, current[1] - prev[1])) if current[1] != prev[1] else 0)
        next_dir = (int(math.copysign(1, nxt[0] - current[0])) if nxt[0] != current[0] else 0, int(math.copysign(1, nxt[1] - current[1])) if nxt[1] != current[1] else 0)
        if prev_dir == next_dir:
            continue
        compressed.append(current)
    compressed.append(path[-1])
    return compressed


def polyline_length(points: tuple[Point, ...]) -> float:
    return float(
        sum(
            math.hypot(end.x - start.x, end.y - start.y)
            for start, end in zip(points[:-1], points[1:], strict=True)
        )
    )


def connector_pixel_coverage(mask: np.ndarray, points: tuple[Point, ...], *, band: int) -> float:
    pixels = np.argwhere(mask)
    if len(pixels) == 0:
        return 0.0
    covered = 0
    for y, x in pixels:
        if any(pixel_near_axis_segment(x, y, start, end, band) for start, end in zip(points[:-1], points[1:], strict=True)):
            covered += 1
    return covered / len(pixels)


def pixel_near_axis_segment(x: int, y: int, start: Point, end: Point, band: int) -> bool:
    if int(round(start.x)) == int(round(end.x)):
        segment_x = int(round(start.x))
        y0 = min(start.y, end.y) - band
        y1 = max(start.y, end.y) + band
        return abs(x - segment_x) <= band and y0 <= y <= y1
    segment_y = int(round(start.y))
    x0 = min(start.x, end.x) - band
    x1 = max(start.x, end.x) + band
    return abs(y - segment_y) <= band and x0 <= x <= x1


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
