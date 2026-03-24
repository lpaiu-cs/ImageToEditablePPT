from __future__ import annotations

from dataclasses import dataclass, replace
from difflib import SequenceMatcher
import json
from pathlib import Path

from PIL import Image

from .config import PipelineConfig
from .detector import (
    RefinedNode,
    detect_elements_with_metadata,
    finalize_detected_elements,
    refine_node_geometry,
    verify_edge_exists,
)
from .exporter import export_to_pptx
from .filtering import RejectedRegion
from .gating import gate_elements
from .ir import BBox, BoxGeometry, Element, FillStyle, StrokeStyle, TextPayload
from .preprocess import load_image, preprocess_image
from .repair import repair_elements
from .router import generate_connections
from .text import OCRBackend, OCRTextRegion, extract_text_elements, get_ocr_backend, merge_ocr_regions, normalize_ocr_text
from .vlm_parser import DiagramStructure, StructureParser, VLMEdge, VLMError, VLMNode, denormalize_structure, extract_structure


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
    structure = denormalize_structure(structure, image_size=image.size)
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
    backend = ocr_backend or get_ocr_backend(True)
    semantic_ocr = collect_semantic_ocr_regions(image, backend, config)
    anchored_nodes, anchor_map = anchor_nodes_to_ocr(structure.nodes, semantic_ocr, config)
    geometry_candidates = detect_global_geometry_candidates(image, config)
    candidate_assignments = assign_geometry_candidates_to_nodes(
        anchored_nodes,
        anchor_map,
        geometry_candidates,
        semantic_ocr,
        config,
    )
    refined_nodes = [
        refine_node_geometry(
            image,
            replace(node, approx_bbox=candidate_assignments[node.id].bbox) if node.id in candidate_assignments else node,
            config,
            text_anchor=anchor_map.get(node.id).bbox if node.id not in candidate_assignments and node.id in anchor_map else None,
        )
        for node in anchored_nodes
    ]
    refined_nodes = hydrate_missing_node_texts(image, refined_nodes, backend)
    verified_edges = verify_semantic_edges(image, refined_nodes, structure.edges, config)
    node_elements: list[Element] = []
    for index, node in enumerate(refined_nodes, start=1):
        node_elements.extend(node_to_elements(node, index=index, config=config))
    edge_elements = generate_connections(refined_nodes, verified_edges, config)
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


def collect_semantic_ocr_regions(
    image: Image.Image,
    backend: OCRBackend,
    config: PipelineConfig,
) -> list[OCRTextRegion]:
    return merge_ocr_regions(
        [
            region
            for region in backend.extract(image)
            if region.confidence >= config.semantic_ocr_confidence and region.text.strip()
        ]
    )


def anchor_nodes_to_ocr(
    nodes: list[VLMNode],
    ocr_regions: list[OCRTextRegion],
    config: PipelineConfig,
) -> tuple[list[VLMNode], dict[str, OCRTextRegion]]:
    if not ocr_regions:
        return nodes, {}
    assignments: dict[str, OCRTextRegion] = {}
    used_indices: set[int] = set()
    for node in sorted(nodes, key=lambda candidate: len(candidate.text or ""), reverse=True):
        anchor_index = find_best_ocr_anchor(node, ocr_regions, used_indices, config)
        if anchor_index is None:
            continue
        used_indices.add(anchor_index)
        assignments[node.id] = ocr_regions[anchor_index]
    anchored = [
        replace(node, text=assignments[node.id].text) if node.id in assignments else node
        for node in nodes
    ]
    return anchored, assignments


def find_best_ocr_anchor(
    node: VLMNode,
    ocr_regions: list[OCRTextRegion],
    used_regions: set[int],
    config: PipelineConfig,
) -> int | None:
    target = normalize_ocr_text(node.text)
    if not target:
        return None
    best: tuple[float, int] | None = None
    for index, region in enumerate(ocr_regions):
        if index in used_regions:
            continue
        candidate_text = normalize_ocr_text(region.text)
        if not candidate_text:
            continue
        similarity = SequenceMatcher(None, target, candidate_text).ratio()
        if similarity < config.semantic_ocr_similarity:
            continue
        hint = ocr_hint_score(node.approx_bbox, region.bbox)
        score = similarity * (1.0 - config.semantic_ocr_hint_weight) + hint * config.semantic_ocr_hint_weight
        if best is None or score > best[0]:
            best = (score, index)
    return None if best is None else best[1]


def ocr_hint_score(hint_bbox: BBox, region_bbox: BBox) -> float:
    if hint_bbox.expand(max(20.0, min(hint_bbox.width, hint_bbox.height) * 0.35)).contains_point(region_bbox.center):
        return 1.0
    dx = hint_bbox.center.x - region_bbox.center.x
    dy = hint_bbox.center.y - region_bbox.center.y
    distance = (dx * dx + dy * dy) ** 0.5
    diagonal = max(1.0, (hint_bbox.width * hint_bbox.width + hint_bbox.height * hint_bbox.height) ** 0.5)
    return max(0.0, 1.0 - distance / (diagonal * 4.0))


def verify_semantic_edges(
    image: Image.Image,
    nodes: list[RefinedNode],
    edges: list[VLMEdge],
    config: PipelineConfig,
) -> list[VLMEdge]:
    node_map = {node.id: node for node in nodes}
    verified: list[VLMEdge] = []
    for edge in edges:
        source = node_map.get(edge.source)
        target = node_map.get(edge.target)
        if source is None or target is None:
            continue
        if verify_edge_exists(
            image,
            source.exact_bbox,
            target.exact_bbox,
            config,
            expect_dashed=edge.type == "dashed_arrow",
        ):
            verified.append(edge)
    return verified


def detect_global_geometry_candidates(
    image: Image.Image,
    config: PipelineConfig,
) -> list[Element]:
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
    boxes = [element for element in detection.elements if element.kind in {"rect", "rounded_rect"}]
    return snap_candidates_to_guides(boxes, tolerance=max(8.0, config.snap_box_endpoint_margin * 0.75))


def snap_candidates_to_guides(candidates: list[Element], *, tolerance: float) -> list[Element]:
    if not candidates:
        return []
    xs = [candidate.bbox.x0 for candidate in candidates] + [candidate.bbox.x1 for candidate in candidates]
    ys = [candidate.bbox.y0 for candidate in candidates] + [candidate.bbox.y1 for candidate in candidates]
    x_guides = cluster_guides(xs, tolerance=tolerance)
    y_guides = cluster_guides(ys, tolerance=tolerance)
    snapped: list[Element] = []
    for candidate in candidates:
        bbox = BBox(
            snap_value(candidate.bbox.x0, x_guides),
            snap_value(candidate.bbox.y0, y_guides),
            snap_value(candidate.bbox.x1, x_guides),
            snap_value(candidate.bbox.y1, y_guides),
        )
        if bbox.width <= 1.0 or bbox.height <= 1.0:
            snapped.append(candidate)
            continue
        geometry = BoxGeometry(bbox=bbox, corner_radius=getattr(candidate.geometry, "corner_radius", 0.0))
        snapped.append(
            replace(
                candidate,
                geometry=geometry,
                source_region=bbox,
            )
        )
    return snapped


def cluster_guides(values: list[float], *, tolerance: float) -> list[float]:
    if not values:
        return []
    ordered = sorted(values)
    clusters: list[list[float]] = [[ordered[0]]]
    for value in ordered[1:]:
        if abs(value - clusters[-1][-1]) <= tolerance:
            clusters[-1].append(value)
        else:
            clusters.append([value])
    return [sum(cluster) / len(cluster) for cluster in clusters]


def snap_value(value: float, guides: list[float]) -> float:
    if not guides:
        return value
    return min(guides, key=lambda guide: abs(guide - value))


def assign_geometry_candidates_to_nodes(
    nodes: list[VLMNode],
    anchor_map: dict[str, OCRTextRegion],
    candidates: list[Element],
    ocr_regions: list[OCRTextRegion],
    config: PipelineConfig,
) -> dict[str, Element]:
    assigned: dict[str, Element] = {}
    used_candidates: set[str] = set()
    ordered_nodes = sorted(
        nodes,
        key=lambda node: (
            anchor_map[node.id].bbox.area if node.id in anchor_map else node.approx_bbox.area,
            len(node.text or ""),
        ),
    )
    for node in ordered_nodes:
        candidate = select_candidate_for_node(node, anchor_map.get(node.id), candidates, used_candidates, ocr_regions, config)
        if candidate is None:
            continue
        assigned[node.id] = candidate
        used_candidates.add(candidate.id)
    return assigned


def select_candidate_for_node(
    node: VLMNode,
    anchor: OCRTextRegion | None,
    candidates: list[Element],
    used_candidates: set[str],
    ocr_regions: list[OCRTextRegion],
    config: PipelineConfig,
) -> Element | None:
    best: tuple[float, Element] | None = None
    for candidate in candidates:
        if candidate.id in used_candidates:
            continue
        score = candidate_score(node, anchor, candidate, ocr_regions, config)
        if score is None:
            continue
        if best is None or score > best[0]:
            best = (score, candidate)
    return None if best is None or best[0] < 1.35 else best[1]


def candidate_score(
    node: VLMNode,
    anchor: OCRTextRegion | None,
    candidate: Element,
    ocr_regions: list[OCRTextRegion],
    config: PipelineConfig,
) -> float | None:
    bbox = candidate.bbox
    score = candidate.confidence * 0.8
    if anchor is not None:
        if not bbox.expand(max(12.0, config.text_margin)).contains_point(anchor.bbox.center):
            return None
        score += 2.6
        score += bbox.iou(anchor.bbox.expand(config.text_margin * 1.5)) * 0.4
        margins = (
            anchor.bbox.x0 - bbox.x0,
            anchor.bbox.y0 - bbox.y0,
            bbox.x1 - anchor.bbox.x1,
            bbox.y1 - anchor.bbox.y1,
        )
        if min(margins) < 0:
            return None
        score += min(margins) / max(8.0, config.text_margin) * 0.08
    else:
        overlap = bbox.iou(node.approx_bbox)
        if overlap < 0.05:
            return None
        score += overlap * 1.2
    score += bbox.iou(node.approx_bbox) * 0.75
    anchor_area = anchor.bbox.area if anchor is not None else max(1.0, node.approx_bbox.area * 0.2)
    area_ratio = bbox.area / max(1.0, anchor_area)
    score -= min(3.2, max(0.0, area_ratio - 1.0) * 0.06)
    score -= composite_box_penalty(bbox, anchor, ocr_regions)
    return score


def composite_box_penalty(
    bbox: BBox,
    anchor: OCRTextRegion | None,
    ocr_regions: list[OCRTextRegion],
) -> float:
    penalty = 0.0
    anchor_center = None if anchor is None else anchor.bbox.center
    extras = 0
    for region in ocr_regions:
        center = region.bbox.center
        if not bbox.contains_point(center):
            continue
        if anchor_center is not None and abs(center.x - anchor_center.x) < 6.0 and abs(center.y - anchor_center.y) < 6.0:
            continue
        extras += 1
    if extras > 0:
        penalty += extras * 0.85
    return penalty


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
