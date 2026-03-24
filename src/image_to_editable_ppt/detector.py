from __future__ import annotations

from dataclasses import dataclass, replace
import math

import numpy as np
from PIL import Image

try:
    import cv2
except ImportError:  # pragma: no cover - guarded by dependency/tests
    cv2 = None

from .components import remove_small_components
from .config import PipelineConfig
from .filtering import FilteredComponent, RejectedRegion, filter_residual_components
from .fitter import (
    boxes_equivalent,
    extract_strokes,
    fit_component_box_from_outer_contour,
    fit_boxes,
    fit_branchy_component_lines,
    fit_fill_region_boxes,
    fit_global_stroke_lines,
    fit_hough_segment_elements,
    fit_linear_component,
    fit_orthogonal_connector,
)
from .ir import BBox, Element, Point, PolylineGeometry
from .preprocess import ProcessedImage
from .style import estimate_fill_color, median_color, sample_bbox_border_colors
from .vlm_parser import VLMNode


@dataclass(slots=True)
class DetectionResult:
    elements: list[Element]
    text_regions: list[BBox]
    rejected_regions: list[RejectedRegion]
    bridge_mask: np.ndarray


@dataclass(slots=True, frozen=True)
class RefinedNode:
    id: str
    type: str
    text: str
    approx_bbox: BBox
    exact_bbox: BBox
    confidence: float
    stroke_color: tuple[int, int, int]
    stroke_width: float
    fill_enabled: bool
    fill_color: tuple[int, int, int] | None
    corner_radius: float


def detect_elements(processed: ProcessedImage, config: PipelineConfig) -> list[Element]:
    return detect_elements_with_metadata(processed, config).elements


def detect_elements_with_metadata(processed: ProcessedImage, config: PipelineConfig) -> DetectionResult:
    box_min_length = max(8, processed.scale.min_stroke_length // 2)
    horizontal = extract_strokes(
        processed.boundary_mask_raw,
        "horizontal",
        config,
        array=processed.array,
        gray=processed.gray,
        min_length=box_min_length,
    )
    vertical = extract_strokes(
        processed.boundary_mask_raw,
        "vertical",
        config,
        array=processed.array,
        gray=processed.gray,
        min_length=box_min_length,
    )
    graph_horizontal = extract_strokes(
        processed.boundary_mask,
        "horizontal",
        config,
        array=processed.array,
        gray=processed.gray,
        min_length=box_min_length,
    )
    graph_vertical = extract_strokes(
        processed.boundary_mask,
        "vertical",
        config,
        array=processed.array,
        gray=processed.gray,
        min_length=box_min_length,
    )
    boxes = fit_boxes(
        horizontal,
        vertical,
        boundary_mask=processed.boundary_mask_raw,
        array=processed.array,
        detail_mask=processed.detail_mask,
        background_color=processed.background_color,
        config=config,
        scale=processed.scale,
    )
    fill_boxes = fit_fill_region_boxes(
        mask=processed.fill_region_mask,
        boundary_mask=processed.boundary_mask_raw,
        array=processed.array,
        smoothed_array=processed.smoothed_array,
        detail_mask=processed.detail_mask,
        background_color=processed.background_color,
        config=config,
        scale=processed.scale,
        existing_elements=boxes,
        start_index=len(boxes) + 1,
    )
    boxes.extend(candidate for candidate in fill_boxes if not box_element_is_duplicate(candidate, boxes))
    text_filter = filter_residual_components(
        processed.detail_mask_raw,
        processed=processed,
        config=config,
        structural_elements=boxes,
    )
    residual = processed.detail_mask.copy()
    clear_margin = max(4.0, processed.scale.estimated_stroke_width * 3.0)
    for box in boxes:
        bbox = box.bbox.expand(clear_margin)
        x0 = max(0, int(bbox.x0))
        y0 = max(0, int(bbox.y0))
        x1 = min(residual.shape[1], int(np.ceil(bbox.x1)))
        y1 = min(residual.shape[0], int(np.ceil(bbox.y1)))
        residual[y0:y1, x0:x1] = False
    for region in text_filter.text_regions:
        x0 = max(0, int(region.x0))
        y0 = max(0, int(region.y0))
        x1 = min(residual.shape[1], int(np.ceil(region.x1)))
        y1 = min(residual.shape[0], int(np.ceil(region.y1)))
        residual[y0:y1, x0:x1] = False
    residual = remove_small_components(residual, max(4, processed.scale.min_component_area // 2))
    filtered = filter_residual_components(
        residual,
        processed=processed,
        config=config,
        structural_elements=boxes,
    )
    bridge_regions = text_filter.text_regions + [
        region.bbox
        for region in text_filter.rejected_regions
        if region.reason == "rejected_as_too_small"
        and region.area <= processed.scale.min_component_area * 2
        and max(region.bbox.width, region.bbox.height) <= processed.scale.min_linear_length
    ]
    bridge_mask = np.zeros_like(processed.detail_mask, dtype=bool)
    mark_regions(bridge_mask, bridge_regions, value=True)
    hough_mask = processed.boundary_mask.copy()
    mark_regions(hough_mask, [box.bbox.expand(clear_margin) for box in boxes], value=False)
    mark_regions(hough_mask, bridge_regions, value=False)
    mark_regions(
        hough_mask,
        [
            region.bbox
            for region in filtered.rejected_regions
            if region.label in {"text_like", "icon_like"}
        ],
        value=False,
    )
    hough_linear = fit_hough_segment_elements(
        mask=hough_mask,
        array=processed.array,
        gray=processed.gray,
        bridge_mask=bridge_mask,
        config=config,
        scale=processed.scale,
        structural_elements=boxes,
        existing_elements=[],
        start_index=len(boxes) + 1,
    )
    linear = detect_linear_elements(
        components=filtered.diagram_components + filtered.weak_components,
        processed=processed,
        config=config,
        start_index=len(boxes) + len(hough_linear) + 1,
        structural_elements=boxes,
        existing_elements=hough_linear,
    )
    if not hough_linear and not linear and boxes and max(processed.size) >= 1800:
        linear = fit_global_stroke_lines(
            horizontal=graph_horizontal,
            vertical=graph_vertical,
            array=processed.array,
            gray=processed.gray,
            config=config,
            scale=processed.scale,
            structural_elements=boxes,
            start_index=len(boxes) + 1,
        )
    elements = finalize_detected_elements(boxes + hough_linear + linear, processed, config)
    return DetectionResult(
        elements=elements,
        text_regions=text_filter.text_regions,
        rejected_regions=filtered.rejected_regions
        + [region for region in text_filter.rejected_regions if region.label == "text_like"],
        bridge_mask=bridge_mask,
    )


def refine_node_geometry(
    image: Image.Image,
    proposal: VLMNode,
    config: PipelineConfig,
    *,
    text_anchor: BBox | None = None,
) -> RefinedNode:
    array = np.asarray(image.convert("RGB"), dtype=np.uint8)
    approx_bbox = clamp_bbox(proposal.approx_bbox, width=array.shape[1], height=array.shape[0])
    exact_bbox = (
        grow_container_from_text_anchor(array, text_anchor, approx_bbox, config)
        if text_anchor is not None
        else snap_bbox_to_local_contour(array, approx_bbox, config)
    )
    stroke_width = estimate_local_stroke_width(exact_bbox)
    stroke_color = sample_bbox_border_colors(array, exact_bbox, stroke_width)
    background_color = estimate_surrounding_background(array, exact_bbox)
    fill_enabled, fill_color = estimate_fill_color(
        array=array,
        bbox=exact_bbox,
        stroke_width=stroke_width,
        background_color=background_color,
        delta_threshold=14.0,
        homogeneity_threshold=24.0,
        detail_mask=None,
    )
    if proposal.type == "text_only":
        fill_enabled = False
        fill_color = None
    corner_radius = estimate_corner_radius(array, exact_bbox, proposal.type)
    return RefinedNode(
        id=proposal.id,
        type=proposal.type,
        text=proposal.text,
        approx_bbox=approx_bbox,
        exact_bbox=exact_bbox,
        confidence=0.90 if exact_bbox != approx_bbox else 0.82,
        stroke_color=stroke_color,
        stroke_width=stroke_width,
        fill_enabled=fill_enabled,
        fill_color=fill_color,
        corner_radius=corner_radius,
    )


def clamp_bbox(bbox: BBox, *, width: int, height: int) -> BBox:
    x0 = min(max(0.0, bbox.x0), float(width - 1))
    y0 = min(max(0.0, bbox.y0), float(height - 1))
    x1 = min(max(x0 + 1.0, bbox.x1), float(width))
    y1 = min(max(y0 + 1.0, bbox.y1), float(height))
    return BBox(x0, y0, x1, y1)


def snap_bbox_to_local_contour(
    array: np.ndarray,
    approx_bbox: BBox,
    config: PipelineConfig,
) -> BBox:
    if cv2 is None:
        return approx_bbox
    padding = max(config.local_refine_padding, max(approx_bbox.width, approx_bbox.height) * 0.08)
    crop_bbox = clamp_bbox(
        approx_bbox.expand(padding),
        width=array.shape[1],
        height=array.shape[0],
    )
    x0 = int(math.floor(crop_bbox.x0))
    y0 = int(math.floor(crop_bbox.y0))
    x1 = int(math.ceil(crop_bbox.x1))
    y1 = int(math.ceil(crop_bbox.y1))
    crop = array[y0:y1, x0:x1]
    if crop.size == 0:
        return approx_bbox
    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    sobel_x = cv2.Sobel(blurred, cv2.CV_32F, 1, 0, ksize=3)
    sobel_y = cv2.Sobel(blurred, cv2.CV_32F, 0, 1, ksize=3)
    gradient = cv2.magnitude(sobel_x, sobel_y)
    threshold = max(
        float(np.percentile(gradient, config.local_refine_gradient_percentile)),
        float(np.mean(gradient) + config.local_refine_threshold_bias),
    )
    canny = cv2.Canny(blurred, 48, 144)
    binary = np.zeros_like(gray, dtype=np.uint8)
    binary[gradient >= threshold] = 255
    binary = cv2.bitwise_or(binary, canny)
    kernel = np.ones((5, 5), dtype=np.uint8)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return approx_bbox
    target_center = approx_bbox.center
    best_bbox = approx_bbox
    best_score = -1.0
    approx_area = max(approx_bbox.area, 1.0)
    for contour in contours:
        rx, ry, rw, rh = cv2.boundingRect(contour)
        candidate = BBox(x0 + rx, y0 + ry, x0 + rx + rw, y0 + ry + rh)
        if candidate.width < 8 or candidate.height < 8:
            continue
        score = candidate.iou(approx_bbox) * 4.0
        if candidate.contains_point(target_center):
            score += 1.5
        area_ratio = min(candidate.area, approx_area) / max(candidate.area, approx_area)
        score += area_ratio
        if score > best_score:
            best_score = score
            best_bbox = candidate
    if best_score < config.local_refine_min_iou * 4.0:
        return approx_bbox
    return clamp_bbox(best_bbox, width=array.shape[1], height=array.shape[0])


def grow_container_from_text_anchor(
    array: np.ndarray,
    text_anchor: BBox,
    hint_bbox: BBox,
    config: PipelineConfig,
) -> BBox:
    seed_padding = max(
        config.local_refine_padding * 0.6,
        text_anchor.height * 1.2,
        text_anchor.width * 0.22,
    )
    seed_bbox = clamp_bbox(
        text_anchor.expand(seed_padding),
        width=array.shape[1],
        height=array.shape[0],
    )
    if cv2 is None:
        return snap_bbox_to_local_contour(array, merge_bboxes(seed_bbox, hint_bbox), config)
    search_bbox = clamp_bbox(
        merge_bboxes(seed_bbox.expand(seed_padding), hint_bbox.expand(config.local_refine_padding)),
        width=array.shape[1],
        height=array.shape[0],
    )
    x0 = int(math.floor(search_bbox.x0))
    y0 = int(math.floor(search_bbox.y0))
    x1 = int(math.ceil(search_bbox.x1))
    y1 = int(math.ceil(search_bbox.y1))
    crop = array[y0:y1, x0:x1]
    if crop.size == 0:
        return hint_bbox
    smoothed = cv2.pyrMeanShiftFiltering(crop, sp=12, sr=18)
    gray = cv2.cvtColor(smoothed, cv2.COLOR_RGB2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    sobel_x = cv2.Sobel(blurred, cv2.CV_32F, 1, 0, ksize=3)
    sobel_y = cv2.Sobel(blurred, cv2.CV_32F, 0, 1, ksize=3)
    gradient = cv2.magnitude(sobel_x, sobel_y)
    threshold = max(
        float(np.percentile(gradient, max(70.0, config.local_refine_gradient_percentile - 8.0))),
        float(np.mean(gradient) + config.local_refine_threshold_bias * 0.7),
    )
    canny = cv2.Canny(blurred, 42, 132)
    binary = np.zeros_like(gray, dtype=np.uint8)
    binary[gradient >= threshold] = 255
    binary = cv2.bitwise_or(binary, canny)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, np.ones((5, 5), dtype=np.uint8), iterations=2)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return snap_bbox_to_local_contour(array, merge_bboxes(seed_bbox, hint_bbox), config)
    best_bbox = merge_bboxes(seed_bbox, hint_bbox)
    best_score = -1.0
    seed_center = text_anchor.center
    for contour in contours:
        rx, ry, rw, rh = cv2.boundingRect(contour)
        candidate = BBox(x0 + rx, y0 + ry, x0 + rx + rw, y0 + ry + rh)
        if candidate.width < max(18.0, text_anchor.width * 1.35):
            continue
        if candidate.height < max(18.0, text_anchor.height * 1.55):
            continue
        score = 0.0
        if candidate.contains_point(seed_center):
            score += 2.5
        if bbox_contains(candidate, text_anchor.expand(3.0)):
            score += 2.0
        score += candidate.iou(hint_bbox) * 2.0
        expansion_ratio = min(candidate.area, max(hint_bbox.area, seed_bbox.area)) / max(candidate.area, 1.0)
        score += expansion_ratio
        if score > best_score:
            best_score = score
            best_bbox = candidate
    if best_score < 2.6:
        return snap_bbox_to_local_contour(array, merge_bboxes(seed_bbox, hint_bbox), config)
    return clamp_bbox(best_bbox, width=array.shape[1], height=array.shape[0])


def estimate_local_stroke_width(bbox: BBox) -> float:
    return max(2.0, min(bbox.width, bbox.height) * 0.03)


def estimate_surrounding_background(array: np.ndarray, bbox: BBox) -> tuple[int, int, int]:
    outer = clamp_bbox(bbox.expand(max(6.0, min(bbox.width, bbox.height) * 0.08)), width=array.shape[1], height=array.shape[0])
    x0 = int(math.floor(outer.x0))
    y0 = int(math.floor(outer.y0))
    x1 = int(math.ceil(outer.x1))
    y1 = int(math.ceil(outer.y1))
    ix0 = int(math.floor(bbox.x0))
    iy0 = int(math.floor(bbox.y0))
    ix1 = int(math.ceil(bbox.x1))
    iy1 = int(math.ceil(bbox.y1))
    ring = array[y0:y1, x0:x1].copy()
    ring[iy0 - y0 : iy1 - y0, ix0 - x0 : ix1 - x0] = 0
    mask = np.ones(ring.shape[:2], dtype=bool)
    mask[iy0 - y0 : iy1 - y0, ix0 - x0 : ix1 - x0] = False
    colors = ring[mask]
    if colors.size == 0:
        colors = array.reshape(-1, 3)
    return median_color(colors)


def estimate_corner_radius(array: np.ndarray, bbox: BBox, proposal_type: str) -> float:
    if proposal_type == "cylinder":
        return min(bbox.width, bbox.height) * 0.18
    if proposal_type == "document":
        return 0.0
    stroke_width = estimate_local_stroke_width(bbox)
    sample = max(4, int(round(min(bbox.width, bbox.height) * 0.12)))
    x0 = int(math.floor(bbox.x0))
    y0 = int(math.floor(bbox.y0))
    x1 = int(math.ceil(bbox.x1))
    y1 = int(math.ceil(bbox.y1))
    if x1 - x0 < sample * 2 or y1 - y0 < sample * 2:
        return 0.0
    gray = np.asarray(array[y0:y1, x0:x1].mean(axis=2), dtype=np.float32)
    edge_threshold = np.percentile(gray, 30)
    corners = [
        gray[:sample, :sample],
        gray[:sample, -sample:],
        gray[-sample:, :sample],
        gray[-sample:, -sample:],
    ]
    dark_ratio = [float((corner <= edge_threshold).mean()) for corner in corners]
    if max(dark_ratio) < 0.18:
        return max(stroke_width * 2.0, min(bbox.width, bbox.height) * 0.08)
    return 0.0


def merge_bboxes(first: BBox, second: BBox) -> BBox:
    return BBox(
        min(first.x0, second.x0),
        min(first.y0, second.y0),
        max(first.x1, second.x1),
        max(first.y1, second.y1),
    )


def bbox_contains(container: BBox, inner: BBox) -> bool:
    return (
        container.x0 <= inner.x0
        and container.y0 <= inner.y0
        and container.x1 >= inner.x1
        and container.y1 >= inner.y1
    )


def verify_edge_exists(
    image: Image.Image,
    source_bbox: BBox,
    target_bbox: BBox,
    config: PipelineConfig,
    *,
    expect_dashed: bool = False,
) -> bool:
    array = np.asarray(image.convert("RGB"), dtype=np.uint8)
    gray = np.asarray(image.convert("L"), dtype=np.float32)
    background = estimate_image_background(array)
    if cv2 is not None:
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        sobel_x = cv2.Sobel(blurred, cv2.CV_32F, 1, 0, ksize=3)
        sobel_y = cv2.Sobel(blurred, cv2.CV_32F, 0, 1, ksize=3)
        gradient = cv2.magnitude(sobel_x, sobel_y)
    else:
        gradient = np.zeros_like(gray)
    start, end = shortest_anchor_segment(source_bbox, target_bbox)
    if math.hypot(end.x - start.x, end.y - start.y) < 12.0:
        return False
    steps = max(24, int(math.hypot(end.x - start.x, end.y - start.y) / 10.0))
    evidence = 0
    strongest = 0.0
    color_threshold = config.edge_verification_color_distance
    gradient_threshold = max(14.0, float(np.percentile(gradient, 72)))
    for index in range(steps):
        ratio = (index + 0.5) / steps
        point = Point(
            start.x + (end.x - start.x) * ratio,
            start.y + (end.y - start.y) * ratio,
        )
        patch = sample_patch(array, point, radius=2)
        patch_gradient = sample_patch(gradient, point, radius=2)
        if patch.size == 0 or patch_gradient.size == 0:
            continue
        mean_gradient = float(np.mean(patch_gradient))
        colors = patch.reshape(-1, 3)
        contrast = float(np.percentile(np.linalg.norm(colors.astype(np.float32) - background[None, :], axis=1), 75))
        strongest = max(strongest, mean_gradient, contrast)
        if mean_gradient >= gradient_threshold or contrast >= color_threshold:
            evidence += 1
    ratio = evidence / max(1, steps)
    required = config.edge_verification_dashed_ratio if expect_dashed else config.edge_verification_min_ratio
    return ratio >= required and strongest >= min(color_threshold, gradient_threshold)


def shortest_anchor_segment(source_bbox: BBox, target_bbox: BBox) -> tuple[Point, Point]:
    source_center = source_bbox.center
    target_center = target_bbox.center
    dx = target_center.x - source_center.x
    dy = target_center.y - source_center.y
    if abs(dx) >= abs(dy):
        source = Point(source_bbox.x1 if dx >= 0 else source_bbox.x0, source_center.y)
        target = Point(target_bbox.x0 if dx >= 0 else target_bbox.x1, target_center.y)
        return source, target
    source = Point(source_center.x, source_bbox.y1 if dy >= 0 else source_bbox.y0)
    target = Point(target_center.x, target_bbox.y0 if dy >= 0 else target_bbox.y1)
    return source, target


def estimate_image_background(array: np.ndarray) -> np.ndarray:
    border = np.concatenate(
        [
            array[0, :, :],
            array[-1, :, :],
            array[:, 0, :],
            array[:, -1, :],
        ],
        axis=0,
    )
    return np.median(border.astype(np.float32), axis=0)


def sample_patch(array: np.ndarray, point: Point, *, radius: int) -> np.ndarray:
    x = int(round(point.x))
    y = int(round(point.y))
    y0 = max(0, y - radius)
    y1 = min(array.shape[0], y + radius + 1)
    x0 = max(0, x - radius)
    x1 = min(array.shape[1], x + radius + 1)
    return array[y0:y1, x0:x1]


def detect_linear_elements(
    *,
    components: list[FilteredComponent],
    processed: ProcessedImage,
    config: PipelineConfig,
    start_index: int,
    structural_elements: list[Element],
    existing_elements: list[Element],
) -> list[Element]:
    elements: list[Element] = []
    next_index = start_index
    ordered = sorted(
        components,
        key=lambda filtered: (
            0 if filtered.strength == "strong" else 1,
            -filtered.features.long_axis,
            -filtered.features.area,
        ),
    )
    for filtered in ordered:
        component = filtered.component
        box_candidate = None
        if should_try_outer_box_fallback(filtered, processed):
            box_candidate = fit_component_box_from_outer_contour(
                component.pixels,
                bbox=component.bbox,
                boundary_mask=processed.boundary_mask_raw,
                array=processed.array,
                detail_mask=processed.detail_mask,
                background_color=processed.background_color,
                config=config,
                scale=processed.scale,
                element_id=f"box-{next_index}",
            )
        if box_candidate is not None:
            if box_element_is_duplicate(box_candidate, structural_elements + existing_elements + elements):
                box_candidate = None
            else:
                elements.append(box_candidate)
                next_index += 1
                continue
        element = fit_orthogonal_connector(
            component.pixels,
            processed.array,
            component.bbox,
            config,
            element_id=f"linear-{next_index}",
            scale=processed.scale,
            features=filtered.features,
            proposal_strength=filtered.strength,
        )
        if element is None:
            element = fit_linear_component(
                component.pixels,
                processed.array,
                component.bbox,
                config,
                element_id=f"linear-{next_index}",
                scale=processed.scale,
                features=filtered.features,
                proposal_strength=filtered.strength,
            )
        if element is None:
            fallback = []
            if filtered.features.aspect >= 3.0 or filtered.features.near_structure_count > 0:
                fallback = fit_branchy_component_lines(
                    component.pixels,
                    processed.array,
                    component.bbox,
                    config,
                    element_prefix=f"linear-{next_index}",
                    scale=processed.scale,
                    structural_elements=structural_elements,
                )
            if fallback:
                for candidate in fallback:
                    if filtered.strength == "weak":
                        candidate = weaken_linear_candidate(candidate)
                        candidate = strengthen_box_anchored_linear_candidate(
                            candidate,
                            structural_elements,
                            processed.scale.min_box_size,
                            config,
                        )
                        if not weak_linear_candidate_is_plausible(
                            candidate,
                            structural_elements,
                            processed.size,
                            processed.scale.min_box_size,
                            processed.scale.min_linear_length,
                        ):
                            continue
                    if linear_element_is_duplicate(candidate, existing_elements + elements):
                        continue
                    elements.append(candidate)
                    next_index += 1
            continue
        if filtered.strength == "weak":
            element = weaken_linear_candidate(element)
            element = strengthen_box_anchored_linear_candidate(
                element,
                structural_elements,
                processed.scale.min_box_size,
                config,
            )
            if not weak_linear_candidate_is_plausible(
                element,
                structural_elements,
                processed.size,
                processed.scale.min_box_size,
                processed.scale.min_linear_length,
            ):
                continue
        if linear_element_is_duplicate(element, existing_elements + elements):
            continue
        elements.append(element)
        next_index += 1
    return elements


def linear_element_is_duplicate(element: Element, existing: list[Element]) -> bool:
    return any(
        element.kind == prior.kind
        and element.bbox.iou(prior.bbox) >= 0.74
        for prior in existing
    )


def box_element_is_duplicate(element: Element, existing: list[Element]) -> bool:
    if element.kind not in {"rect", "rounded_rect"}:
        return False
    return any(
        candidate.kind in {"rect", "rounded_rect"}
        and (
            boxes_equivalent(element, candidate)
            or contained_overlap_is_duplicate(element.bbox, candidate.bbox)
        )
        for candidate in existing
    )


def contained_overlap_is_duplicate(first: BBox, second: BBox) -> bool:
    overlap = overlap_on_smaller_area(first, second)
    if overlap < 0.82:
        return False
    width_ratio = min(first.width, second.width) / max(1.0, max(first.width, second.width))
    height_ratio = min(first.height, second.height) / max(1.0, max(first.height, second.height))
    center_dx = abs(first.center.x - second.center.x)
    center_dy = abs(first.center.y - second.center.y)
    center_margin = max(min(first.width, second.width), min(first.height, second.height)) * 0.18
    return (
        width_ratio >= 0.74
        and height_ratio >= 0.74
        and center_dx <= center_margin
        and center_dy <= center_margin
    )


def should_try_outer_box_fallback(filtered: FilteredComponent, processed: ProcessedImage) -> bool:
    feature = filtered.features
    return (
        filtered.strength == "weak"
        and feature.width >= processed.scale.min_box_size * 1.2
        and feature.height >= processed.scale.min_box_size * 0.9
        and feature.aspect <= 10.0
        and feature.long_axis >= processed.scale.min_box_size * 1.8
    )


def weaken_linear_candidate(element: Element) -> Element:
    return replace(element, confidence=max(0.0, element.confidence - 0.12))


def strengthen_box_anchored_linear_candidate(
    element: Element,
    structural_elements: list[Element],
    min_box_size: int,
    config: PipelineConfig,
) -> Element:
    if element.kind not in {"line", "orthogonal_connector", "arrow"}:
        return element
    points = getattr(element.geometry, "points", ())
    if len(points) < 2:
        return element
    hits = endpoint_box_hits(points[0], points[-1], structural_elements, margin=max(8.0, min_box_size * 0.45))
    if hits < 2:
        return element
    return replace(element, confidence=max(element.confidence, config.inclusion_confidence))


def weak_linear_candidate_is_plausible(
    element: Element,
    structural_elements: list[Element],
    image_size: tuple[int, int],
    min_box_size: int,
    min_linear_length: int,
) -> bool:
    if element.kind not in {"line", "orthogonal_connector", "arrow"}:
        return True
    points = getattr(element.geometry, "points", ())
    if len(points) < 2:
        return False
    endpoint_hits = endpoint_box_hits(points[0], points[-1], structural_elements, margin=max(8.0, min_box_size * 0.45))
    if endpoint_hits >= 2:
        return True
    if touches_image_border(element, image_size, margin=max(16.0, min_box_size * 1.2)):
        return False
    return endpoint_hits >= 1 and max(element.bbox.width, element.bbox.height) >= min_linear_length * 2.6


def endpoint_box_hits(start, end, structural_elements: list[Element], margin: float) -> int:
    hits = 0
    for element in structural_elements:
        if element.kind not in {"rect", "rounded_rect"}:
            continue
        expanded = element.bbox.expand(margin)
        if expanded.contains_point(start):
            hits += 1
        if expanded.contains_point(end):
            hits += 1
    return hits


def element_endpoint_hits_boxes(element: Element, boxes: list[Element], margin: float) -> int:
    points = getattr(element.geometry, "points", ())
    if len(points) < 2:
        return 0
    return endpoint_box_hits(points[0], points[-1], boxes, margin)


def touches_image_border(element: Element, image_size: tuple[int, int], margin: float) -> bool:
    width, height = image_size
    bbox = element.bbox
    return (
        bbox.x0 <= margin
        or bbox.y0 <= margin
        or bbox.x1 >= width - margin
        or bbox.y1 >= height - margin
    )


def mark_regions(mask: np.ndarray, regions: list[BBox], *, value: bool) -> None:
    for region in regions:
        x0 = max(0, int(region.x0))
        y0 = max(0, int(region.y0))
        x1 = min(mask.shape[1], int(np.ceil(region.x1)))
        y1 = min(mask.shape[0], int(np.ceil(region.y1)))
        if x1 <= x0 or y1 <= y0:
            continue
        mask[y0:y1, x0:x1] = value


def finalize_detected_elements(elements: list[Element], processed: ProcessedImage, config: PipelineConfig) -> list[Element]:
    boxes: list[Element] = []
    others: list[Element] = []
    line_candidate_count = sum(1 for element in elements if element.kind == "line")
    for element in sorted(elements, key=lambda candidate: candidate.confidence, reverse=True):
        if element.kind in {"rect", "rounded_rect"}:
            if box_element_is_duplicate(element, boxes):
                continue
            boxes.append(element)
            continue
        if element.kind == "arrow":
            element = orient_arrow_element(element, processed)
        if element.kind == "orthogonal_connector":
            element = normalize_connector_axes(element, tolerance=max(4.0, processed.scale.estimated_stroke_width * 2.0))
        if element.kind == "orthogonal_connector" and not polyline_is_axis_aligned(element, tolerance=max(4.0, processed.scale.estimated_stroke_width * 2.0)):
            continue
        if element.kind == "orthogonal_connector" and connector_loops_back_into_same_box(element, boxes, processed):
            continue
        if element.kind == "orthogonal_connector" and weak_connector_is_unanchored(element, boxes, processed):
            continue
        if element.kind == "line" and not boxes and line_candidate_count == 1 and isolated_line_too_short(element, processed):
            continue
        if element.kind == "line" and short_unanchored_line(element, boxes, processed):
            continue
        if element.kind == "line" and line_endpoint_hits_boxes(element, boxes, processed) == 0 and ambiguous_wedge_line(element, processed, config):
            continue
        if element.kind == "line" and line_matches_any_box_edge(element, boxes, processed.scale):
            continue
        if element.kind in {"line", "orthogonal_connector", "arrow"}:
            endpoint_hits = element_endpoint_hits_boxes(
                element,
                boxes,
                margin=max(8.0, processed.scale.min_box_size * 0.45),
            )
            if endpoint_hits >= 2 and element.confidence < config.inclusion_confidence:
                element = replace(element, confidence=config.inclusion_confidence)
        if linear_element_is_duplicate(element, others) or parallel_line_is_duplicate(element, others, processed.scale):
            continue
        others.append(element)
    return boxes + others


def line_matches_any_box_edge(element: Element, boxes: list[Element], scale) -> bool:
    if element.kind not in {"line", "arrow"}:
        return False
    points = getattr(element.geometry, "points", ())
    if len(points) != 2:
        return False
    start, end = points
    horizontal = abs(start.y - end.y) <= abs(start.x - end.x)
    margin = max(8.0, scale.estimated_stroke_width * 6.0, scale.min_box_size * 0.95)
    for box in boxes:
        if box.kind not in {"rect", "rounded_rect"}:
            continue
        if horizontal:
            if min(abs(start.y - box.bbox.y0), abs(start.y - box.bbox.y1)) > margin:
                continue
            overlap = min(max(start.x, end.x), box.bbox.x1) - max(min(start.x, end.x), box.bbox.x0)
            if overlap > 0 and overlap / max(1.0, min(abs(end.x - start.x), box.bbox.width)) >= 0.68:
                return True
            continue
        if min(abs(start.x - box.bbox.x0), abs(start.x - box.bbox.x1)) > margin:
            continue
        overlap = min(max(start.y, end.y), box.bbox.y1) - max(min(start.y, end.y), box.bbox.y0)
        if overlap > 0 and overlap / max(1.0, min(abs(end.y - start.y), box.bbox.height)) >= 0.68:
            return True
    return False


def normalize_connector_axes(element: Element, *, tolerance: float) -> Element:
    points = list(getattr(element.geometry, "points", ()))
    if len(points) < 2:
        return element
    normalized = [points[0]]
    for point in points[1:]:
        previous = normalized[-1]
        dx = point.x - previous.x
        dy = point.y - previous.y
        if abs(dx) <= tolerance:
            normalized.append(Point(previous.x, point.y))
            continue
        if abs(dy) <= tolerance:
            normalized.append(Point(point.x, previous.y))
            continue
        if abs(dx) >= abs(dy):
            normalized.append(Point(point.x, previous.y))
            continue
        normalized.append(Point(previous.x, point.y))
    compressed = compress_axis_points(normalized)
    if len(compressed) < 2:
        return element
    kind = "line" if len(compressed) == 2 else element.kind
    geometry = PolylineGeometry(points=tuple(compressed))
    return replace(element, kind=kind, geometry=geometry, source_region=geometry.bbox)


def compress_axis_points(points: list[Point]) -> list[Point]:
    compressed: list[Point] = []
    for point in points:
        if not compressed:
            compressed.append(point)
            continue
        if compressed[-1] == point:
            continue
        compressed.append(point)
    if len(compressed) <= 2:
        return compressed
    reduced = [compressed[0]]
    for index in range(1, len(compressed) - 1):
        prev = reduced[-1]
        current = compressed[index]
        nxt = compressed[index + 1]
        if (abs(prev.x - current.x) <= 1.0 and abs(current.x - nxt.x) <= 1.0) or (
            abs(prev.y - current.y) <= 1.0 and abs(current.y - nxt.y) <= 1.0
        ):
            continue
        reduced.append(current)
    reduced.append(compressed[-1])
    return reduced


def orient_arrow_element(element: Element, processed: ProcessedImage) -> Element:
    points = getattr(element.geometry, "points", ())
    if len(points) != 2:
        return element
    start_ratio, end_ratio = line_endpoint_widening(element, processed.foreground_mask, processed.scale)
    tip_on_max_axis = end_ratio >= start_ratio
    start, end = points
    horizontal = abs(end.x - start.x) >= abs(end.y - start.y)
    if horizontal:
        tip = max((start, end), key=lambda point: point.x) if tip_on_max_axis else min((start, end), key=lambda point: point.x)
    else:
        tip = max((start, end), key=lambda point: point.y) if tip_on_max_axis else min((start, end), key=lambda point: point.y)
    tail = start if tip == end else end
    geometry = PolylineGeometry(points=(tail, tip))
    return replace(element, geometry=geometry, source_region=geometry.bbox)


def polyline_is_axis_aligned(element: Element, *, tolerance: float) -> bool:
    points = getattr(element.geometry, "points", ())
    if len(points) < 2:
        return False
    return all(
        abs(end.x - start.x) <= tolerance or abs(end.y - start.y) <= tolerance
        for start, end in zip(points[:-1], points[1:], strict=True)
    )


def weak_connector_is_unanchored(element: Element, boxes: list[Element], processed: ProcessedImage) -> bool:
    points = getattr(element.geometry, "points", ())
    if len(points) < 2:
        return True
    hits = endpoint_box_hits(points[0], points[-1], boxes, margin=max(8.0, processed.scale.min_box_size * 0.45))
    aspect = max(element.bbox.width, element.bbox.height) / max(1.0, min(element.bbox.width, element.bbox.height))
    return hits == 0 and (
        max(element.bbox.width, element.bbox.height) < processed.scale.min_linear_length * 2.4
        or (max(element.bbox.width, element.bbox.height) < 90.0 and aspect < 5.0)
    )


def connector_loops_back_into_same_box(element: Element, boxes: list[Element], processed: ProcessedImage) -> bool:
    points = getattr(element.geometry, "points", ())
    if len(points) < 2:
        return False
    margin = max(8.0, processed.scale.min_box_size * 0.45)
    start_boxes = [
        box
        for box in boxes
        if box.kind in {"rect", "rounded_rect"} and box.bbox.expand(margin).contains_point(points[0])
    ]
    end_boxes = [
        box
        for box in boxes
        if box.kind in {"rect", "rounded_rect"} and box.bbox.expand(margin).contains_point(points[-1])
    ]
    if not start_boxes or not end_boxes:
        return False
    return any(start is end for start in start_boxes for end in end_boxes)


def line_endpoint_hits_boxes(element: Element, boxes: list[Element], processed: ProcessedImage) -> int:
    points = getattr(element.geometry, "points", ())
    if len(points) != 2:
        return 0
    return endpoint_box_hits(points[0], points[-1], boxes, margin=max(8.0, processed.scale.min_box_size * 0.45))


def short_unanchored_line(element: Element, boxes: list[Element], processed: ProcessedImage) -> bool:
    if not boxes:
        return False
    points = getattr(element.geometry, "points", ())
    if len(points) != 2:
        return False
    hits = endpoint_box_hits(points[0], points[-1], boxes, margin=max(8.0, processed.scale.min_box_size * 0.45))
    return hits == 0 and max(element.bbox.width, element.bbox.height) < max(60.0, processed.scale.min_linear_length * 1.25)


def parallel_line_is_duplicate(element: Element, existing: list[Element], scale) -> bool:
    if element.kind not in {"line", "arrow"}:
        return False
    points = getattr(element.geometry, "points", ())
    if len(points) != 2:
        return False
    start, end = points
    horizontal = abs(start.y - end.y) <= abs(start.x - end.x)
    margin = max(6.0, scale.estimated_stroke_width * 5.0)
    for prior in existing:
        if prior.kind not in {"line", "arrow"}:
            continue
        prior_points = getattr(prior.geometry, "points", ())
        if len(prior_points) != 2:
            continue
        prior_start, prior_end = prior_points
        prior_horizontal = abs(prior_start.y - prior_end.y) <= abs(prior_start.x - prior_end.x)
        if horizontal != prior_horizontal:
            continue
        if horizontal:
            if abs(start.y - prior_start.y) > margin:
                continue
            overlap = min(max(start.x, end.x), max(prior_start.x, prior_end.x)) - max(min(start.x, end.x), min(prior_start.x, prior_end.x))
            if overlap > 0 and overlap / max(1.0, min(abs(end.x - start.x), abs(prior_end.x - prior_start.x))) >= 0.7:
                return True
            continue
        if abs(start.x - prior_start.x) > margin:
            continue
        overlap = min(max(start.y, end.y), max(prior_start.y, prior_end.y)) - max(min(start.y, end.y), min(prior_start.y, prior_end.y))
        if overlap > 0 and overlap / max(1.0, min(abs(end.y - start.y), abs(prior_end.y - prior_start.y))) >= 0.7:
            return True
    return False


def overlap_on_smaller_area(first: BBox, second: BBox) -> float:
    x0 = max(first.x0, second.x0)
    y0 = max(first.y0, second.y0)
    x1 = min(first.x1, second.x1)
    y1 = min(first.y1, second.y1)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    intersection = (x1 - x0) * (y1 - y0)
    return intersection / max(1.0, min(first.area, second.area))


def ambiguous_wedge_line(element: Element, processed: ProcessedImage, config: PipelineConfig) -> bool:
    if element.kind != "line":
        return False
    points = getattr(element.geometry, "points", ())
    if len(points) != 2:
        return False
    start, end = points
    if min(abs(end.x - start.x), abs(end.y - start.y)) > processed.scale.estimated_stroke_width * 3.5:
        return False
    if max(abs(end.x - start.x), abs(end.y - start.y)) < processed.scale.min_linear_length * 1.1:
        return False
    start_ratio, end_ratio = line_endpoint_widening(element, processed.foreground_mask, processed.scale)
    return (
        max(start_ratio, end_ratio) >= config.min_arrow_widen_ratio
        and abs(start_ratio - end_ratio) <= 0.22
    )


def isolated_line_too_short(element: Element, processed: ProcessedImage) -> bool:
    if element.kind != "line":
        return False
    return max(element.bbox.width, element.bbox.height) < processed.scale.min_linear_length * 4.5


def line_endpoint_widening(element: Element, mask: np.ndarray, scale) -> tuple[float, float]:
    start, end = element.geometry.points
    band = max(3, int(round(scale.estimated_stroke_width * 2.6)))
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
