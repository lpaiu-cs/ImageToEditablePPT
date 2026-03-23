from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from .components import remove_small_components
from .config import PipelineConfig
from .filtering import FilteredComponent, RejectedRegion, filter_residual_components
from .fitter import (
    extract_strokes,
    fit_boxes,
    fit_branchy_component_lines,
    fit_global_stroke_lines,
    fit_linear_component,
    fit_orthogonal_connector,
)
from .ir import BBox, Element
from .preprocess import ProcessedImage


@dataclass(slots=True)
class DetectionResult:
    elements: list[Element]
    text_regions: list[BBox]
    rejected_regions: list[RejectedRegion]


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
    text_filter = filter_residual_components(
        processed.detail_mask,
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
    linear = detect_linear_elements(
        components=filtered.diagram_components + filtered.weak_components,
        processed=processed,
        config=config,
        start_index=len(boxes) + 1,
        structural_elements=boxes,
    )
    if not linear and boxes and max(processed.size) >= 1800:
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
    return DetectionResult(
        elements=boxes + linear,
        text_regions=text_filter.text_regions,
        rejected_regions=filtered.rejected_regions
        + [region for region in text_filter.rejected_regions if region.label == "text_like"],
    )


def detect_linear_elements(
    *,
    components: list[FilteredComponent],
    processed: ProcessedImage,
    config: PipelineConfig,
    start_index: int,
    structural_elements: list[Element],
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
        element = fit_orthogonal_connector(
            component.pixels,
            processed.array,
            component.bbox,
            config,
            element_id=f"linear-{next_index}",
            scale=processed.scale,
            features=filtered.features,
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
                    if linear_element_is_duplicate(candidate, elements):
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
        if linear_element_is_duplicate(element, elements):
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
