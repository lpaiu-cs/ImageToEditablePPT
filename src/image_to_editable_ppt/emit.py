from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, ImageDraw

from .config import PipelineConfig
from .diagnostics import DiagnosticsRecorder
from .gating import gate_elements
from .graph import GraphBuildResult
from .ir import Element
from .reconstructors import (
    build_raster_fallback_regions,
    emit_connector_elements,
    emit_node_elements,
    hydrate_missing_node_texts,
    hypothesis_to_refined_node,
    verify_graph_connectors,
)
from .reconstructors.connectors import ConnectorSpec
from .schema import DropReason, EmissionRecord, MotifHypothesis, ObjectHypothesis, RectCandidate, validate_emission_trace, validate_stage_entities
from .text import OCRBackend
from .vlm_parser import VLMEdge, VLMNode


@dataclass(slots=True)
class EmitStageResult:
    elements: list[Element]
    emission_records: list[EmissionRecord]
    dropped_records: list[EmissionRecord]
    fallback_regions: list[object]


def emit_shapes(
    image: Image.Image,
    selected: list[ObjectHypothesis],
    graph_result: GraphBuildResult,
    node_lookup: dict[str, VLMNode],
    anchor_map: dict[str, object],
    backend: OCRBackend,
    config: PipelineConfig,
    geometry_candidates: list[RectCandidate],
    motif_hypotheses: list[MotifHypothesis],
    *,
    diagnostics: DiagnosticsRecorder | None = None,
    stage: str = "07_emit",
) -> EmitStageResult:
    recorder = diagnostics or DiagnosticsRecorder()
    selected_by_hypothesis_id = {hypothesis.id: hypothesis for hypothesis in selected}
    node_order = {node_id: index for index, node_id in enumerate(node_lookup)}
    ordered_selected = sorted(
        selected,
        key=lambda hypothesis: node_order.get(hypothesis.assigned_vlm_ids[0], 10_000) if hypothesis.assigned_vlm_ids else 10_000,
    )

    raster_fallback = build_raster_fallback_regions(image, ordered_selected, config, stage=stage)
    raster_hypothesis_ids = {
        record.hypothesis_ids[0]
        for record in raster_fallback.emission_records
        if record.hypothesis_ids
    }
    native_selected = [hypothesis for hypothesis in ordered_selected if hypothesis.id not in raster_hypothesis_ids]

    refined_nodes = []
    node_hypothesis_pairs: list[tuple[VLMNode, ObjectHypothesis]] = []
    for hypothesis in native_selected:
        if not hypothesis.assigned_vlm_ids:
            continue
        node = node_lookup.get(hypothesis.assigned_vlm_ids[0])
        if node is None:
            continue
        refined = hypothesis_to_refined_node(image, node, hypothesis, config, anchor_bbox=anchor_map.get(node.id))
        refined_nodes.append(refined)
        node_hypothesis_pairs.append((node, hypothesis))
    refined_nodes = hydrate_missing_node_texts(image, refined_nodes, backend)

    connector_specs = graph_edges_to_connector_specs(graph_result.graph.edges, selected_by_hypothesis_id)
    verified = verify_graph_connectors(image, refined_nodes, connector_specs, config)

    elements: list[Element] = []
    emission_records: list[EmissionRecord] = []
    for index, (refined, (_, hypothesis)) in enumerate(zip(refined_nodes, node_hypothesis_pairs, strict=True), start=1):
        for element in emit_node_elements(refined, index=index, config=config):
            elements.append(element)
            emission_records.append(
                EmissionRecord(
                    id=f"emit:{element.id}",
                    kind=element.kind,
                    bbox=element.bbox,
                    score_total=element.confidence,
                    score_terms={"confidence": element.confidence},
                    source_ids=list(hypothesis.source_ids),
                    provenance={"graph_node_ids": [hypothesis.id], "hypothesis_ids": [hypothesis.id]},
                    assigned_text_ids=list(hypothesis.assigned_text_ids),
                    assigned_vlm_ids=list(hypothesis.assigned_vlm_ids),
                    object_type=hypothesis.object_type,
                    primitive_kind=element.kind,
                    graph_node_ids=[hypothesis.id],
                    hypothesis_ids=[hypothesis.id],
                    emitted_element_id=element.id,
                )
            )

    for spec in verified.verified_specs:
        source_hypothesis = selected_by_hypothesis_id[spec.source_hypothesis_id]
        target_hypothesis = selected_by_hypothesis_id[spec.target_hypothesis_id]
        for element in emit_connector_elements(refined_nodes, [spec.edge], config):
            elements.append(element)
            emission_records.append(
                EmissionRecord(
                    id=f"emit:{element.id}",
                    kind=element.kind,
                    bbox=element.bbox,
                    score_total=element.confidence,
                    score_terms={"confidence": element.confidence},
                    source_ids=[spec.graph_edge_id, *source_hypothesis.source_ids, *target_hypothesis.source_ids],
                    provenance={
                        "graph_edge_ids": [spec.graph_edge_id],
                        "graph_node_ids": [spec.source_hypothesis_id, spec.target_hypothesis_id],
                        "hypothesis_ids": [spec.source_hypothesis_id, spec.target_hypothesis_id],
                    },
                    object_type="connector",
                    primitive_kind=element.kind,
                    graph_node_ids=[spec.source_hypothesis_id, spec.target_hypothesis_id],
                    hypothesis_ids=[spec.source_hypothesis_id, spec.target_hypothesis_id],
                    emitted_element_id=element.id,
                )
            )

    elements.extend(raster_fallback.elements)
    emission_records.extend(raster_fallback.emission_records)

    gated = gate_elements(elements, config)
    dropped_records = list(verified.dropped_records)
    for hypothesis in selected:
        if not hypothesis.assigned_vlm_ids:
            dropped_records.append(
                EmissionRecord(
                    id=f"emit-drop:{hypothesis.id}",
                    kind="drop",
                    bbox=hypothesis.bbox,
                    score_total=0.0,
                    score_terms={"no_vlm_assignment": 1.0},
                    source_ids=list(hypothesis.source_ids),
                    provenance=hypothesis.provenance,
                    object_type=hypothesis.object_type,
                    primitive_kind="none",
                    graph_node_ids=[hypothesis.id],
                    hypothesis_ids=[hypothesis.id],
                    drop_reason=DropReason.EMISSION_UNSUPPORTED,
                )
            )

    emission_records = list(validate_stage_entities(stage, "emission_records", emission_records, require_bbox=True))
    dropped_records = list(validate_stage_entities(stage, "dropped_records", dropped_records))
    validate_emission_trace(
        emission_records=emission_records,
        graph=graph_result.graph,
        object_hypotheses=selected,
        motif_hypotheses=motif_hypotheses,
        geometry_candidates=geometry_candidates,
        fallback_regions=raster_fallback.regions,
    )

    result = EmitStageResult(
        elements=gated,
        emission_records=emission_records,
        dropped_records=dropped_records,
        fallback_regions=raster_fallback.regions,
    )
    if recorder.enabled:
        recorder.summary(
            stage,
            {
                "emitted_element_count": len(gated),
                "emission_record_count": len(emission_records),
                "dropped_record_count": len(dropped_records),
                "raster_fallback_count": len(raster_fallback.regions),
            },
        )
        recorder.items(stage, "emission_records", emission_records)
        recorder.items(stage, "dropped_records", dropped_records)
        recorder.items(stage, "raster_fallback_regions", raster_fallback.regions)
        for region, element in zip(raster_fallback.regions, raster_fallback.elements, strict=True):
            if element.raster_image is None:
                continue
            recorder.overlay(stage, f"fallback_asset_{region.asset_id}", Image.open(io.BytesIO(element.raster_image)))
        recorder.overlay(stage, "overlay", draw_emit_overlay(image, gated))
    return result


def graph_edges_to_connector_specs(
    graph_edges,
    selected_by_hypothesis_id: dict[str, ObjectHypothesis],
) -> list[ConnectorSpec]:
    candidate_edges: list[ConnectorSpec] = []
    for edge in graph_edges:
        if edge.edge_type != "attaches":
            continue
        source = selected_by_hypothesis_id.get(edge.source_id)
        target = selected_by_hypothesis_id.get(edge.target_id)
        if source is None or target is None or not source.assigned_vlm_ids or not target.assigned_vlm_ids:
            continue
        candidate_edges.append(
            ConnectorSpec(
                edge=VLMEdge(
                    source=source.assigned_vlm_ids[0],
                    target=target.assigned_vlm_ids[0],
                    type=str(edge.metadata.get("connector_type", "line")),
                    label=str(edge.metadata.get("label", "")),
                ),
                graph_edge_id=edge.id,
                source_hypothesis_id=edge.source_id,
                target_hypothesis_id=edge.target_id,
            )
        )
    return candidate_edges


def draw_emit_overlay(
    image: Image.Image,
    elements: list[Element],
) -> Image.Image:
    overlay = image.convert("RGB").copy()
    draw = ImageDraw.Draw(overlay)
    for element in elements:
        if element.kind in {"rect", "rounded_rect", "text", "raster_region"}:
            draw.rectangle((element.bbox.x0, element.bbox.y0, element.bbox.x1, element.bbox.y1), outline=(0, 0, 0), width=1)
            continue
        points = getattr(element.geometry, "points", ())
        if len(points) >= 2:
            draw.line([(point.x, point.y) for point in points], fill=(0, 0, 0), width=1)
    return overlay
