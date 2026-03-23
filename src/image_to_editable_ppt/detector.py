from __future__ import annotations

from dataclasses import dataclass, replace
import math

import numpy as np

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


@dataclass(slots=True)
class DetectionResult:
    elements: list[Element]
    text_regions: list[BBox]
    rejected_regions: list[RejectedRegion]
    bridge_mask: np.ndarray


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
    hough_mask = processed.boundary_mask_raw.copy()
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
            horizontal=horizontal,
            vertical=vertical,
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
