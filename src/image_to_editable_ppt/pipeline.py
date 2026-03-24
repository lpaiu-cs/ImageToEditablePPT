from __future__ import annotations

from dataclasses import dataclass, replace
import json
from pathlib import Path

from PIL import Image

from .config import PipelineConfig
from .detector import RefinedNode, detect_elements_with_metadata, finalize_detected_elements, refine_node_geometry
from .exporter import export_to_pptx
from .filtering import RejectedRegion
from .gating import gate_elements
from .ir import BBox, BoxGeometry, Element, FillStyle, StrokeStyle, TextPayload
from .preprocess import load_image, preprocess_image
from .repair import repair_elements
from .router import generate_connections
from .text import OCRBackend, extract_text_elements, get_ocr_backend
from .vlm_parser import DiagramStructure, StructureParser, VLMError, extract_structure


@dataclass(slots=True)
class ConversionResult:
    elements: list[Element]
    image_size: tuple[int, int]
    rejected_regions: list[RejectedRegion]
    output_path: Path | None = None
    pipeline_mode: str = "legacy"


def convert_image(
    input_path: str | Path,
    output_path: str | Path,
    *,
    config: PipelineConfig | None = None,
    enable_ocr: bool = False,
    debug_elements_path: str | Path | None = None,
    ocr_backend: OCRBackend | None = None,
    structure_parser: StructureParser | None = None,
) -> ConversionResult:
    image = load_image(input_path)
    result = build_elements(
        image,
        config=config,
        enable_ocr=enable_ocr,
        ocr_backend=ocr_backend,
        input_path=input_path,
        structure_parser=structure_parser,
    )
    export_to_pptx(result.elements, result.image_size, output_path, config or PipelineConfig())
    if debug_elements_path is not None:
        dump_debug_artifacts(result.elements, result.rejected_regions, debug_elements_path)
    result.output_path = Path(output_path)
    return result


def build_elements(
    image: Image.Image,
    *,
    config: PipelineConfig | None = None,
    enable_ocr: bool = False,
    ocr_backend: OCRBackend | None = None,
    input_path: str | Path | None = None,
    structure_parser: StructureParser | None = None,
) -> ConversionResult:
    active_config = config or PipelineConfig()
    semantic = try_build_semantic_elements(
        image,
        config=active_config,
        enable_ocr=enable_ocr,
        ocr_backend=ocr_backend,
        input_path=input_path,
        structure_parser=structure_parser,
    )
    if semantic is not None:
        return semantic
    return build_elements_legacy(image, config=active_config, enable_ocr=enable_ocr, ocr_backend=ocr_backend)


def try_build_semantic_elements(
    image: Image.Image,
    *,
    config: PipelineConfig,
    enable_ocr: bool,
    ocr_backend: OCRBackend | None,
    input_path: str | Path | None,
    structure_parser: StructureParser | None,
) -> ConversionResult | None:
    if not config.semantic_mode and structure_parser is None:
        return None
    try:
        structure = extract_structure(image, image_path=input_path, parser=structure_parser)
    except VLMError:
        if config.semantic_fallback_to_legacy and structure_parser is None:
            return None
        raise
    return build_elements_from_structure(
        image,
        structure=structure,
        config=config,
        enable_ocr=enable_ocr,
        ocr_backend=ocr_backend,
    )


def build_elements_from_structure(
    image: Image.Image,
    *,
    structure: DiagramStructure,
    config: PipelineConfig,
    enable_ocr: bool = False,
    ocr_backend: OCRBackend | None = None,
) -> ConversionResult:
    backend = ocr_backend or get_ocr_backend(enable_ocr)
    refined_nodes = [refine_node_geometry(image, node, config) for node in structure.nodes]
    refined_nodes = hydrate_missing_node_texts(image, refined_nodes, backend)
    node_elements: list[Element] = []
    for index, node in enumerate(refined_nodes, start=1):
        node_elements.extend(node_to_elements(node, index=index, config=config))
    edge_elements = generate_connections(refined_nodes, structure.edges, config)
    elements = gate_elements(node_elements + edge_elements, config)
    return ConversionResult(
        elements=elements,
        image_size=image.size,
        rejected_regions=[],
        pipeline_mode="semantic",
    )


def build_elements_legacy(
    image: Image.Image,
    *,
    config: PipelineConfig,
    enable_ocr: bool = False,
    ocr_backend: OCRBackend | None = None,
) -> ConversionResult:
    processed = preprocess_image(
        image,
        foreground_threshold=config.foreground_threshold,
        min_component_area=config.min_component_area,
        min_stroke_length=config.min_stroke_length,
        min_box_size=config.min_box_size,
        min_relative_line_length=config.min_relative_line_length,
        min_relative_box_size=config.min_relative_box_size,
        adaptive_background=config.adaptive_background,
        background_blur_divisor=config.background_blur_divisor,
        fill_region_background_ratio=config.fill_region_background_ratio,
        fill_region_uniformity_ratio=config.fill_region_uniformity_ratio,
        fill_region_edge_ratio=config.fill_region_edge_ratio,
        non_diagram_edge_density=config.non_diagram_edge_density,
        non_diagram_color_variance=config.non_diagram_color_variance,
        non_diagram_side_support=config.non_diagram_side_support,
    )
    detection = detect_elements_with_metadata(processed, config)
    elements = detection.elements
    elements = repair_elements(elements, processed, config, bridge_mask=detection.bridge_mask)
    elements = finalize_detected_elements(elements, processed, config)
    backend = ocr_backend or get_ocr_backend(enable_ocr)
    text = extract_text_elements(
        image,
        elements,
        config,
        backend=backend,
        candidate_regions=detection.text_regions,
    )
    gated = gate_elements(elements + text, config)
    return ConversionResult(
        elements=gated,
        image_size=image.size,
        rejected_regions=detection.rejected_regions,
        pipeline_mode="legacy",
    )


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


def node_to_elements(node: RefinedNode, *, index: int, config: PipelineConfig) -> list[Element]:
    if node.type == "text_only":
        if not node.text:
            return []
        return [build_text_element(node, bbox=node.exact_bbox, element_id=f"text-{index}", confidence=0.97)]
    elements: list[Element] = []
    kind = "rounded_rect" if node.corner_radius > 0.0 or node.type == "cylinder" else "rect"
    box = Element(
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
    elements.append(box)
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


def dump_elements(elements: list[Element], path: str | Path) -> None:
    with Path(path).open("w", encoding="utf-8") as handle:
        json.dump([element.to_dict() for element in elements], handle, indent=2)


def dump_debug_artifacts(
    elements: list[Element],
    rejected_regions: list[RejectedRegion],
    path: str | Path,
) -> None:
    target = Path(path)
    dump_elements(elements, target)
    rejection_name = f"{target.stem}.rejections{target.suffix or '.json'}"
    rejection_path = target.with_name(rejection_name)
    with rejection_path.open("w", encoding="utf-8") as handle:
        json.dump([region.to_dict() for region in rejected_regions], handle, indent=2)
