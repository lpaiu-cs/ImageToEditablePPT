from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .components import remove_small_components
from .config import PipelineConfig
from .filtering import FilteredComponent, RejectedRegion, filter_residual_components
from .fitter import (
    extract_strokes,
    fit_boxes,
    fit_branchy_component_lines,
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
        processed.boundary_mask,
        "horizontal",
        config,
        array=processed.array,
        gray=processed.gray,
        min_length=box_min_length,
    )
    vertical = extract_strokes(
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
        boundary_mask=processed.boundary_mask,
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
        components=filtered.diagram_components,
        processed=processed,
        config=config,
        start_index=len(boxes) + 1,
        structural_elements=boxes,
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
    for filtered in components:
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
                elements.extend(fallback)
                next_index += len(fallback)
            continue
        elements.append(element)
        next_index += 1
    return elements
