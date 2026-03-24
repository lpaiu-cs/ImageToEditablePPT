from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageDraw

from .diagnostics import DiagnosticsRecorder
from .ir import BBox
from .schema import AuthoringGraph, GraphEdge, MotifHypothesis, ObjectHypothesis, validate_stage_entities
from .vlm_parser import VLMEdge


@dataclass(slots=True)
class GraphBuildResult:
    graph: AuthoringGraph


def build_authoring_graph(
    image: Image.Image,
    selected: list[ObjectHypothesis],
    motifs: list[MotifHypothesis],
    vlm_edges: list[VLMEdge],
    *,
    diagnostics: DiagnosticsRecorder | None = None,
    stage: str = "06_graph",
) -> GraphBuildResult:
    recorder = diagnostics or DiagnosticsRecorder()
    validate_stage_entities(stage, "selected_hypotheses", selected, require_bbox=True)
    validate_stage_entities(stage, "motifs", motifs)
    graph_edges: list[GraphEdge] = []
    hypothesis_by_vlm_id = {
        hypothesis.assigned_vlm_ids[0]: hypothesis
        for hypothesis in selected
        if hypothesis.assigned_vlm_ids
    }
    next_index = 1
    for motif in motifs:
        for member_id in motif.member_ids:
            graph_edges.append(
                GraphEdge(
                    id=f"graph-edge-{next_index:03d}",
                    edge_type="contains",
                    source_id=motif.id,
                    target_id=member_id,
                    score_total=motif.score_total,
                    score_terms={"contains": 1.0},
                    source_ids=[motif.id, member_id],
                )
            )
            next_index += 1
    for edge in vlm_edges:
        source = hypothesis_by_vlm_id.get(edge.source)
        target = hypothesis_by_vlm_id.get(edge.target)
        if source is None or target is None:
            continue
        graph_edges.append(
            GraphEdge(
                id=f"graph-edge-{next_index:03d}",
                edge_type="attaches",
                source_id=source.id,
                target_id=target.id,
                score_total=min(source.score_total, target.score_total),
                score_terms={"semantic_edge": 1.0},
                source_ids=[edge.source, edge.target],
                metadata={"connector_type": edge.type, "label": edge.label},
            )
        )
        next_index += 1
    for index, first in enumerate(selected):
        if first.bbox is None:
            continue
        for second in selected[index + 1 :]:
            if second.bbox is None:
                continue
            if abs(first.bbox.center.x - second.bbox.center.x) <= 8.0:
                graph_edges.append(
                    GraphEdge(
                        id=f"graph-edge-{next_index:03d}",
                        edge_type="align_x",
                        source_id=first.id,
                        target_id=second.id,
                        score_total=1.0,
                        score_terms={"center_delta": abs(first.bbox.center.x - second.bbox.center.x)},
                        source_ids=[first.id, second.id],
                    )
                )
                next_index += 1
            if abs(first.bbox.center.y - second.bbox.center.y) <= 8.0:
                graph_edges.append(
                    GraphEdge(
                        id=f"graph-edge-{next_index:03d}",
                        edge_type="align_y",
                        source_id=first.id,
                        target_id=second.id,
                        score_total=1.0,
                        score_terms={"center_delta": abs(first.bbox.center.y - second.bbox.center.y)},
                        source_ids=[first.id, second.id],
                    )
                )
                next_index += 1
            if first.guide_ids and second.guide_ids and set(first.guide_ids) & set(second.guide_ids):
                graph_edges.append(
                    GraphEdge(
                        id=f"graph-edge-{next_index:03d}",
                        edge_type="repeat",
                        source_id=first.id,
                        target_id=second.id,
                        score_total=1.0,
                        score_terms={"shared_guides": float(len(set(first.guide_ids) & set(second.guide_ids)))},
                        source_ids=[first.id, second.id],
                    )
                )
                next_index += 1
            if first.bbox.area >= second.bbox.area:
                graph_edges.append(
                    GraphEdge(
                        id=f"graph-edge-{next_index:03d}",
                        edge_type="z_before",
                        source_id=first.id,
                        target_id=second.id,
                        score_total=1.0,
                        score_terms={"area_order": first.bbox.area - second.bbox.area},
                        source_ids=[first.id, second.id],
                    )
                )
                next_index += 1
    graph_nodes = [hypothesis.id for hypothesis in selected] + [motif.id for motif in motifs]
    bbox = union_bbox([hypothesis.bbox for hypothesis in selected if hypothesis.bbox is not None])
    graph = AuthoringGraph(
        id="authoring-graph",
        kind="authoring_graph",
        bbox=bbox,
        score_total=float(len(graph_edges)),
        score_terms={"edge_count": float(len(graph_edges)), "node_count": float(len(graph_nodes))},
        source_ids=[hypothesis.id for hypothesis in selected],
        node_ids=graph_nodes,
        edges=graph_edges,
    )
    result = GraphBuildResult(graph=graph)
    if recorder.enabled:
        recorder.summary(stage, {"graph_node_count": len(graph.node_ids), "graph_edge_count": len(graph.edges)})
        recorder.items(stage, "graph_edges", graph.edges)
        recorder.artifact(stage, "graph", graph)
        recorder.overlay(stage, "overlay", draw_graph_overlay(image, selected, graph.edges))
    return result


def union_bbox(boxes: list[BBox]) -> BBox | None:
    if not boxes:
        return None
    return BBox(
        min(box.x0 for box in boxes),
        min(box.y0 for box in boxes),
        max(box.x1 for box in boxes),
        max(box.y1 for box in boxes),
    )


def draw_graph_overlay(
    image: Image.Image,
    selected: list[ObjectHypothesis],
    edges: list[GraphEdge],
) -> Image.Image:
    overlay = image.convert("RGB").copy()
    draw = ImageDraw.Draw(overlay)
    lookup = {hypothesis.id: hypothesis for hypothesis in selected}
    for hypothesis in selected:
        if hypothesis.bbox is None:
            continue
        draw.rectangle((hypothesis.bbox.x0, hypothesis.bbox.y0, hypothesis.bbox.x1, hypothesis.bbox.y1), outline=(34, 139, 34), width=2)
    for edge in edges:
        if edge.edge_type not in {"attaches", "align_x", "align_y"}:
            continue
        source = lookup.get(edge.source_id)
        target = lookup.get(edge.target_id)
        if source is None or target is None or source.bbox is None or target.bbox is None:
            continue
        draw.line(
            (
                source.bbox.center.x,
                source.bbox.center.y,
                target.bbox.center.x,
                target.bbox.center.y,
            ),
            fill=(0, 0, 255) if edge.edge_type == "attaches" else (128, 128, 128),
            width=1,
        )
    return overlay
