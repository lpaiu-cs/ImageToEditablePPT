from __future__ import annotations

from dataclasses import dataclass, replace
from difflib import SequenceMatcher

from PIL import Image, ImageDraw

from .config import PipelineConfig
from .diagnostics import DiagnosticsRecorder
from .ir import BBox
from .schema import ObjectHypothesis, OCRPhrase, RectCandidate
from .text import OCRNormalizationResult, normalize_ocr_text
from .vlm_parser import DiagramStructure, VLMNode


@dataclass(slots=True)
class ObjectStageResult:
    vlm_nodes: list[VLMNode]
    hypotheses: list[ObjectHypothesis]
    anchor_map: dict[str, OCRPhrase]
    candidate_rankings: dict[str, list[dict[str, object]]]
    schema_nodes: list[dict[str, object]]
    unmatched_vlm_node_ids: list[str]


def build_object_hypotheses(
    image: Image.Image,
    structure: DiagramStructure,
    ocr: OCRNormalizationResult,
    candidates: list[RectCandidate],
    config: PipelineConfig,
    *,
    diagnostics: DiagnosticsRecorder | None = None,
    stage: str = "03_objects",
) -> ObjectStageResult:
    recorder = diagnostics or DiagnosticsRecorder()
    anchored_nodes, anchor_map = anchor_nodes_to_ocr(structure.nodes, ocr.phrases, config)
    candidate_assignments, candidate_rankings = assign_geometry_candidates_to_nodes(
        anchored_nodes,
        anchor_map,
        candidates,
        ocr.phrases,
        config,
    )
    hypotheses: list[ObjectHypothesis] = []
    unmatched: list[str] = []
    schema_nodes = [schema_node_row(node, anchor_map.get(node.id)) for node in anchored_nodes]
    for node in anchored_nodes:
        candidate = candidate_assignments.get(node.id)
        anchor = anchor_map.get(node.id)
        if candidate is None:
            unmatched.append(node.id)
            continue
        score_terms = hypothesis_score_terms(node, anchor, candidate, ocr.phrases, config)
        hypotheses.append(
            ObjectHypothesis(
                id=f"object-hypothesis:{node.id}",
                kind=node.type,
                object_type=node_object_type(node.type),
                bbox=candidate.bbox,
                score_total=sum(score_terms.values()),
                score_terms=score_terms,
                source_ids=[candidate.id, node.id],
                provenance={
                    "candidate_ids": [candidate.id],
                    "vlm_ids": [node.id],
                    "ocr_phrase_ids": [] if anchor is None else [anchor.id],
                },
                assigned_text_ids=[] if anchor is None else [anchor.id],
                assigned_vlm_ids=[node.id],
                guide_ids=list(candidate.guide_ids),
                candidate_id=candidate.id,
            )
        )
    result = ObjectStageResult(
        vlm_nodes=anchored_nodes,
        hypotheses=hypotheses,
        anchor_map=anchor_map,
        candidate_rankings=candidate_rankings,
        schema_nodes=schema_nodes,
        unmatched_vlm_node_ids=unmatched,
    )
    if recorder.enabled:
        recorder.summary(
            stage,
            {
                "vlm_node_count": len(structure.nodes),
                "anchored_node_count": len(anchor_map),
                "hypothesis_count": len(hypotheses),
                "unmatched_vlm_node_count": len(unmatched),
            },
        )
        recorder.items(stage, "object_hypotheses", hypotheses)
        recorder.artifact(stage, "vlm_nodes", schema_nodes)
        recorder.artifact(
            stage,
            "anchor_assignments",
            {node_id: phrase.id for node_id, phrase in anchor_map.items()},
        )
        recorder.artifact(stage, "candidate_rankings", candidate_rankings)
        recorder.artifact(stage, "unmatched_vlm_nodes", unmatched)
        recorder.overlay(stage, "overlay", draw_object_overlay(image, anchored_nodes, hypotheses))
    return result


def anchor_nodes_to_ocr(
    nodes: list[VLMNode],
    phrases: list[OCRPhrase],
    config: PipelineConfig,
) -> tuple[list[VLMNode], dict[str, OCRPhrase]]:
    if not phrases:
        return list(nodes), {}
    assignments: dict[str, OCRPhrase] = {}
    used_indices: set[int] = set()
    ordered = sorted(nodes, key=lambda candidate: len(candidate.text or ""), reverse=True)
    for node in ordered:
        anchor_index = find_best_ocr_anchor(node, phrases, used_indices, config)
        if anchor_index is None:
            continue
        used_indices.add(anchor_index)
        assignments[node.id] = phrases[anchor_index]
    anchored = [
        replace(node, text=assignments[node.id].text) if node.id in assignments else node
        for node in nodes
    ]
    return anchored, assignments


def find_best_ocr_anchor(
    node: VLMNode,
    phrases: list[OCRPhrase],
    used_regions: set[int],
    config: PipelineConfig,
) -> int | None:
    target = normalize_ocr_text(node.text)
    if not target:
        return None
    best: tuple[float, int] | None = None
    for index, phrase in enumerate(phrases):
        if index in used_regions:
            continue
        candidate_text = phrase.normalized_text
        if not candidate_text:
            continue
        similarity = SequenceMatcher(None, target, candidate_text).ratio()
        if similarity < config.semantic_ocr_similarity:
            continue
        hint = ocr_hint_score(node.approx_bbox, phrase.bbox)
        score = similarity * (1.0 - config.semantic_ocr_hint_weight) + hint * config.semantic_ocr_hint_weight
        if best is None or score > best[0]:
            best = (score, index)
    return None if best is None else best[1]


def ocr_hint_score(hint_bbox: BBox, region_bbox: BBox | None) -> float:
    if region_bbox is None:
        return 0.0
    if hint_bbox.expand(max(20.0, min(hint_bbox.width, hint_bbox.height) * 0.35)).contains_point(region_bbox.center):
        return 1.0
    dx = hint_bbox.center.x - region_bbox.center.x
    dy = hint_bbox.center.y - region_bbox.center.y
    distance = (dx * dx + dy * dy) ** 0.5
    diagonal = max(1.0, (hint_bbox.width * hint_bbox.width + hint_bbox.height * hint_bbox.height) ** 0.5)
    return max(0.0, 1.0 - distance / (diagonal * 4.0))


def assign_geometry_candidates_to_nodes(
    nodes: list[VLMNode],
    anchor_map: dict[str, OCRPhrase],
    candidates: list[RectCandidate],
    phrases: list[OCRPhrase],
    config: PipelineConfig,
) -> tuple[dict[str, RectCandidate], dict[str, list[dict[str, object]]]]:
    assigned: dict[str, RectCandidate] = {}
    used_candidates: set[str] = set()
    rankings: dict[str, list[dict[str, object]]] = {}
    ordered_nodes = sorted(
        nodes,
        key=lambda node: (
            anchor_map[node.id].bbox.area if node.id in anchor_map and anchor_map[node.id].bbox is not None else node.approx_bbox.area,
            len(node.text or ""),
        ),
    )
    for node in ordered_nodes:
        ranked: list[tuple[float, RectCandidate]] = []
        for candidate in candidates:
            if candidate.id in used_candidates or candidate.bbox is None:
                continue
            score = candidate_score(node, anchor_map.get(node.id), candidate, phrases, config)
            if score is None:
                continue
            ranked.append((score, candidate))
        ranked.sort(key=lambda item: item[0], reverse=True)
        rankings[node.id] = [
            {"candidate_id": candidate.id, "score": score}
            for score, candidate in ranked[:3]
        ]
        if ranked and ranked[0][0] >= 1.35:
            assigned[node.id] = ranked[0][1]
            used_candidates.add(ranked[0][1].id)
    return assigned, rankings


def candidate_score(
    node: VLMNode,
    anchor: OCRPhrase | None,
    candidate: RectCandidate,
    phrases: list[OCRPhrase],
    config: PipelineConfig,
) -> float | None:
    if candidate.bbox is None:
        return None
    score = candidate.score_total * 0.8
    if anchor is not None and anchor.bbox is not None:
        if not candidate.bbox.expand(max(12.0, config.text_margin)).contains_point(anchor.bbox.center):
            return None
        score += 2.6
        score += candidate.bbox.iou(anchor.bbox.expand(config.text_margin * 1.5)) * 0.4
        margins = (
            anchor.bbox.x0 - candidate.bbox.x0,
            anchor.bbox.y0 - candidate.bbox.y0,
            candidate.bbox.x1 - anchor.bbox.x1,
            candidate.bbox.y1 - anchor.bbox.y1,
        )
        if min(margins) < 0:
            return None
        score += min(margins) / max(8.0, config.text_margin) * 0.08
    else:
        overlap = candidate.bbox.iou(node.approx_bbox)
        if overlap < 0.05:
            return None
        score += overlap * 1.2
    score += candidate.bbox.iou(node.approx_bbox) * 0.75
    anchor_area = anchor.bbox.area if anchor is not None and anchor.bbox is not None else max(1.0, node.approx_bbox.area * 0.2)
    area_ratio = candidate.bbox.area / max(1.0, anchor_area)
    score -= min(3.2, max(0.0, area_ratio - 1.0) * 0.06)
    score -= composite_box_penalty(candidate.bbox, anchor, phrases)
    return score


def composite_box_penalty(
    bbox: BBox,
    anchor: OCRPhrase | None,
    phrases: list[OCRPhrase],
) -> float:
    penalty = 0.0
    anchor_center = None if anchor is None or anchor.bbox is None else anchor.bbox.center
    extras = 0
    for phrase in phrases:
        if phrase.bbox is None:
            continue
        center = phrase.bbox.center
        if not bbox.contains_point(center):
            continue
        if anchor_center is not None and abs(center.x - anchor_center.x) < 6.0 and abs(center.y - anchor_center.y) < 6.0:
            continue
        extras += 1
    if extras > 0:
        penalty += extras * 0.85
    return penalty


def hypothesis_score_terms(
    node: VLMNode,
    anchor: OCRPhrase | None,
    candidate: RectCandidate,
    phrases: list[OCRPhrase],
    config: PipelineConfig,
) -> dict[str, float]:
    if candidate.bbox is None:
        return {"candidate_confidence": candidate.score_total}
    anchor_bonus = 0.0
    anchor_iou = 0.0
    padding_margin = 0.0
    if anchor is not None and anchor.bbox is not None:
        anchor_bonus = 2.6
        anchor_iou = candidate.bbox.iou(anchor.bbox.expand(config.text_margin * 1.5)) * 0.4
        margins = (
            anchor.bbox.x0 - candidate.bbox.x0,
            anchor.bbox.y0 - candidate.bbox.y0,
            candidate.bbox.x1 - anchor.bbox.x1,
            candidate.bbox.y1 - anchor.bbox.y1,
        )
        padding_margin = max(0.0, min(margins)) / max(8.0, config.text_margin) * 0.08
    node_overlap = candidate.bbox.iou(node.approx_bbox) * 0.75
    composite_penalty = composite_box_penalty(candidate.bbox, anchor, phrases)
    return {
        "candidate_confidence": candidate.score_total * 0.8,
        "anchor_bonus": anchor_bonus,
        "anchor_iou": anchor_iou,
        "padding_margin": padding_margin,
        "node_overlap": node_overlap,
        "composite_penalty": -composite_penalty,
    }


def node_object_type(node_type: str) -> str:
    return "textbox" if node_type == "text_only" else "container"


def schema_node_row(node: VLMNode, anchor: OCRPhrase | None) -> dict[str, object]:
    return {
        "id": node.id,
        "kind": node.type,
        "bbox": node.approx_bbox.to_dict(),
        "score_total": 1.0,
        "score_terms": {"anchored": 1.0 if anchor is not None else 0.0},
        "source_ids": [node.id],
        "assigned_text_ids": [] if anchor is None else [anchor.id],
        "assigned_vlm_ids": [node.id],
        "text": node.text,
        "object_type": node_object_type(node.type),
    }


def draw_object_overlay(
    image: Image.Image,
    nodes: list[VLMNode],
    hypotheses: list[ObjectHypothesis],
) -> Image.Image:
    overlay = image.convert("RGB").copy()
    draw = ImageDraw.Draw(overlay)
    for node in nodes:
        draw.rectangle(
            (node.approx_bbox.x0, node.approx_bbox.y0, node.approx_bbox.x1, node.approx_bbox.y1),
            outline=(255, 215, 0),
            width=1,
        )
    for hypothesis in hypotheses:
        if hypothesis.bbox is None:
            continue
        draw.rectangle(
            (hypothesis.bbox.x0, hypothesis.bbox.y0, hypothesis.bbox.x1, hypothesis.bbox.y1),
            outline=(50, 205, 50),
            width=2,
        )
    return overlay
