from __future__ import annotations

from .config import PipelineConfig
from .ir import Element


def gate_elements(elements: list[Element], config: PipelineConfig) -> list[Element]:
    gated: list[Element] = []
    for element in elements:
        if element.kind == "text":
            if element.confidence >= config.text_confidence:
                gated.append(element)
            continue
        if borderless_fill_panel_candidate(element, config):
            gated.append(element)
            continue
        if element.confidence >= config.inclusion_confidence:
            gated.append(element)
            continue
        if element.confidence >= config.tentative_confidence and element.kind in {
            "rect",
            "rounded_rect",
            "line",
            "orthogonal_connector",
            "arrow",
        }:
            gated.append(element)
    return gated


def borderless_fill_panel_candidate(element: Element, config: PipelineConfig) -> bool:
    return (
        element.kind in {"rect", "rounded_rect"}
        and element.fill.enabled
        and element.fill.color is not None
        and element.inferred
        and element.stroke.width <= 1.5
        and element.confidence >= min(config.filled_panel_accept_confidence, config.inclusion_confidence)
    )
