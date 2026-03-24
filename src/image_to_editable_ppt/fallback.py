from __future__ import annotations

from dataclasses import dataclass, replace

from PIL import Image, ImageDraw

from .config import PipelineConfig
from .detector import RefinedNode, refine_node_geometry
from .diagnostics import DiagnosticsRecorder
from .schema import FallbackRegion, ObjectHypothesis
from .vlm_parser import VLMNode


@dataclass(slots=True)
class FallbackStageResult:
    refined_nodes: list[RefinedNode]
    fallback_regions: list[FallbackRegion]
    hypotheses: list[ObjectHypothesis]


def build_grow_fallback_hypotheses(
    image: Image.Image,
    nodes: list[VLMNode],
    *,
    anchor_bboxes: dict[str, object],
    config: PipelineConfig,
    diagnostics: DiagnosticsRecorder | None = None,
    stage: str = "03_objects",
) -> FallbackStageResult:
    recorder = diagnostics or DiagnosticsRecorder()
    refined_nodes: list[RefinedNode] = []
    fallback_regions: list[FallbackRegion] = []
    hypotheses: list[ObjectHypothesis] = []
    for node in nodes:
        anchor_bbox = anchor_bboxes.get(node.id)
        refined = refine_node_geometry(image, node, config, text_anchor=getattr(anchor_bbox, "bbox", None))
        refined_nodes.append(refined)
        fallback_region = FallbackRegion(
            id=f"fallback-region:{node.id}",
            kind="grow_fallback",
            bbox=refined.exact_bbox,
            score_total=refined.confidence,
            score_terms={"refined_confidence": refined.confidence},
            source_ids=["grow_fallback", node.id],
            provenance={"source": ["grow_fallback"], "vlm_ids": [node.id]},
            assigned_text_ids=[] if anchor_bbox is None else [anchor_bbox.id],
            assigned_vlm_ids=[node.id],
            object_type="textbox" if node.type == "text_only" else "container",
        )
        fallback_regions.append(fallback_region)
        hypotheses.append(
            ObjectHypothesis(
                id=f"object-hypothesis:{node.id}:fallback",
                kind=node.type,
                bbox=refined.exact_bbox,
                score_total=refined.confidence,
                score_terms={"refined_confidence": refined.confidence},
                source_ids=["grow_fallback", node.id],
                provenance={"source": ["grow_fallback"], "fallback_region_ids": [fallback_region.id]},
                assigned_text_ids=[] if anchor_bbox is None else [anchor_bbox.id],
                assigned_vlm_ids=[node.id],
                object_type="textbox" if node.type == "text_only" else "container",
                candidate_id=None,
                fallback=True,
            )
        )
    result = FallbackStageResult(
        refined_nodes=refined_nodes,
        fallback_regions=fallback_regions,
        hypotheses=hypotheses,
    )
    if recorder.enabled and fallback_regions:
        recorder.items(stage, "fallback_regions", fallback_regions)
        recorder.items(stage, "fallback_hypotheses", hypotheses)
        recorder.overlay(stage, "fallback_overlay", draw_fallback_overlay(image, fallback_regions))
    return result


def draw_fallback_overlay(
    image: Image.Image,
    fallback_regions: list[FallbackRegion],
) -> Image.Image:
    overlay = image.convert("RGB").copy()
    draw = ImageDraw.Draw(overlay)
    for region in fallback_regions:
        if region.bbox is None:
            continue
        draw.rectangle((region.bbox.x0, region.bbox.y0, region.bbox.x1, region.bbox.y1), outline=(255, 0, 255), width=2)
    return overlay
