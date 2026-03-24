from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path

from PIL import Image

from .config import PipelineConfig
from .diagnostics import DiagnosticsRecorder
from .emit import emit_shapes
from .exporter import export_to_pptx
from .fallback import build_grow_fallback_hypotheses
from .filtering import RejectedRegion
from .gating import gate_elements
from .geometry import build_geometry_candidates
from .graph import build_authoring_graph
from .guides import infer_guides
from .ir import Element
from .objects import build_object_hypotheses
from .preprocess import load_image, preprocess_image
from .reconstructors import build_motif_hypotheses
from .repair import repair_elements
from .selection import select_authoring_objects
from .text import OCRBackend, extract_text_elements, get_ocr_backend, normalize_and_merge_ocr
from .vlm_parser import DiagramStructure, StructureParser, VLMError, denormalize_structure, extract_structure


@dataclass(slots=True)
class ConversionResult:
    elements: list[Element]
    image_size: tuple[int, int]
    rejected_regions: list[RejectedRegion]
    output_path: Path | None = None
    pipeline_mode: str = "legacy"
    stage_artifacts: dict[str, object] = field(default_factory=dict)
    diagnostics_dir: Path | None = None


def convert_image(
    input_path: str | Path,
    output_path: str | Path,
    *,
    config: PipelineConfig | None = None,
    enable_ocr: bool = False,
    debug_elements_path: str | Path | None = None,
    ocr_backend: OCRBackend | None = None,
    structure_parser: StructureParser | None = None,
    diagnostics: DiagnosticsRecorder | None = None,
) -> ConversionResult:
    image = load_image(input_path)
    result = build_elements(
        image,
        config=config,
        enable_ocr=enable_ocr,
        ocr_backend=ocr_backend,
        input_path=input_path,
        structure_parser=structure_parser,
        diagnostics=diagnostics,
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
    diagnostics: DiagnosticsRecorder | None = None,
) -> ConversionResult:
    active_config = config or PipelineConfig()
    semantic = try_build_semantic_elements(
        image,
        config=active_config,
        enable_ocr=enable_ocr,
        ocr_backend=ocr_backend,
        input_path=input_path,
        structure_parser=structure_parser,
        diagnostics=diagnostics,
    )
    if semantic is not None:
        return semantic
    return build_elements_legacy(
        image,
        config=active_config,
        enable_ocr=enable_ocr,
        ocr_backend=ocr_backend,
    )


def try_build_semantic_elements(
    image: Image.Image,
    *,
    config: PipelineConfig,
    enable_ocr: bool,
    ocr_backend: OCRBackend | None,
    input_path: str | Path | None,
    structure_parser: StructureParser | None,
    diagnostics: DiagnosticsRecorder | None,
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
        diagnostics=diagnostics,
    )


def build_elements_from_structure(
    image: Image.Image,
    *,
    structure: DiagramStructure,
    config: PipelineConfig,
    enable_ocr: bool = False,
    ocr_backend: OCRBackend | None = None,
    diagnostics: DiagnosticsRecorder | None = None,
) -> ConversionResult:
    recorder = diagnostics or DiagnosticsRecorder()
    backend = ocr_backend or get_ocr_backend(True if structure.nodes else enable_ocr)
    text_result = normalize_and_merge_ocr(image, backend, config, diagnostics=recorder, stage="00_text")
    geometry_result = build_geometry_candidates(image, config, diagnostics=recorder, stage="01_geometry_raw")
    guide_result = infer_guides(
        image,
        geometry_result.rect_candidates,
        tolerance=max(8.0, config.snap_box_endpoint_margin * 0.75),
        diagnostics=recorder,
        stage="02_guides",
    )
    object_result = build_object_hypotheses(
        image,
        structure,
        text_result,
        guide_result.snapped_candidates,
        config,
        diagnostics=recorder,
        stage="03_objects",
    )
    fallback_result = build_grow_fallback_hypotheses(
        image,
        [node for node in object_result.vlm_nodes if node.id in set(object_result.unmatched_vlm_node_ids)],
        anchor_bboxes=object_result.anchor_map,
        config=config,
        diagnostics=recorder,
        stage="03_objects",
    )
    all_hypotheses = [*object_result.hypotheses, *fallback_result.hypotheses]
    motif_result = build_motif_hypotheses(
        image,
        all_hypotheses,
        guide_result.guide_field,
        diagnostics=recorder,
        stage="04_motifs",
    )
    selection_result = select_authoring_objects(
        image,
        all_hypotheses,
        motif_result.motifs,
        config,
        diagnostics=recorder,
        stage="05_selection",
    )
    graph_result = build_authoring_graph(
        image,
        selection_result.selected,
        selection_result.selected_motifs,
        structure.edges,
        diagnostics=recorder,
        stage="06_graph",
    )
    node_lookup = {node.id: node for node in object_result.vlm_nodes}
    emit_result = emit_shapes(
        image,
        selection_result.selected,
        graph_result,
        node_lookup,
        object_result.anchor_map,
        backend,
        config,
        guide_result.snapped_candidates,
        selection_result.selected_motifs,
        diagnostics=recorder,
        stage="07_emit",
    )
    stage_artifacts = {
        "00_text": {"words": text_result.words, "phrases": text_result.phrases},
        "01_geometry_raw": {
            "rect_candidates": geometry_result.rect_candidates,
            "connector_candidates": geometry_result.connector_candidates,
            "line_primitives": geometry_result.line_primitives,
            "region_primitives": geometry_result.region_primitives,
        },
        "02_guides": {
            "guide_field": guide_result.guide_field,
            "rect_candidates": guide_result.snapped_candidates,
            "snap_records": guide_result.snap_records,
        },
        "03_objects": {
            "hypotheses": object_result.hypotheses,
            "fallback_hypotheses": fallback_result.hypotheses,
            "fallback_regions": fallback_result.fallback_regions,
            "candidate_rankings": object_result.candidate_rankings,
        },
        "04_motifs": {"motifs": motif_result.motifs},
        "05_selection": {
            "selected": selection_result.selected,
            "suppressed": selection_result.suppressed,
            "selected_motifs": selection_result.selected_motifs,
            "motif_effects": selection_result.motif_effects,
            "conflicts": selection_result.conflict_graph,
        },
        "06_graph": {"graph": graph_result.graph, "graph_nodes": selection_result.selected, "motifs": selection_result.selected_motifs},
        "07_emit": {
            "emission_records": emit_result.emission_records,
            "dropped_records": emit_result.dropped_records,
            "fallback_regions": emit_result.fallback_regions,
        },
    }
    return ConversionResult(
        elements=emit_result.elements,
        image_size=image.size,
        rejected_regions=geometry_result.observations.detection.rejected_regions,
        pipeline_mode="semantic",
        stage_artifacts=stage_artifacts,
        diagnostics_dir=recorder.base_path,
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
    detection = geometry_detection(processed, config)
    elements = detection.elements
    elements = repair_elements(elements, processed, config, bridge_mask=detection.bridge_mask)
    from .detector import finalize_detected_elements

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


def geometry_detection(processed, config):
    from .detector import detect_elements_with_metadata

    return detect_elements_with_metadata(processed, config)


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
