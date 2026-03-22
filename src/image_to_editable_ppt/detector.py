from __future__ import annotations

import numpy as np

from .components import find_connected_components, remove_small_components
from .config import PipelineConfig
from .fitter import extract_strokes, fit_boxes, fit_linear_component, fit_orthogonal_connector
from .ir import Element
from .preprocess import ProcessedImage


def detect_elements(processed: ProcessedImage, config: PipelineConfig) -> list[Element]:
    horizontal = extract_strokes(processed.boundary_mask, "horizontal", config)
    vertical = extract_strokes(processed.boundary_mask, "vertical", config)
    boxes = fit_boxes(
        horizontal,
        vertical,
        boundary_mask=processed.boundary_mask,
        array=processed.array,
        background_color=processed.background_color,
        config=config,
    )
    residual = processed.foreground_mask.copy()
    for box in boxes:
        bbox = box.bbox.expand(2.0)
        x0 = max(0, int(bbox.x0))
        y0 = max(0, int(bbox.y0))
        x1 = min(residual.shape[1], int(np.ceil(bbox.x1)))
        y1 = min(residual.shape[0], int(np.ceil(bbox.y1)))
        residual[y0:y1, x0:x1] = False
    residual = remove_small_components(residual, config.min_component_area)
    linear = detect_linear_elements(
        residual_mask=residual,
        processed=processed,
        config=config,
        start_index=len(boxes) + 1,
    )
    return boxes + linear


def detect_linear_elements(
    *,
    residual_mask: np.ndarray,
    processed: ProcessedImage,
    config: PipelineConfig,
    start_index: int,
) -> list[Element]:
    elements: list[Element] = []
    next_index = start_index
    for component in find_connected_components(residual_mask):
        element = fit_linear_component(
            component.pixels,
            processed.array,
            component.bbox,
            config,
            element_id=f"linear-{next_index}",
        )
        if element is None:
            element = fit_orthogonal_connector(
                component.pixels,
                processed.array,
                component.bbox,
                config,
                element_id=f"linear-{next_index}",
            )
        if element is None:
            continue
        elements.append(element)
        next_index += 1
    return elements
