from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace
import math
from statistics import median
from typing import TYPE_CHECKING

try:
    import cv2
except ImportError:  # pragma: no cover - guarded by dependency/tests
    cv2 = None

import numpy as np

from .components import find_connected_components, remove_small_components
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


@dataclass(slots=True, frozen=True)
class StrokeGraphEdge:
    neighbor: int
    kind: str
    bridge_ratio: float = 0.0


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
    bridge_mask: np.ndarray | None = None,
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
        return (
            merge_collinear_gaps(merged, config, mask=mask, array=array, gray=gray, bridge_mask=bridge_mask)
            if allow_gap_merge
            else merged
        )
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
    return (
        merge_collinear_gaps(merged, config, mask=mask, array=array, gray=gray, bridge_mask=bridge_mask)
        if allow_gap_merge
        else merged
    )


def merge_collinear_gaps(
    strokes: list[Stroke],
    config: PipelineConfig,
    *,
    mask: np.ndarray,
    array: np.ndarray | None,
    gray: np.ndarray | None,
    bridge_mask: np.ndarray | None = None,
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
                bridge_mask=bridge_mask,
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
                bridge_mask=bridge_mask,
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
    bridge_mask: np.ndarray | None = None,
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
    has_occluder, has_conflict = inspect_stroke_gap(mask, first, second, config, bridge_mask=bridge_mask)
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
    *,
    bridge_mask: np.ndarray | None = None,
) -> tuple[bool, bool]:
    orientation = first.orientation
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
    bridge_ratio = 0.0
    if bridge_mask is not None:
        bridge_window = bridge_mask[y0:y1, x0:x1]
        if orientation == "horizontal":
            bridge_inner = bridge_window[:, trim:-trim] if bridge_window.shape[1] > trim * 2 else bridge_window
        else:
            bridge_inner = bridge_window[trim:-trim, :] if bridge_window.shape[0] > trim * 2 else bridge_window
        bridge_ratio = float(bridge_inner.mean()) if bridge_inner.size else 0.0
    if fill_ratio <= config.repair_occluder_fill_ratio and bridge_ratio < config.repair_bridge_fill_ratio:
        return False, False
    has_conflict = fill_ratio >= config.repair_conflict_fill_ratio or cross_ratio >= 0.84
    has_occluder = (
        config.repair_occluder_fill_ratio <= fill_ratio <= config.repair_conflict_fill_ratio
        and cross_ratio < 0.84
    )
    if bridge_ratio >= config.repair_bridge_fill_ratio and not has_conflict:
        has_occluder = True
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
    enable_relaxed_panel_recovery = max(array.shape[0], array.shape[1]) >= 1800
    candidates.extend(
        box_candidates_from_horizontal_pairs(
            horizontal=horizontal,
            vertical=vertical,
            boundary_mask=boundary_mask,
            array=array,
            detail_mask=detail_mask,
            background_color=background_color,
            config=config,
            scale=scale,
            start_index=len(candidates) + 1,
            relaxed=enable_relaxed_panel_recovery,
        )
    )
    if enable_relaxed_panel_recovery:
        candidates.extend(
            box_candidates_from_vertical_pairs(
                horizontal=horizontal,
                vertical=vertical,
                boundary_mask=boundary_mask,
                array=array,
                detail_mask=detail_mask,
                background_color=background_color,
                config=config,
                scale=scale,
                start_index=len(candidates) + 1,
            )
        )
    deduped: list[Element] = []
    for candidate in sorted(candidates, key=lambda element: element.confidence, reverse=True):
        if any(boxes_equivalent(candidate, existing) for existing in deduped):
            continue
        deduped.append(candidate)
    return deduped


def fit_fill_region_boxes(
    *,
    mask: np.ndarray,
    boundary_mask: np.ndarray,
    array: np.ndarray,
    smoothed_array: np.ndarray,
    detail_mask: np.ndarray,
    background_color: tuple[int, int, int],
    config: PipelineConfig,
    scale: ScaleContext,
    existing_elements: list[Element],
    start_index: int,
) -> list[Element]:
    if not mask.any():
        return []
    candidate_masks = [mask, *quantized_fill_region_masks(mask, smoothed_array, background_color)]
    min_area = max(
        scale.min_component_area * 6,
        int(round(scale.min_box_size * scale.min_box_size * 1.8)),
    )
    candidates: list[Element] = []
    next_index = start_index
    for candidate_mask in candidate_masks:
        if not candidate_mask.any():
            continue
        for component in sorted(find_connected_components(candidate_mask), key=lambda candidate: candidate.area, reverse=True):
            if component.area < min_area:
                continue
            if component.width < scale.min_box_size * 1.6 or component.height < scale.min_box_size * 1.2:
                continue
            candidate = fit_fill_region_box_from_component(
                component.pixels,
                bbox=component.bbox,
                mask=candidate_mask,
                boundary_mask=boundary_mask,
                array=array,
                smoothed_array=smoothed_array,
                detail_mask=detail_mask,
                background_color=background_color,
                config=config,
                scale=scale,
                element_id=f"box-{next_index}",
            )
            if candidate is None:
                continue
            if any(boxes_equivalent(candidate, existing) for existing in existing_elements + candidates):
                continue
            if nested_fill_candidate(candidate, existing_elements + candidates, scale):
                continue
            candidates.append(candidate)
            next_index += 1
            if len(candidates) >= 8:
                return candidates
    return candidates


def nested_fill_candidate(candidate: Element, existing: list[Element], scale: ScaleContext) -> bool:
    margin = max(4.0, scale.estimated_stroke_width * 3.0)
    for element in existing:
        if element.kind not in {"rect", "rounded_rect"}:
            continue
        if candidate.bbox.area >= element.bbox.area * 0.7:
            continue
        expanded = element.bbox.expand(margin)
        if (
            expanded.contains_point(Point(candidate.bbox.x0, candidate.bbox.y0))
            and expanded.contains_point(Point(candidate.bbox.x1, candidate.bbox.y1))
        ):
            return True
    return False


def quantized_fill_region_masks(
    base_mask: np.ndarray,
    smoothed_array: np.ndarray,
    background_color: tuple[int, int, int],
) -> list[np.ndarray]:
    if not base_mask.any():
        return []
    step = 24
    quantized = (smoothed_array // step).astype(np.int16)
    keys = (
        (quantized[:, :, 0].astype(np.int32) << 16)
        | (quantized[:, :, 1].astype(np.int32) << 8)
        | quantized[:, :, 2].astype(np.int32)
    )
    masked_keys = keys[base_mask]
    if masked_keys.size == 0:
        return []
    unique, counts = np.unique(masked_keys, return_counts=True)
    order = np.argsort(counts)[::-1]
    masks: list[np.ndarray] = []
    for key, count in zip(unique[order][:10], counts[order][:10], strict=False):
        if int(count) < 400:
            continue
        color = (
            int((key >> 16) & 0xFF),
            int((key >> 8) & 0xFF),
            int(key & 0xFF),
        )
        approx_color = tuple(int(channel * step + step / 2) for channel in color)
        if color_distance(approx_color, background_color) < 24.0:
            continue
        color_mask = base_mask & (keys == key)
        color_mask = remove_small_components(color_mask, 200)
        if color_mask.any():
            masks.append(color_mask)
    return masks


def fit_fill_region_box_from_component(
    pixels: np.ndarray,
    *,
    bbox: BBox,
    mask: np.ndarray,
    boundary_mask: np.ndarray,
    array: np.ndarray,
    smoothed_array: np.ndarray,
    detail_mask: np.ndarray,
    background_color: tuple[int, int, int],
    config: PipelineConfig,
    scale: ScaleContext,
    element_id: str,
) -> Element | None:
    local_mask = component_mask(pixels, bbox)
    contour_points = outer_contour_points(local_mask)
    if contour_points is None or len(contour_points) < 16:
        return None
    candidate_bbox = contour_bbox_from_percentiles(
        contour_points,
        bbox,
        trim_ratio=min(config.outer_box_percentile_trim, 0.05),
        scale=scale,
    )
    if candidate_bbox is None:
        return None
    if candidate_bbox.width < scale.min_box_size * 1.5 or candidate_bbox.height < scale.min_box_size:
        return None
    if bbox_touches_image_border(candidate_bbox, array.shape, margin=max(6.0, scale.estimated_stroke_width * 2.5)):
        return None
    density = component_fill_density(mask, candidate_bbox)
    if density < config.fill_region_min_density:
        return None
    corner_hits = fill_region_corner_hits(local_mask, candidate_bbox, bbox, scale)
    if corner_hits < 2:
        return None
    stroke_width = max(1.0, scale.estimated_stroke_width * 0.8)
    top, right, bottom, left = strokes_from_bbox(candidate_bbox, max(1.0, scale.estimated_stroke_width))
    supports = side_supports(boundary_mask, candidate_bbox, top, right, bottom, left)
    borderless = max(supports.values()) < config.outer_box_min_side_support * 0.6
    if not borderless and max(supports.values()) >= config.outer_box_min_side_support and min(supports.values()) < config.outer_box_min_side_support * 0.45:
        return None
    fill_enabled, fill_color = estimate_fill_color(
        array=smoothed_array,
        bbox=candidate_bbox,
        stroke_width=stroke_width,
        background_color=background_color,
        delta_threshold=config.fill_delta_threshold,
        homogeneity_threshold=config.fill_homogeneity_threshold * 0.85,
        detail_mask=detail_mask,
    )
    if not fill_enabled or fill_color is None:
        return None
    border_color = sample_bbox_border_colors(array, candidate_bbox, stroke_width)
    if color_distance(border_color, fill_color) < config.fill_delta_threshold * 0.6:
        stroke_color = fill_color
        stroke_width = 1.0
    else:
        stroke_color = border_color
    rounded = corner_hits <= 3 or contour_looks_rounded(contour_points, candidate_bbox, bbox, config, scale)
    confidence = min(
        0.88,
        0.62
        + min(density, 0.92) * 0.16
        + min(candidate_bbox.width, candidate_bbox.height) / max(scale.min_box_size * 5.0, 1.0) * 0.06,
    )
    if borderless:
        confidence = max(confidence, config.filled_panel_accept_confidence)
    return Element(
        id=element_id,
        kind="rounded_rect" if rounded else "rect",
        geometry=BoxGeometry(
            bbox=candidate_bbox,
            corner_radius=max(6.0, min(candidate_bbox.width, candidate_bbox.height) * config.outer_box_corner_radius_ratio)
            if rounded
            else 0.0,
        ),
        stroke=StrokeStyle(color=stroke_color, width=stroke_width),
        fill=FillStyle(enabled=True, color=fill_color),
        text=None,
        confidence=confidence,
        source_region=candidate_bbox,
        inferred=True,
    )


def component_fill_density(mask: np.ndarray, bbox: BBox) -> float:
    x0 = max(0, int(math.floor(bbox.x0)))
    y0 = max(0, int(math.floor(bbox.y0)))
    x1 = min(mask.shape[1], int(math.ceil(bbox.x1)))
    y1 = min(mask.shape[0], int(math.ceil(bbox.y1)))
    if x1 <= x0 or y1 <= y0:
        return 0.0
    window = mask[y0:y1, x0:x1]
    return float(window.mean()) if window.size else 0.0


def fill_region_corner_hits(
    local_mask: np.ndarray,
    candidate_bbox: BBox,
    component_bbox: BBox,
    scale: ScaleContext,
) -> int:
    local_x0 = max(0, int(round(candidate_bbox.x0 - component_bbox.x0)))
    local_y0 = max(0, int(round(candidate_bbox.y0 - component_bbox.y0)))
    local_x1 = min(local_mask.shape[1] - 1, int(round(candidate_bbox.x1 - component_bbox.x0 - 1.0)))
    local_y1 = min(local_mask.shape[0] - 1, int(round(candidate_bbox.y1 - component_bbox.y0 - 1.0)))
    corner_band = max(
        3,
        int(round(scale.estimated_stroke_width * 3.0)),
        int(round(min(candidate_bbox.width, candidate_bbox.height) * 0.12)),
    )
    hits = 0
    for corner_x, corner_y in (
        (local_x0, local_y0),
        (local_x1, local_y0),
        (local_x0, local_y1),
        (local_x1, local_y1),
    ):
        x0 = max(0, corner_x - corner_band)
        y0 = max(0, corner_y - corner_band)
        x1 = min(local_mask.shape[1], corner_x + corner_band + 1)
        y1 = min(local_mask.shape[0], corner_y + corner_band + 1)
        if x1 <= x0 or y1 <= y0:
            continue
        if local_mask[y0:y1, x0:x1].any():
            hits += 1
    return hits


def box_candidates_from_horizontal_pairs(
    *,
    horizontal: list[Stroke],
    vertical: list[Stroke],
    boundary_mask: np.ndarray,
    array: np.ndarray,
    detail_mask: np.ndarray,
    background_color: tuple[int, int, int],
    config: PipelineConfig,
    scale: ScaleContext,
    start_index: int,
    relaxed: bool,
) -> list[Element]:
    candidates: list[Element] = []
    next_index = start_index
    for top in horizontal:
        for bottom in horizontal:
            if bottom.center_y <= top.center_y + scale.min_box_size:
                continue
            if relaxed:
                left_range, right_range = compatible_horizontal_box_edges(top, bottom, config, scale)
                if left_range is None or right_range is None:
                    continue
                left = best_vertical_for_box(
                    vertical,
                    x_range=left_range,
                    y0=top.center_y,
                    y1=bottom.center_y,
                    config=config,
                    scale=scale,
                )
                right = best_vertical_for_box(
                    vertical,
                    x_range=right_range,
                    y0=top.center_y,
                    y1=bottom.center_y,
                    config=config,
                    scale=scale,
                )
            else:
                edge_tolerance = config.stroke_merge_gap
                if top.inferred or bottom.inferred:
                    edge_tolerance += max(4, int(round(scale.estimated_stroke_width * 3.0)))
                if abs(top.x0 - bottom.x0) > edge_tolerance:
                    continue
                if abs(top.x1 - bottom.x1) > edge_tolerance:
                    continue
                left = best_vertical_for_box(
                    vertical,
                    x_target=min(top.x0, bottom.x0),
                    y0=top.center_y,
                    y1=bottom.center_y,
                    config=config,
                )
                right = best_vertical_for_box(
                    vertical,
                    x_target=max(top.x1, bottom.x1),
                    y0=top.center_y,
                    y1=bottom.center_y,
                    config=config,
                )
            if left is None or right is None:
                continue
            candidate = build_box_candidate(
                top=top,
                right=right,
                bottom=bottom,
                left=left,
                boundary_mask=boundary_mask,
                array=array,
                detail_mask=detail_mask,
                background_color=background_color,
                config=config,
                scale=scale,
                element_id=f"box-{next_index}",
            )
            if candidate is None:
                continue
            candidates.append(candidate)
            next_index += 1
    return candidates


def box_candidates_from_vertical_pairs(
    *,
    horizontal: list[Stroke],
    vertical: list[Stroke],
    boundary_mask: np.ndarray,
    array: np.ndarray,
    detail_mask: np.ndarray,
    background_color: tuple[int, int, int],
    config: PipelineConfig,
    scale: ScaleContext,
    start_index: int,
) -> list[Element]:
    candidates: list[Element] = []
    next_index = start_index
    for left in vertical:
        for right in vertical:
            if right.center_x <= left.center_x + scale.min_box_size:
                continue
            top_range, bottom_range = compatible_vertical_box_edges(left, right, config, scale)
            if top_range is None or bottom_range is None:
                continue
            top = best_horizontal_for_box(
                horizontal,
                y_range=top_range,
                x0=left.center_x,
                x1=right.center_x,
                config=config,
                scale=scale,
            )
            bottom = best_horizontal_for_box(
                horizontal,
                y_range=bottom_range,
                x0=left.center_x,
                x1=right.center_x,
                config=config,
                scale=scale,
            )
            if top is None or bottom is None or bottom.center_y <= top.center_y + scale.min_box_size:
                continue
            candidate = build_box_candidate(
                top=top,
                right=right,
                bottom=bottom,
                left=left,
                boundary_mask=boundary_mask,
                array=array,
                detail_mask=detail_mask,
                background_color=background_color,
                config=config,
                scale=scale,
                element_id=f"box-{next_index}",
            )
            if candidate is None:
                continue
            candidates.append(candidate)
            next_index += 1
    return candidates


def build_box_candidate(
    *,
    top: Stroke,
    right: Stroke,
    bottom: Stroke,
    left: Stroke,
    boundary_mask: np.ndarray,
    array: np.ndarray,
    detail_mask: np.ndarray,
    background_color: tuple[int, int, int],
    config: PipelineConfig,
    scale: ScaleContext,
    element_id: str,
) -> Element | None:
    bbox = BBox(
        min(left.center_x, top.x0, bottom.x0),
        min(top.center_y, left.y0, right.y0),
        max(right.center_x, top.x1, bottom.x1),
        max(bottom.center_y, left.y1, right.y1),
    )
    if bbox.width < scale.min_box_size or bbox.height < scale.min_box_size:
        return None
    supports = side_supports(boundary_mask, bbox, top, right, bottom, left)
    if min(supports.values()) < config.min_side_support:
        return None
    average_support = sum(supports.values()) / len(supports)
    if average_support < config.min_box_support:
        return None
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
    return Element(
        id=element_id,
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


def compatible_horizontal_box_edges(
    top: Stroke,
    bottom: Stroke,
    config: PipelineConfig,
    scale: ScaleContext,
) -> tuple[tuple[float, float] | None, tuple[float, float] | None]:
    top_width = top.x1 - top.x0
    bottom_width = bottom.x1 - bottom.x0
    if top_width < scale.min_box_size or bottom_width < scale.min_box_size:
        return None, None
    overlap_x0 = max(top.x0, bottom.x0)
    overlap_x1 = min(top.x1, bottom.x1)
    overlap = overlap_x1 - overlap_x0
    if overlap < scale.min_box_size * 0.7:
        return None, None
    width_ratio = min(top_width, bottom_width) / max(1.0, max(top_width, bottom_width))
    overlap_ratio = overlap / max(1.0, max(top_width, bottom_width))
    center_delta = abs(top.center_x - bottom.center_x)
    center_tolerance = max(
        config.stroke_merge_gap * 2.5,
        scale.min_box_size * 1.2,
        max(top_width, bottom_width) * 0.18,
    )
    if top.inferred or bottom.inferred:
        center_tolerance += max(4.0, scale.estimated_stroke_width * 4.0)
    if width_ratio < 0.58 or overlap_ratio < 0.62 or center_delta > center_tolerance:
        return None, None
    left_range = (min(top.x0, bottom.x0), max(top.x0, bottom.x0))
    right_range = (min(top.x1, bottom.x1), max(top.x1, bottom.x1))
    return left_range, right_range


def compatible_vertical_box_edges(
    left: Stroke,
    right: Stroke,
    config: PipelineConfig,
    scale: ScaleContext,
) -> tuple[tuple[float, float] | None, tuple[float, float] | None]:
    left_height = left.y1 - left.y0
    right_height = right.y1 - right.y0
    if left_height < scale.min_box_size or right_height < scale.min_box_size:
        return None, None
    overlap_y0 = max(left.y0, right.y0)
    overlap_y1 = min(left.y1, right.y1)
    overlap = overlap_y1 - overlap_y0
    if overlap < scale.min_box_size * 0.7:
        return None, None
    height_ratio = min(left_height, right_height) / max(1.0, max(left_height, right_height))
    overlap_ratio = overlap / max(1.0, max(left_height, right_height))
    center_delta = abs(left.center_y - right.center_y)
    center_tolerance = max(
        config.stroke_merge_gap * 2.5,
        scale.min_box_size * 1.2,
        max(left_height, right_height) * 0.18,
    )
    if left.inferred or right.inferred:
        center_tolerance += max(4.0, scale.estimated_stroke_width * 4.0)
    if height_ratio < 0.58 or overlap_ratio < 0.62 or center_delta > center_tolerance:
        return None, None
    top_range = (min(left.y0, right.y0), max(left.y0, right.y0))
    bottom_range = (min(left.y1, right.y1), max(left.y1, right.y1))
    return top_range, bottom_range


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


def fit_component_box_from_outer_contour(
    pixels: np.ndarray,
    *,
    bbox: BBox,
    boundary_mask: np.ndarray,
    array: np.ndarray,
    detail_mask: np.ndarray,
    background_color: tuple[int, int, int],
    config: PipelineConfig,
    scale: ScaleContext,
    element_id: str,
) -> Element | None:
    local_mask = component_mask(pixels, bbox)
    contour_points = outer_contour_points(local_mask)
    if contour_points is None or len(contour_points) < 12:
        return None
    candidate_bbox = contour_bbox_from_percentiles(
        contour_points,
        bbox,
        trim_ratio=config.outer_box_percentile_trim,
        scale=scale,
    )
    if candidate_bbox is None:
        return None
    if candidate_bbox.width < scale.min_box_size or candidate_bbox.height < scale.min_box_size:
        return None
    if min(candidate_bbox.width, candidate_bbox.height) < scale.min_box_size * 0.9:
        return None
    if candidate_bbox.width / max(1.0, candidate_bbox.height) > 12.0:
        return None
    if candidate_bbox.height / max(1.0, candidate_bbox.width) > 12.0:
        return None
    if bbox_touches_image_border(candidate_bbox, array.shape, margin=max(4.0, scale.estimated_stroke_width * 2.0)):
        return None
    stroke_width = estimate_contour_stroke_width(local_mask, scale)
    candidate_bbox = snap_box_edges_to_boundary(boundary_mask, candidate_bbox, stroke_width, scale)
    top, right, bottom, left = strokes_from_bbox(candidate_bbox, stroke_width)
    supports = side_supports(boundary_mask, candidate_bbox, top, right, bottom, left)
    if min(supports.values()) < config.outer_box_min_side_support:
        return None
    average_support = sum(supports.values()) / len(supports)
    if average_support < config.outer_box_min_support:
        return None
    fill_enabled, fill_color = estimate_fill_color(
        array=array,
        bbox=candidate_bbox,
        stroke_width=stroke_width,
        background_color=background_color,
        delta_threshold=config.fill_delta_threshold,
        homogeneity_threshold=config.fill_homogeneity_threshold,
        detail_mask=detail_mask,
    )
    if average_support < config.min_box_support:
        fill_enabled = False
        fill_color = None
    stroke_color = sample_bbox_border_colors(array, candidate_bbox, stroke_width)
    inferred = min(supports.values()) < config.min_side_support or average_support < config.min_box_support
    rounded = contour_looks_rounded(contour_points, candidate_bbox, bbox, config, scale)
    confidence = min(
        0.94,
        0.70
        + average_support * 0.20
        + min(candidate_bbox.width, candidate_bbox.height) / max(scale.min_box_size * 4.0, 1.0) * 0.02
        - (0.03 if inferred else 0.0),
    )
    return Element(
        id=element_id,
        kind="rounded_rect" if rounded else "rect",
        geometry=BoxGeometry(
            bbox=candidate_bbox,
            corner_radius=max(6.0, min(candidate_bbox.width, candidate_bbox.height) * config.outer_box_corner_radius_ratio)
            if rounded
            else 0.0,
        ),
        stroke=StrokeStyle(color=stroke_color, width=stroke_width),
        fill=FillStyle(enabled=fill_enabled, color=fill_color),
        text=None,
        confidence=confidence,
        source_region=candidate_bbox,
        inferred=inferred,
    )


def outer_contour_points(mask: np.ndarray) -> np.ndarray | None:
    if cv2 is None:
        return None
    mask_u8 = (mask.astype(np.uint8) * 255)
    contours, _ = cv2.findContours(mask_u8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        return None
    contour = max(contours, key=cv2.contourArea)
    if contour.ndim != 3 or contour.shape[1] != 1:
        return None
    return contour[:, 0, :].astype(np.float32)


def contour_bbox_from_percentiles(
    contour_points: np.ndarray,
    bbox: BBox,
    *,
    trim_ratio: float,
    scale: ScaleContext,
) -> BBox | None:
    if contour_points.size == 0:
        return None
    trim = float(np.clip(trim_ratio, 0.0, 0.18)) * 100.0
    xs = contour_points[:, 0]
    ys = contour_points[:, 1]
    x0 = float(np.percentile(xs, trim))
    x1 = float(np.percentile(xs, 100.0 - trim))
    y0 = float(np.percentile(ys, trim))
    y1 = float(np.percentile(ys, 100.0 - trim))
    expand = max(1.0, scale.estimated_stroke_width * 1.4)
    candidate = BBox(
        bbox.x0 + max(0.0, x0 - expand),
        bbox.y0 + max(0.0, y0 - expand),
        bbox.x0 + min(bbox.width, x1 + expand + 1.0),
        bbox.y0 + min(bbox.height, y1 + expand + 1.0),
    )
    if candidate.width <= 0 or candidate.height <= 0:
        return None
    return candidate


def estimate_contour_stroke_width(mask: np.ndarray, scale: ScaleContext) -> float:
    horizontal_profile = mask.sum(axis=1)
    vertical_profile = mask.sum(axis=0)
    bands = [
        end - start
        for start, end in profile_bands(horizontal_profile, threshold=max(1, int(round(mask.shape[1] * 0.18))))
    ]
    bands.extend(
        end - start
        for start, end in profile_bands(vertical_profile, threshold=max(1, int(round(mask.shape[0] * 0.18))))
    )
    if bands:
        return float(np.clip(np.median(np.asarray(bands, dtype=np.float32)), 1.0, scale.estimated_stroke_width * 3.4))
    return max(1.0, scale.estimated_stroke_width)


def snap_box_edges_to_boundary(
    boundary_mask: np.ndarray,
    bbox: BBox,
    stroke_width: float,
    scale: ScaleContext,
) -> BBox:
    search = max(4, int(round(scale.min_box_size * 0.9)))
    top_y = best_supported_edge(
        boundary_mask,
        bbox,
        fixed=bbox.y0,
        search=search,
        orientation="horizontal",
        stroke_width=stroke_width,
    )
    bottom_y = best_supported_edge(
        boundary_mask,
        bbox,
        fixed=bbox.y1,
        search=search,
        orientation="horizontal",
        stroke_width=stroke_width,
    )
    provisional = BBox(bbox.x0, min(top_y, bottom_y), bbox.x1, max(top_y, bottom_y))
    left_x = best_supported_edge(
        boundary_mask,
        provisional,
        fixed=provisional.x0,
        search=search,
        orientation="vertical",
        stroke_width=stroke_width,
    )
    right_x = best_supported_edge(
        boundary_mask,
        provisional,
        fixed=provisional.x1,
        search=search,
        orientation="vertical",
        stroke_width=stroke_width,
    )
    snapped = BBox(min(left_x, right_x), provisional.y0, max(left_x, right_x), provisional.y1)
    if snapped.width <= scale.min_box_size * 0.7 or snapped.height <= scale.min_box_size * 0.7:
        return bbox
    return snapped


def best_supported_edge(
    boundary_mask: np.ndarray,
    bbox: BBox,
    *,
    fixed: float,
    search: int,
    orientation: str,
    stroke_width: float,
) -> float:
    best_value = fixed
    if orientation == "horizontal":
        best_score = line_support(boundary_mask, bbox.x0, bbox.x1, fixed, orientation, stroke_width)
        for delta in range(-search, search + 1):
            candidate = fixed + delta
            score = line_support(boundary_mask, bbox.x0, bbox.x1, candidate, orientation, stroke_width)
            if score > best_score:
                best_value = candidate
                best_score = score
        return best_value
    best_score = line_support(boundary_mask, bbox.y0, bbox.y1, fixed, orientation, stroke_width)
    for delta in range(-search, search + 1):
        candidate = fixed + delta
        score = line_support(boundary_mask, bbox.y0, bbox.y1, candidate, orientation, stroke_width)
        if score > best_score:
            best_value = candidate
            best_score = score
    return best_value


def strokes_from_bbox(bbox: BBox, stroke_width: float) -> tuple[Stroke, Stroke, Stroke, Stroke]:
    top = Stroke("horizontal", bbox.x0, bbox.y0, bbox.x1, bbox.y0 + stroke_width, stroke_width)
    right = Stroke("vertical", bbox.x1 - stroke_width, bbox.y0, bbox.x1, bbox.y1, stroke_width)
    bottom = Stroke("horizontal", bbox.x0, bbox.y1 - stroke_width, bbox.x1, bbox.y1, stroke_width)
    left = Stroke("vertical", bbox.x0, bbox.y0, bbox.x0 + stroke_width, bbox.y1, stroke_width)
    return top, right, bottom, left


def contour_looks_rounded(
    contour_points: np.ndarray,
    bbox: BBox,
    source_bbox: BBox,
    config: PipelineConfig,
    scale: ScaleContext,
) -> bool:
    local_x = contour_points[:, 0]
    local_y = contour_points[:, 1]
    local_x0 = bbox.x0 - source_bbox.x0
    local_y0 = bbox.y0 - source_bbox.y0
    local_x1 = bbox.x1 - source_bbox.x0
    local_y1 = bbox.y1 - source_bbox.y0
    width = max(1.0, local_x1 - local_x0)
    height = max(1.0, local_y1 - local_y0)
    corner_band = max(scale.estimated_stroke_width * 3.0, min(width, height) * config.outer_box_corner_radius_ratio)
    corner_hits = 0
    for corner_x, corner_y in (
        (local_x0, local_y0),
        (local_x1, local_y0),
        (local_x0, local_y1),
        (local_x1, local_y1),
    ):
        distances = np.hypot(local_x - corner_x, local_y - corner_y)
        if np.any(distances <= corner_band):
            corner_hits += 1
    return corner_hits <= 2


def bbox_touches_image_border(bbox: BBox, image_shape: tuple[int, ...], *, margin: float) -> bool:
    height, width = image_shape[:2]
    return (
        bbox.x0 <= margin
        or bbox.y0 <= margin
        or bbox.x1 >= width - margin
        or bbox.y1 >= height - margin
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
    proposal_strength: str = "strong",
) -> Element | None:
    points = line_fitting_points(pixels, bbox, proposal_strength=proposal_strength)
    min_component_area = scale.min_component_area if scale is not None else config.min_component_area
    min_linear_length = scale.min_linear_length if scale is not None else max(
        config.min_stroke_length,
        int(round(max(array.shape[0], array.shape[1]) * config.min_relative_line_length)),
    )
    min_point_count = min_component_area if proposal_strength == "strong" else max(12, min_component_area // 3)
    if len(points) < min_point_count:
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
    aspect_threshold = config.min_line_aspect_ratio
    continuity_threshold = 0.82
    min_length_threshold = float(min_linear_length)
    if proposal_strength == "weak":
        aspect_threshold = min(aspect_threshold, config.weak_line_aspect_ratio)
        continuity_threshold = config.weak_line_continuity
        min_length_threshold *= config.weak_line_min_length_ratio
    if aspect < aspect_threshold:
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
    if length < min_length_threshold:
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
    ambiguous_wedge = (
        max(start_widen, end_widen) >= config.min_arrow_widen_ratio
        and abs(start_widen - end_widen) <= 0.25
    )
    if ambiguous_wedge:
        return None
    straight_orth_limit = max(config.max_straight_orth_error, approx_width * (0.8 if arrow_candidate else 0.55))
    if proposal_strength == "weak":
        straight_orth_limit *= config.weak_line_orth_error_scale
    if orth_error > straight_orth_limit:
        return None
    if continuity < continuity_threshold:
        return None
    if features is not None:
        if features.near_structure_count == 0 and length < min_linear_length * (1.5 if proposal_strength == "strong" else 1.15):
            return None
        if not arrow_candidate and features.branchiness > (0.45 if proposal_strength == "strong" else 0.68):
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
    proposal_strength: str = "strong",
) -> Element | None:
    local_mask_full = component_mask(pixels, bbox)
    if proposal_strength == "weak":
        contour_outline = outer_contour_outline_mask(local_mask_full)
        if contour_outline is not None:
            local_mask_full = contour_outline
    local_mask = build_boundary_mask(local_mask_full)
    min_stroke_length = scale.min_stroke_length if scale is not None else config.min_stroke_length
    min_linear_length = scale.min_linear_length if scale is not None else max(
        config.min_stroke_length,
        int(round(max(array.shape[0], array.shape[1]) * config.min_relative_line_length)),
    )
    min_length = max(8, config.connector_min_segment_length // 2, min_stroke_length // (4 if proposal_strength == "weak" else 3))
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
    coverage_threshold = config.connector_min_coverage if proposal_strength == "strong" else max(0.60, config.connector_min_coverage - 0.12)
    if coverage < coverage_threshold:
        return None
    path_length = polyline_length(local_points)
    path_length_threshold = min_linear_length * (1.1 if proposal_strength == "strong" else 0.85)
    if path_length < path_length_threshold:
        return None
    if features is not None:
        if features.near_structure_count == 0 and path_length < min_linear_length * (1.5 if proposal_strength == "strong" else 1.1):
            return None
        if features.density > (0.48 if proposal_strength == "strong" else 0.60):
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
        confidence=min(
            0.96,
            (0.72 if proposal_strength == "strong" else 0.68)
            + coverage * 0.24
            + min(len(global_points), 5) * 0.01,
        ),
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


def line_fitting_points(
    pixels: np.ndarray,
    bbox: BBox,
    *,
    proposal_strength: str,
) -> np.ndarray:
    if proposal_strength != "weak":
        return np.column_stack((pixels[:, 1].astype(np.float32), pixels[:, 0].astype(np.float32)))
    local_mask = component_mask(pixels, bbox)
    contour_points = outer_contour_points(local_mask)
    if contour_points is None or len(contour_points) < 8:
        return np.column_stack((pixels[:, 1].astype(np.float32), pixels[:, 0].astype(np.float32)))
    contour_points = contour_points.copy()
    contour_points[:, 0] += float(bbox.x0)
    contour_points[:, 1] += float(bbox.y0)
    return contour_points.astype(np.float32)


def outer_contour_outline_mask(mask: np.ndarray) -> np.ndarray | None:
    if cv2 is None:
        return None
    mask_u8 = (mask.astype(np.uint8) * 255)
    contours, _ = cv2.findContours(mask_u8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        return None
    outline = np.zeros_like(mask_u8)
    cv2.drawContours(outline, [max(contours, key=cv2.contourArea)], -1, 255, thickness=max(1, int(round(max(mask.shape) / 180.0))))
    return outline.astype(bool)


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
    y0 = max(0, int(math.floor(bbox.y0)))
    y1 = min(array.shape[0], int(math.ceil(bbox.y1)))
    x0 = max(0, int(math.floor(bbox.x0)))
    x1 = min(array.shape[1], int(math.ceil(bbox.x1)))
    local_array = array[y0:y1, x0:x1, :]
    local_gray = local_array.astype(np.float32) @ np.asarray([0.299, 0.587, 0.114], dtype=np.float32)
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
    merge_gap = max(config.stroke_merge_gap, int(round(min_linear_length * 0.9)))
    bridge_config = replace(config, stroke_merge_gap=merge_gap)
    segments = merge_collinear_gaps(
        segments,
        bridge_config,
        mask=local_mask,
        array=local_array,
        gray=local_gray,
    )
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


def fit_global_stroke_lines(
    *,
    horizontal: list[Stroke],
    vertical: list[Stroke],
    array: np.ndarray,
    gray: np.ndarray,
    config: PipelineConfig,
    scale: ScaleContext,
    structural_elements: list[Element],
    start_index: int,
) -> list[Element]:
    min_length = max(scale.min_linear_length * 1.5, scale.min_box_size * 1.8)
    candidates = sorted(
        [stroke for stroke in horizontal + vertical if stroke.length >= min_length],
        key=lambda stroke: stroke.length,
        reverse=True,
    )
    elements: list[Element] = []
    next_index = start_index
    for stroke in candidates:
        if stroke_matches_box_edge(stroke, structural_elements, scale):
            continue
        if sample_stroke_darkness(gray, stroke) < 18.0:
            continue
        geometry = global_stroke_geometry(stroke)
        connection_count = stroke_connection_count(geometry.points[0], geometry.points[-1], structural_elements, scale)
        if stroke_touches_border(stroke, array.shape, margin=max(16.0, scale.min_box_size * 1.2)) and connection_count < 2:
            continue
        if connection_count == 0 and stroke.length < scale.min_linear_length * 2.8:
            continue
        if any(geometry.bbox.iou(existing.bbox) >= 0.72 for existing in elements):
            continue
        elements.append(
            Element(
                id=f"linear-{next_index}",
                kind="line",
                geometry=geometry,
                stroke=StrokeStyle(
                    color=sample_stroke_color(array, stroke),
                    width=max(1.0, stroke.thickness),
                ),
                fill=FillStyle(enabled=False, color=None),
                text=None,
                confidence=min(
                    0.90,
                    0.74
                    + min(stroke.length / max(1.0, scale.min_linear_length * 1.5), 2.0) * 0.05
                    + min(connection_count, 2) * 0.03,
                ),
                source_region=geometry.bbox,
                inferred=stroke.inferred,
            )
        )
        next_index += 1
        if len(elements) >= 6:
            break
    return elements


def fit_hough_segment_elements(
    *,
    mask: np.ndarray,
    array: np.ndarray,
    gray: np.ndarray,
    bridge_mask: np.ndarray | None,
    config: PipelineConfig,
    scale: ScaleContext,
    structural_elements: list[Element],
    existing_elements: list[Element],
    start_index: int,
) -> list[Element]:
    if cv2 is None or not mask.any():
        return []
    mask_u8 = (mask.astype(np.uint8) * 255)
    threshold = max(16, int(round(scale.min_linear_length * config.hough_threshold_ratio)))
    min_length = max(10, int(round(scale.min_linear_length * config.hough_min_length_ratio)))
    max_gap = max(config.stroke_merge_gap, int(round(scale.min_linear_length * config.hough_bridge_gap_ratio)))
    detected = cv2.HoughLinesP(
        mask_u8,
        1.0,
        np.pi / 180.0,
        threshold=threshold,
        minLineLength=min_length,
        maxLineGap=max(4, int(round(scale.estimated_stroke_width * 4.0))),
    )
    if detected is None:
        return []
    raw_strokes = hough_axis_strokes(detected, mask=mask, scale=scale, min_length=min_length)
    if not raw_strokes:
        return []
    bridge_config = replace(config, stroke_merge_gap=max_gap)
    merged = merge_parallel_strokes(
        raw_strokes,
        bridge_config,
        mask=mask,
        array=array,
        gray=gray,
        allow_gap_merge=True,
        bridge_mask=bridge_mask,
    )
    connector_config = replace(config, connector_max_segments=max(config.connector_max_segments, 5))
    connectors, used_indices = hough_connector_elements(
        merged,
        mask=mask,
        array=array,
        config=connector_config,
        scale=scale,
        bridge_mask=bridge_mask,
        structural_elements=structural_elements,
        existing_elements=existing_elements,
        start_index=start_index,
    )
    elements = connectors[:]
    next_index = start_index + len(connectors)
    ordered = sorted(enumerate(merged), key=lambda item: item[1].length, reverse=True)
    for original_index, stroke in ordered:
        if original_index in used_indices:
            continue
        if stroke.length < scale.min_linear_length:
            continue
        if stroke_matches_box_edge(stroke, structural_elements, scale):
            continue
        if sample_stroke_darkness(gray, stroke) < 18.0:
            continue
        geometry = global_stroke_geometry(stroke)
        connection_count = stroke_connection_count(geometry.points[0], geometry.points[-1], structural_elements, scale)
        if stroke_touches_border(stroke, array.shape, margin=max(16.0, scale.min_box_size * 1.2)) and connection_count < 2:
            continue
        if connection_count == 0 and stroke.length < scale.min_linear_length * 1.8:
            continue
        if any(geometry.bbox.iou(existing.bbox) >= 0.72 for existing in existing_elements + elements):
            continue
        elements.append(
            Element(
                id=f"linear-{next_index}",
                kind="line",
                geometry=geometry,
                stroke=StrokeStyle(color=sample_stroke_color(array, stroke), width=max(1.0, stroke.thickness)),
                fill=FillStyle(enabled=False, color=None),
                text=None,
                confidence=min(
                    0.92,
                    0.72
                    + min(stroke.length / max(1.0, scale.min_linear_length * 1.25), 2.2) * 0.05
                    + min(connection_count, 2) * 0.03,
                ),
                source_region=geometry.bbox,
                inferred=stroke.inferred,
            )
        )
        next_index += 1
    return elements


def hough_axis_strokes(
    detected: np.ndarray,
    *,
    mask: np.ndarray,
    scale: ScaleContext,
    min_length: int,
) -> list[Stroke]:
    strokes: list[Stroke] = []
    axis_tolerance = max(3.0, scale.estimated_stroke_width * 2.8)
    for candidate in detected[:, 0, :]:
        x0, y0, x1, y1 = (float(value) for value in candidate)
        dx = x1 - x0
        dy = y1 - y0
        length = math.hypot(dx, dy)
        if length < min_length:
            continue
        if abs(dx) >= abs(dy):
            if abs(dy) > axis_tolerance:
                continue
            y = (y0 + y1) / 2.0
            thickness = estimate_hough_stroke_thickness(mask, "horizontal", x0=min(x0, x1), x1=max(x0, x1), fixed=y, scale=scale)
            strokes.append(
                Stroke(
                    orientation="horizontal",
                    x0=min(x0, x1),
                    y0=y - thickness / 2.0,
                    x1=max(x0, x1),
                    y1=y + thickness / 2.0,
                    thickness=thickness,
                )
            )
            continue
        if abs(dx) > axis_tolerance:
            continue
        x = (x0 + x1) / 2.0
        thickness = estimate_hough_stroke_thickness(mask, "vertical", y0=min(y0, y1), y1=max(y0, y1), fixed=x, scale=scale)
        strokes.append(
            Stroke(
                orientation="vertical",
                x0=x - thickness / 2.0,
                y0=min(y0, y1),
                x1=x + thickness / 2.0,
                y1=max(y0, y1),
                thickness=thickness,
            )
        )
    return strokes


def estimate_hough_stroke_thickness(
    mask: np.ndarray,
    orientation: str,
    *,
    fixed: float,
    scale: ScaleContext,
    x0: float = 0.0,
    x1: float = 0.0,
    y0: float = 0.0,
    y1: float = 0.0,
) -> float:
    band = max(2, int(round(scale.estimated_stroke_width * 2.0)))
    if orientation == "horizontal":
        ix0 = max(0, int(math.floor(x0)))
        ix1 = min(mask.shape[1], int(math.ceil(x1)))
        iy0 = max(0, int(round(fixed)) - band)
        iy1 = min(mask.shape[0], int(round(fixed)) + band + 1)
        if ix1 <= ix0 or iy1 <= iy0:
            return max(1.0, scale.estimated_stroke_width)
        profile = mask[iy0:iy1, ix0:ix1].sum(axis=1)
    else:
        ix0 = max(0, int(round(fixed)) - band)
        ix1 = min(mask.shape[1], int(round(fixed)) + band + 1)
        iy0 = max(0, int(math.floor(y0)))
        iy1 = min(mask.shape[0], int(math.ceil(y1)))
        if ix1 <= ix0 or iy1 <= iy0:
            return max(1.0, scale.estimated_stroke_width)
        profile = mask[iy0:iy1, ix0:ix1].sum(axis=0)
    active = np.count_nonzero(profile > 0)
    if active == 0:
        return max(1.0, scale.estimated_stroke_width)
    return float(np.clip(active, 1.0, scale.estimated_stroke_width * 3.4))


def hough_connector_elements(
    strokes: list[Stroke],
    *,
    mask: np.ndarray,
    array: np.ndarray,
    config: PipelineConfig,
    scale: ScaleContext,
    bridge_mask: np.ndarray | None,
    structural_elements: list[Element],
    existing_elements: list[Element],
    start_index: int,
) -> tuple[list[Element], set[int]]:
    adjacency = build_global_stroke_graph(strokes, scale=scale, config=config, bridge_mask=bridge_mask)
    groups = stroke_graph_components(adjacency)
    elements: list[Element] = []
    used: set[int] = set()
    next_index = start_index
    for group in groups:
        if len(group) < 2:
            continue
        if any(index in used for index in group):
            continue
        path = longest_stroke_path(group, adjacency, strokes, config)
        if len(path) < 2:
            continue
        geometry, path_kind, bridge_edges = stroke_path_geometry(path, adjacency, strokes, config)
        if geometry is None or path_kind is None:
            continue
        band = max(1, int(round(median([strokes[index].thickness for index in path]))))
        coverage = connector_pixel_coverage(mask, geometry.points, band=max(1, band))
        coverage_threshold = max(0.50, config.connector_min_coverage - 0.24)
        if bridge_edges > 0:
            coverage_threshold = max(0.34, coverage_threshold - 0.14)
        if coverage < coverage_threshold:
            continue
        path_length = polyline_length(geometry.points)
        if path_length < scale.min_linear_length * (0.70 if bridge_edges > 0 else 0.85):
            continue
        endpoint_hits = stroke_connection_count(geometry.points[0], geometry.points[-1], structural_elements, scale)
        if path_kind == "line" and endpoint_hits == 0 and bridge_edges == 0 and path_length < scale.min_linear_length * 1.6:
            continue
        if (
            path_kind == "orthogonal_connector"
            and endpoint_hits == 0
            and bridge_edges == 0
            and (
                path_length < scale.min_linear_length * 2.2
                or max(geometry.bbox.width, geometry.bbox.height) / max(1.0, min(geometry.bbox.width, geometry.bbox.height)) < 1.35
            )
        ):
            continue
        if endpoint_hits == 0 and bridge_edges == 0 and path_length < scale.min_linear_length * 1.5:
            continue
        if any(
            geometry.bbox.iou(existing.bbox) >= 0.72
            for existing in existing_elements + elements
            if existing.kind in {"line", "orthogonal_connector", "arrow"}
        ):
            continue
        resolved_kind = path_kind
        if path_kind == "line":
            start_ratio, end_ratio = polyline_endpoint_widening(mask, geometry, band=max(2, band))
            if max(start_ratio, end_ratio) >= config.min_arrow_widen_ratio and abs(start_ratio - end_ratio) > 0.25:
                resolved_kind = "arrow"
                geometry = orient_arrow_geometry(geometry, tip_on_max_axis=end_ratio >= start_ratio)
        anchor = max((strokes[index] for index in group), key=lambda candidate: candidate.length)
        elements.append(
            Element(
                id=f"linear-{next_index}",
                kind=resolved_kind,
                geometry=geometry,
                stroke=StrokeStyle(color=sample_stroke_color(array, anchor), width=max(1.0, band * 1.5)),
                fill=FillStyle(enabled=False, color=None),
                text=None,
                confidence=min(
                    0.95,
                    0.70
                    + coverage * 0.20
                    + min(len(geometry.points), 6) * 0.01
                    + min(endpoint_hits, 2) * 0.02
                    + min(bridge_edges, 2) * 0.03,
                ),
                source_region=geometry.bbox,
                inferred=any(strokes[index].inferred for index in group),
            )
        )
        used.update(path)
        next_index += 1
    return elements, used


def build_global_stroke_graph(
    strokes: list[Stroke],
    *,
    scale: ScaleContext,
    config: PipelineConfig,
    bridge_mask: np.ndarray | None,
) -> dict[int, list[StrokeGraphEdge]]:
    adjacency: dict[int, list[StrokeGraphEdge]] = {index: [] for index in range(len(strokes))}
    for left in range(len(strokes)):
        for right in range(left + 1, len(strokes)):
            edge = stroke_graph_edge(
                strokes[left],
                strokes[right],
                scale=scale,
                config=config,
                bridge_mask=bridge_mask,
            )
            if edge is None:
                continue
            adjacency[left].append(StrokeGraphEdge(neighbor=right, kind=edge.kind, bridge_ratio=edge.bridge_ratio))
            adjacency[right].append(StrokeGraphEdge(neighbor=left, kind=edge.kind, bridge_ratio=edge.bridge_ratio))
    return adjacency


def stroke_graph_edge(
    first: Stroke,
    second: Stroke,
    *,
    scale: ScaleContext,
    config: PipelineConfig,
    bridge_mask: np.ndarray | None,
) -> StrokeGraphEdge | None:
    if first.orientation == second.orientation:
        if not strokes_are_collinear(first, second, scale=scale, config=config):
            return None
        bridge_ratio = stroke_gap_bridge_ratio(first, second, bridge_mask)
        gap = stroke_interval_gap(first, second)
        endpoint_gap = min_stroke_endpoint_distance(first, second)
        if bridge_ratio >= config.global_graph_bridge_ratio or endpoint_gap <= max(config.global_graph_endpoint_margin, scale.estimated_stroke_width * 8.0) or gap <= max(config.stroke_merge_gap * 2.5, scale.min_linear_length * 0.4):
            return StrokeGraphEdge(neighbor=-1, kind="collinear", bridge_ratio=bridge_ratio)
        return None
    tolerance = max(config.global_graph_endpoint_margin * 0.5, scale.estimated_stroke_width * 4.0)
    if strokes_interact(first, second, tolerance=tolerance) or min_stroke_endpoint_distance(first, second) <= tolerance:
        return StrokeGraphEdge(neighbor=-1, kind="junction", bridge_ratio=0.0)
    return None


def stroke_graph_components(adjacency: dict[int, list[StrokeGraphEdge]]) -> list[list[int]]:
    groups: list[list[int]] = []
    visited: set[int] = set()
    for start in adjacency:
        if start in visited:
            continue
        stack = [start]
        group: list[int] = []
        visited.add(start)
        while stack:
            current = stack.pop()
            group.append(current)
            for edge in adjacency[current]:
                neighbor = edge.neighbor
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                stack.append(neighbor)
        groups.append(sorted(group))
    return groups


def longest_stroke_path(
    group: list[int],
    adjacency: dict[int, list[StrokeGraphEdge]],
    strokes: list[Stroke],
    config: PipelineConfig,
) -> list[int]:
    node_set = set(group)
    degrees = {node: sum(1 for edge in adjacency[node] if edge.neighbor in node_set) for node in group}
    starts = [node for node in group if degrees[node] <= 1] or group
    if len(group) > config.global_graph_max_component:
        return greedy_stroke_path(starts, adjacency, strokes, node_set)
    best_path: list[int] = []
    best_score = -1.0

    def dfs(node: int, visited: set[int], path: list[int], score: float) -> None:
        nonlocal best_path, best_score
        if score > best_score:
            best_score = score
            best_path = path[:]
        neighbors = sorted(
            (
                edge
                for edge in adjacency[node]
                if edge.neighbor in node_set and edge.neighbor not in visited
            ),
            key=lambda edge: strokes[edge.neighbor].length + edge.bridge_ratio * 120.0,
            reverse=True,
        )
        for edge in neighbors:
            visited.add(edge.neighbor)
            dfs(
                edge.neighbor,
                visited,
                path + [edge.neighbor],
                score + strokes[edge.neighbor].length + edge.bridge_ratio * 40.0,
            )
            visited.remove(edge.neighbor)

    for start in starts:
        dfs(start, {start}, [start], strokes[start].length)
    return best_path


def greedy_stroke_path(
    starts: list[int],
    adjacency: dict[int, list[StrokeGraphEdge]],
    strokes: list[Stroke],
    node_set: set[int],
) -> list[int]:
    start = max(starts, key=lambda node: strokes[node].length)
    path = [start]
    visited = {start}
    while True:
        head = path[-1]
        candidates = [
            edge
            for edge in adjacency[head]
            if edge.neighbor in node_set and edge.neighbor not in visited
        ]
        if not candidates:
            break
        edge = max(candidates, key=lambda item: strokes[item.neighbor].length + item.bridge_ratio * 120.0)
        path.append(edge.neighbor)
        visited.add(edge.neighbor)
    return path


def stroke_path_geometry(
    path: list[int],
    adjacency: dict[int, list[StrokeGraphEdge]],
    strokes: list[Stroke],
    config: PipelineConfig,
) -> tuple[PolylineGeometry | None, str | None, int]:
    path_strokes = [strokes[index] for index in path]
    bridge_edges = count_path_bridge_edges(path, adjacency)
    if all(stroke.orientation == path_strokes[0].orientation for stroke in path_strokes):
        geometry = merged_collinear_path_geometry(path_strokes)
        return geometry, "line", bridge_edges
    interfaces = [
        stroke_interface_point(first, second)
        for first, second in zip(path_strokes[:-1], path_strokes[1:], strict=True)
    ]
    if any(point is None for point in interfaces):
        return None, None, bridge_edges
    interface_points = [point for point in interfaces if point is not None]
    if not interface_points:
        return None, None, bridge_edges
    points: list[Point] = [path_endpoint_away_from_interface(path_strokes[0], interface_points[0])]
    points.extend(interface_points)
    points.append(path_endpoint_away_from_interface(path_strokes[-1], interface_points[-1]))
    compressed = compress_point_path(points)
    if len(compressed) < 2:
        return None, None, bridge_edges
    if len(compressed) - 1 > config.global_connector_max_segments:
        compressed = simplify_point_path(compressed, max_segments=config.global_connector_max_segments)
    if len(compressed) < 2:
        return None, None, bridge_edges
    kind = "line" if len(compressed) == 2 else "orthogonal_connector"
    return PolylineGeometry(points=tuple(compressed)), kind, bridge_edges


def count_path_bridge_edges(path: list[int], adjacency: dict[int, list[StrokeGraphEdge]]) -> int:
    count = 0
    for left, right in zip(path[:-1], path[1:], strict=True):
        for edge in adjacency[left]:
            if edge.neighbor == right and edge.bridge_ratio >= 0.01:
                count += 1
                break
    return count


def merged_collinear_path_geometry(strokes: list[Stroke]) -> PolylineGeometry:
    orientation = strokes[0].orientation
    if orientation == "horizontal":
        y = float(np.median([stroke.center_y for stroke in strokes]))
        x0 = min(stroke.x0 for stroke in strokes)
        x1 = max(stroke.x1 for stroke in strokes)
        return PolylineGeometry(points=(Point(float(x0), y), Point(float(x1), y)))
    x = float(np.median([stroke.center_x for stroke in strokes]))
    y0 = min(stroke.y0 for stroke in strokes)
    y1 = max(stroke.y1 for stroke in strokes)
    return PolylineGeometry(points=(Point(x, float(y0)), Point(x, float(y1))))


def stroke_interface_point(first: Stroke, second: Stroke) -> Point | None:
    if first.orientation == second.orientation:
        if first.orientation == "horizontal":
            if first.center_x <= second.center_x:
                x = max(first.x1, min(second.x0, second.x1))
            else:
                x = max(second.x1, min(first.x0, first.x1))
            return Point(float((first.x1 + second.x0) / 2.0 if second.x0 >= first.x1 else (max(first.x0, second.x0) + min(first.x1, second.x1)) / 2.0), float((first.center_y + second.center_y) / 2.0))
        return Point(float((first.center_x + second.center_x) / 2.0), float((first.y1 + second.y0) / 2.0 if second.y0 >= first.y1 else (max(first.y0, second.y0) + min(first.y1, second.y1)) / 2.0))
    horizontal = first if first.orientation == "horizontal" else second
    vertical = second if first.orientation == "horizontal" else first
    return Point(float(vertical.center_x), float(horizontal.center_y))


def path_endpoint_away_from_interface(stroke: Stroke, interface: Point) -> Point:
    endpoints = stroke_endpoints(stroke)
    return max(endpoints, key=lambda point: gap_between_path_points(point, interface))


def stroke_endpoints(stroke: Stroke) -> tuple[Point, Point]:
    if stroke.orientation == "horizontal":
        point_y = float(stroke.center_y)
        return (Point(float(stroke.x0), point_y), Point(float(stroke.x1), point_y))
    point_x = float(stroke.center_x)
    return (Point(point_x, float(stroke.y0)), Point(point_x, float(stroke.y1)))


def compress_point_path(points: list[Point]) -> list[Point]:
    compressed: list[Point] = []
    for point in points:
        if not compressed:
            compressed.append(point)
            continue
        if gap_between_path_points(compressed[-1], point) <= 1.0:
            compressed[-1] = point
            continue
        compressed.append(point)
    if len(compressed) <= 2:
        return compressed
    reduced = [compressed[0]]
    for index in range(1, len(compressed) - 1):
        prev = reduced[-1]
        current = compressed[index]
        nxt = compressed[index + 1]
        if points_are_collinear(prev, current, nxt):
            continue
        reduced.append(current)
    reduced.append(compressed[-1])
    return reduced


def simplify_point_path(points: list[Point], *, max_segments: int) -> list[Point]:
    simplified = points[:]
    while len(simplified) - 1 > max_segments and len(simplified) > 2:
        shortest_index = min(
            range(1, len(simplified) - 1),
            key=lambda index: gap_between_path_points(simplified[index - 1], simplified[index]) + gap_between_path_points(simplified[index], simplified[index + 1]),
        )
        simplified.pop(shortest_index)
        simplified = compress_point_path(simplified)
    return simplified


def points_are_collinear(first: Point, second: Point, third: Point) -> bool:
    return (abs(first.x - second.x) <= 1.0 and abs(second.x - third.x) <= 1.0) or (
        abs(first.y - second.y) <= 1.0 and abs(second.y - third.y) <= 1.0
    )


def strokes_are_collinear(
    first: Stroke,
    second: Stroke,
    *,
    scale: ScaleContext,
    config: PipelineConfig,
) -> bool:
    tolerance = max(config.stroke_alignment_tolerance * 2.0, scale.estimated_stroke_width * 3.5)
    if first.orientation == "horizontal":
        return abs(first.center_y - second.center_y) <= tolerance
    return abs(first.center_x - second.center_x) <= tolerance


def stroke_interval_gap(first: Stroke, second: Stroke) -> float:
    if first.orientation == "horizontal":
        return max(0.0, max(first.x0, second.x0) - min(first.x1, second.x1))
    return max(0.0, max(first.y0, second.y0) - min(first.y1, second.y1))


def stroke_gap_bridge_ratio(
    first: Stroke,
    second: Stroke,
    bridge_mask: np.ndarray | None,
) -> float:
    if bridge_mask is None:
        return 0.0
    if first.orientation != second.orientation:
        return 0.0
    band = max(2, int(round(max(first.thickness, second.thickness) * 2.0)))
    if first.orientation == "horizontal":
        left = min(first.x1, second.x1)
        right = max(first.x0, second.x0)
        x0 = max(0, int(math.floor(min(left, right))))
        x1 = min(bridge_mask.shape[1], int(math.ceil(max(left, right))) + 1)
        y = int(round((first.center_y + second.center_y) / 2.0))
        y0 = max(0, y - band)
        y1 = min(bridge_mask.shape[0], y + band + 1)
    else:
        top = min(first.y1, second.y1)
        bottom = max(first.y0, second.y0)
        y0 = max(0, int(math.floor(min(top, bottom))))
        y1 = min(bridge_mask.shape[0], int(math.ceil(max(top, bottom))) + 1)
        x = int(round((first.center_x + second.center_x) / 2.0))
        x0 = max(0, x - band)
        x1 = min(bridge_mask.shape[1], x + band + 1)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    window = bridge_mask[y0:y1, x0:x1]
    return float(window.mean()) if window.size else 0.0


def min_stroke_endpoint_distance(first: Stroke, second: Stroke) -> float:
    first_points = stroke_endpoints(first)
    second_points = stroke_endpoints(second)
    return min(gap_between_path_points(left, right) for left in first_points for right in second_points)


def gap_between_path_points(first: Point, second: Point) -> float:
    return math.hypot(second.x - first.x, second.y - first.y)


def polyline_endpoint_widening(mask: np.ndarray, geometry: PolylineGeometry, *, band: int) -> tuple[float, float]:
    if len(geometry.points) != 2:
        return 1.0, 1.0
    start, end = geometry.points
    if abs(end.x - start.x) >= abs(end.y - start.y):
        x0 = max(0, int(math.floor(min(start.x, end.x))))
        x1 = min(mask.shape[1], int(math.ceil(max(start.x, end.x))) + 1)
        y = int(round((start.y + end.y) / 2.0))
        y0 = max(0, y - band)
        y1 = min(mask.shape[0], y + band + 1)
        if x1 <= x0 or y1 <= y0:
            return 1.0, 1.0
        profile = mask[y0:y1, x0:x1].sum(axis=0)
    else:
        y0 = max(0, int(math.floor(min(start.y, end.y))))
        y1 = min(mask.shape[0], int(math.ceil(max(start.y, end.y))) + 1)
        x = int(round((start.x + end.x) / 2.0))
        x0 = max(0, x - band)
        x1 = min(mask.shape[1], x + band + 1)
        if x1 <= x0 or y1 <= y0:
            return 1.0, 1.0
        profile = mask[y0:y1, x0:x1].sum(axis=1)
    if profile.size < 6:
        return 1.0, 1.0
    span = max(2, profile.size // 5)
    center_start = max(0, profile.size // 2 - span // 2)
    center_end = min(profile.size, center_start + span)
    core = float(np.median(profile[center_start:center_end])) if center_end > center_start else 1.0
    core = max(1.0, core)
    start_ratio = float(np.max(profile[:span])) / core
    end_ratio = float(np.max(profile[-span:])) / core
    return start_ratio, end_ratio


def orient_arrow_geometry(geometry: PolylineGeometry, *, tip_on_max_axis: bool) -> PolylineGeometry:
    start, end = geometry.points
    horizontal = abs(end.x - start.x) >= abs(end.y - start.y)
    if horizontal:
        tip = max((start, end), key=lambda point: point.x) if tip_on_max_axis else min((start, end), key=lambda point: point.x)
    else:
        tip = max((start, end), key=lambda point: point.y) if tip_on_max_axis else min((start, end), key=lambda point: point.y)
    tail = start if tip == end else end
    return PolylineGeometry(points=(tail, tip))


def strokes_interact(first: Stroke, second: Stroke, *, tolerance: float) -> bool:
    if first.orientation == second.orientation:
        if first.orientation == "horizontal":
            aligned = abs(first.center_y - second.center_y) <= tolerance
            gap = max(first.x0, second.x0) - min(first.x1, second.x1)
        else:
            aligned = abs(first.center_x - second.center_x) <= tolerance
            gap = max(first.y0, second.y0) - min(first.y1, second.y1)
        return aligned and gap <= tolerance
    horizontal = first if first.orientation == "horizontal" else second
    vertical = second if first.orientation == "horizontal" else first
    return (
        horizontal.x0 - tolerance <= vertical.center_x <= horizontal.x1 + tolerance
        and vertical.y0 - tolerance <= horizontal.center_y <= vertical.y1 + tolerance
    )


def global_stroke_geometry(stroke: Stroke) -> PolylineGeometry:
    if stroke.orientation == "horizontal":
        return PolylineGeometry(
            points=(
                Point(float(stroke.x0), float(stroke.center_y)),
                Point(float(stroke.x1), float(stroke.center_y)),
            )
        )
    return PolylineGeometry(
        points=(
            Point(float(stroke.center_x), float(stroke.y0)),
            Point(float(stroke.center_x), float(stroke.y1)),
        )
    )


def stroke_connection_count(
    start: Point,
    end: Point,
    structural_elements: list[Element],
    scale: ScaleContext,
) -> int:
    margin = max(6.0, scale.estimated_stroke_width * 5.0)
    count = 0
    for element in structural_elements:
        if element.kind not in {"rect", "rounded_rect"}:
            continue
        expanded = element.bbox.expand(margin)
        if expanded.contains_point(start):
            count += 1
        if expanded.contains_point(end):
            count += 1
    return count


def stroke_matches_box_edge(
    stroke: Stroke,
    structural_elements: list[Element],
    scale: ScaleContext,
) -> bool:
    margin = max(4.0, scale.estimated_stroke_width * 4.0)
    for element in structural_elements:
        if element.kind not in {"rect", "rounded_rect"}:
            continue
        box = element.bbox
        if stroke.orientation == "horizontal":
            if min(abs(stroke.center_y - box.y0), abs(stroke.center_y - box.y1)) > margin:
                continue
            overlap = min(stroke.x1, box.x1) - max(stroke.x0, box.x0)
            if overlap <= 0:
                continue
            if overlap / max(1.0, min(stroke.length, box.width)) >= 0.68:
                return True
            continue
        if min(abs(stroke.center_x - box.x0), abs(stroke.center_x - box.x1)) > margin:
            continue
        overlap = min(stroke.y1, box.y1) - max(stroke.y0, box.y0)
        if overlap <= 0:
            continue
        if overlap / max(1.0, min(stroke.length, box.height)) >= 0.68:
            return True
    return False


def stroke_touches_border(
    stroke: Stroke,
    image_shape: tuple[int, ...],
    *,
    margin: float,
) -> bool:
    height, width = image_shape[:2]
    if stroke.orientation == "horizontal":
        return stroke.x0 <= margin or stroke.x1 >= width - margin or stroke.center_y <= margin or stroke.center_y >= height - margin
    return stroke.center_x <= margin or stroke.center_x >= width - margin or stroke.y0 <= margin or stroke.y1 >= height - margin


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
    bbox = PolylineGeometry(points=points).bbox.expand(float(band + 2))
    x0 = max(0, int(math.floor(bbox.x0)))
    y0 = max(0, int(math.floor(bbox.y0)))
    x1 = min(mask.shape[1], int(math.ceil(bbox.x1)))
    y1 = min(mask.shape[0], int(math.ceil(bbox.y1)))
    if x1 <= x0 or y1 <= y0:
        return 0.0
    local_mask = mask[y0:y1, x0:x1]
    pixels = np.argwhere(local_mask)
    if len(pixels) == 0:
        return 0.0
    covered = 0
    shifted_points = tuple(Point(point.x - x0, point.y - y0) for point in points)
    for y, x in pixels:
        if any(pixel_near_axis_segment(x, y, start, end, band) for start, end in zip(shifted_points[:-1], shifted_points[1:], strict=True)):
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
    x_target: float | None = None,
    x_range: tuple[float, float] | None = None,
    y0: float,
    y1: float,
    config: PipelineConfig,
    scale: ScaleContext | None = None,
) -> Stroke | None:
    candidates = []
    tolerance = float(config.stroke_merge_gap)
    if scale is not None:
        tolerance = max(tolerance, scale.estimated_stroke_width * 8.0)
    for stroke in vertical:
        if x_range is not None:
            range_x0, range_x1 = x_range
            if stroke.center_x < range_x0 - tolerance or stroke.center_x > range_x1 + tolerance:
                continue
            distance = 0.0
            if stroke.center_x < range_x0:
                distance = range_x0 - stroke.center_x
            elif stroke.center_x > range_x1:
                distance = stroke.center_x - range_x1
        else:
            if x_target is None or abs(stroke.center_x - x_target) > tolerance:
                continue
            distance = abs(stroke.center_x - x_target)
        coverage = min(stroke.y1, y1) - max(stroke.y0, y0)
        if coverage < (y1 - y0) * 0.55:
            continue
        candidates.append((coverage, -distance, stroke))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return candidates[0][2]


def best_horizontal_for_box(
    horizontal: list[Stroke],
    *,
    y_target: float | None = None,
    y_range: tuple[float, float] | None = None,
    x0: float,
    x1: float,
    config: PipelineConfig,
    scale: ScaleContext | None = None,
) -> Stroke | None:
    candidates = []
    tolerance = float(config.stroke_merge_gap)
    if scale is not None:
        tolerance = max(tolerance, scale.estimated_stroke_width * 8.0)
    for stroke in horizontal:
        if y_range is not None:
            range_y0, range_y1 = y_range
            if stroke.center_y < range_y0 - tolerance or stroke.center_y > range_y1 + tolerance:
                continue
            distance = 0.0
            if stroke.center_y < range_y0:
                distance = range_y0 - stroke.center_y
            elif stroke.center_y > range_y1:
                distance = stroke.center_y - range_y1
        else:
            if y_target is None or abs(stroke.center_y - y_target) > tolerance:
                continue
            distance = abs(stroke.center_y - y_target)
        coverage = min(stroke.x1, x1) - max(stroke.x0, x0)
        if coverage < (x1 - x0) * 0.55:
            continue
        candidates.append((coverage, -distance, stroke))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return candidates[0][2]


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
