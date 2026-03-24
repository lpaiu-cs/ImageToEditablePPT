from __future__ import annotations

from dataclasses import replace

from PIL import Image

from ..config import PipelineConfig
from ..detector import RefinedNode
from ..ir import BBox, BoxGeometry, Element, FillStyle, StrokeStyle, TextPayload
from ..text import OCRBackend


def hydrate_missing_node_texts(
    image: Image.Image,
    nodes: list[RefinedNode],
    backend: OCRBackend,
) -> list[RefinedNode]:
    hydrated: list[RefinedNode] = []
    for node in nodes:
        if node.text:
            hydrated.append(node)
            continue
        crop_box = (
            max(0, int(node.exact_bbox.x0)),
            max(0, int(node.exact_bbox.y0)),
            min(image.size[0], int(node.exact_bbox.x1)),
            min(image.size[1], int(node.exact_bbox.y1)),
        )
        if crop_box[2] - crop_box[0] < 4 or crop_box[3] - crop_box[1] < 4:
            hydrated.append(node)
            continue
        crop = image.crop(crop_box)
        regions = sorted(backend.extract(crop), key=lambda region: region.confidence, reverse=True)
        if not regions:
            hydrated.append(node)
            continue
        content = " ".join(region.text.strip() for region in regions if region.text.strip()).strip()
        if not content:
            hydrated.append(node)
            continue
        hydrated.append(replace(node, text=content))
    return hydrated


def emit_node_elements(
    node: RefinedNode,
    *,
    index: int,
    config: PipelineConfig,
) -> list[Element]:
    if node.type == "text_only":
        if not node.text:
            return []
        return [build_text_element(node, bbox=node.exact_bbox, element_id=f"text-{index}", confidence=0.97)]
    elements: list[Element] = []
    kind = "rounded_rect" if node.corner_radius > 0.0 or node.type == "cylinder" else "rect"
    elements.append(
        Element(
            id=f"node-{index}",
            kind=kind,
            geometry=BoxGeometry(node.exact_bbox, corner_radius=node.corner_radius),
            stroke=StrokeStyle(color=node.stroke_color, width=node.stroke_width),
            fill=FillStyle(enabled=node.fill_enabled, color=node.fill_color),
            text=None,
            confidence=node.confidence,
            source_region=node.exact_bbox,
            inferred=node.exact_bbox != node.approx_bbox,
        )
    )
    if node.text:
        text_bbox = inset_text_bbox(node.exact_bbox, config)
        elements.append(
            build_text_element(
                node,
                bbox=text_bbox,
                element_id=f"node-text-{index}",
                confidence=0.97,
            )
        )
    return elements


def build_text_element(
    node: RefinedNode,
    *,
    bbox: BBox,
    element_id: str,
    confidence: float,
) -> Element:
    return Element(
        id=element_id,
        kind="text",
        geometry=BoxGeometry(bbox),
        stroke=StrokeStyle(color=node.stroke_color, width=0.0),
        fill=FillStyle(enabled=False, color=None),
        text=TextPayload(content=node.text, alignment="center", confidence=confidence),
        confidence=confidence,
        source_region=bbox,
        inferred=node.exact_bbox != node.approx_bbox,
    )


def inset_text_bbox(bbox: BBox, config: PipelineConfig) -> BBox:
    horizontal = max(config.text_margin, bbox.width * 0.08)
    vertical = max(config.text_margin * 0.65, bbox.height * 0.14)
    inset = BBox(bbox.x0 + horizontal, bbox.y0 + vertical, bbox.x1 - horizontal, bbox.y1 - vertical)
    if inset.width < bbox.width * 0.35 or inset.height < bbox.height * 0.25:
        return bbox
    return inset
