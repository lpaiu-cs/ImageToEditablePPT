from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
from PIL import Image, ImageDraw

try:
    import cv2
except ImportError:  # pragma: no cover - guarded by dependency/tests
    cv2 = None

from .config import PipelineConfig
from .detector import RefinedNode, refine_node_geometry
from .diagnostics import DiagnosticsRecorder
from .geometry import bbox_contains, clamp_bbox, merge_bboxes, snap_bbox_to_local_contour
from .ir import BBox
from .schema import FallbackRegion, ObjectHypothesis, validate_stage_entities
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
        fallback_regions=list(validate_stage_entities(stage, "fallback_regions", fallback_regions, require_bbox=True)),
        hypotheses=list(validate_stage_entities(stage, "fallback_hypotheses", hypotheses, require_bbox=True)),
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


def grow_container_from_text_anchor(
    array: np.ndarray,
    text_anchor: BBox,
    hint_bbox: BBox,
    config: PipelineConfig,
) -> BBox:
    seed_padding = max(config.local_refine_padding * 0.6, text_anchor.height * 1.2, text_anchor.width * 0.22)
    seed_bbox = clamp_bbox(text_anchor.expand(seed_padding), width=array.shape[1], height=array.shape[0])
    if cv2 is None:
        return snap_bbox_to_local_contour(array, merge_bboxes(seed_bbox, hint_bbox), config)
    search_bbox = clamp_bbox(
        merge_bboxes(seed_bbox.expand(seed_padding), hint_bbox.expand(config.local_refine_padding)),
        width=array.shape[1],
        height=array.shape[0],
    )
    x0 = int(math.floor(search_bbox.x0))
    y0 = int(math.floor(search_bbox.y0))
    x1 = int(math.ceil(search_bbox.x1))
    y1 = int(math.ceil(search_bbox.y1))
    crop = array[y0:y1, x0:x1]
    if crop.size == 0:
        return hint_bbox
    smoothed = cv2.pyrMeanShiftFiltering(crop, sp=12, sr=18)
    gray = cv2.cvtColor(smoothed, cv2.COLOR_RGB2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    sobel_x = cv2.Sobel(blurred, cv2.CV_32F, 1, 0, ksize=3)
    sobel_y = cv2.Sobel(blurred, cv2.CV_32F, 0, 1, ksize=3)
    gradient = cv2.magnitude(sobel_x, sobel_y)
    threshold = max(float(np.percentile(gradient, max(70.0, config.local_refine_gradient_percentile - 8.0))), float(np.mean(gradient) + config.local_refine_threshold_bias * 0.7))
    canny = cv2.Canny(blurred, 42, 132)
    binary = np.zeros_like(gray, dtype=np.uint8)
    binary[gradient >= threshold] = 255
    binary = cv2.bitwise_or(binary, canny)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, np.ones((5, 5), dtype=np.uint8), iterations=2)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return snap_bbox_to_local_contour(array, merge_bboxes(seed_bbox, hint_bbox), config)
    best_bbox = merge_bboxes(seed_bbox, hint_bbox)
    best_score = -1.0
    seed_center = text_anchor.center
    for contour in contours:
        rx, ry, rw, rh = cv2.boundingRect(contour)
        candidate = BBox(x0 + rx, y0 + ry, x0 + rx + rw, y0 + ry + rh)
        if candidate.width < max(18.0, text_anchor.width * 1.35):
            continue
        if candidate.height < max(18.0, text_anchor.height * 1.55):
            continue
        score = 0.0
        if candidate.contains_point(seed_center):
            score += 2.5
        if bbox_contains(candidate, text_anchor.expand(3.0)):
            score += 2.0
        score += candidate.iou(hint_bbox) * 2.0
        expansion_ratio = min(candidate.area, max(hint_bbox.area, seed_bbox.area)) / max(candidate.area, 1.0)
        score += expansion_ratio
        if score > best_score:
            best_score = score
            best_bbox = candidate
    if best_score < 2.6:
        return snap_bbox_to_local_contour(array, merge_bboxes(seed_bbox, hint_bbox), config)
    return clamp_bbox(best_bbox, width=array.shape[1], height=array.shape[0])
