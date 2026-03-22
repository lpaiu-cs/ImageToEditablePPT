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
