from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageDraw

from .config import PipelineConfig
from .diagnostics import DiagnosticsRecorder
from .schema import ObjectHypothesis, SuppressionReason


@dataclass(slots=True)
class SelectionResult:
    selected: list[ObjectHypothesis]
    suppressed: list[ObjectHypothesis]
    conflict_graph: list[dict[str, object]]


def select_authoring_objects(
    image: Image.Image,
    hypotheses: list[ObjectHypothesis],
    config: PipelineConfig,
    *,
    diagnostics: DiagnosticsRecorder | None = None,
    stage: str = "05_selection",
) -> SelectionResult:
    recorder = diagnostics or DiagnosticsRecorder()
    selected: list[ObjectHypothesis] = []
    suppressed: list[ObjectHypothesis] = []
    conflict_graph: list[dict[str, object]] = []
    for hypothesis in sorted(hypotheses, key=lambda item: item.score_total, reverse=True):
        conflict = first_conflict(hypothesis, selected)
        if conflict is None:
            selected.append(hypothesis)
            continue
        conflict_graph.append({"kept": conflict.id, "dropped": hypothesis.id, "reason": SuppressionReason.DUPLICATE_LOWER_SCORE.value})
        suppressed.append(
            ObjectHypothesis(
                id=hypothesis.id,
                kind=hypothesis.kind,
                bbox=hypothesis.bbox,
                score_total=hypothesis.score_total,
                score_terms=hypothesis.score_terms,
                source_ids=hypothesis.source_ids,
                provenance=hypothesis.provenance,
                parent_ids=hypothesis.parent_ids,
                guide_ids=hypothesis.guide_ids,
                assigned_text_ids=hypothesis.assigned_text_ids,
                assigned_vlm_ids=hypothesis.assigned_vlm_ids,
                object_type=hypothesis.object_type,
                candidate_id=hypothesis.candidate_id,
                fallback=hypothesis.fallback,
                suppression_reason=SuppressionReason.DUPLICATE_LOWER_SCORE,
                drop_reason=hypothesis.drop_reason,
            )
        )
    result = SelectionResult(selected=selected, suppressed=suppressed, conflict_graph=conflict_graph)
    if recorder.enabled:
        recorder.summary(
            stage,
            {
                "selected_count": len(selected),
                "suppressed_count": len(suppressed),
                "conflict_count": len(conflict_graph),
            },
        )
        recorder.items(stage, "selected_hypotheses", selected)
        recorder.items(stage, "suppressed_hypotheses", suppressed)
        recorder.artifact(stage, "conflict_graph", conflict_graph)
        recorder.overlay(stage, "overlay", draw_selection_overlay(image, selected, suppressed))
    return result


def first_conflict(
    candidate: ObjectHypothesis,
    selected: list[ObjectHypothesis],
) -> ObjectHypothesis | None:
    for prior in selected:
        if candidate.candidate_id and candidate.candidate_id == prior.candidate_id:
            return prior
        if candidate.assigned_vlm_ids and prior.assigned_vlm_ids and candidate.assigned_vlm_ids == prior.assigned_vlm_ids:
            return prior
        if candidate.bbox is not None and prior.bbox is not None and candidate.bbox.iou(prior.bbox) >= 0.82:
            return prior
    return None


def draw_selection_overlay(
    image: Image.Image,
    selected: list[ObjectHypothesis],
    suppressed: list[ObjectHypothesis],
) -> Image.Image:
    overlay = image.convert("RGB").copy()
    draw = ImageDraw.Draw(overlay)
    for hypothesis in suppressed:
        if hypothesis.bbox is None:
            continue
        draw.rectangle((hypothesis.bbox.x0, hypothesis.bbox.y0, hypothesis.bbox.x1, hypothesis.bbox.y1), outline=(220, 20, 60), width=1)
    for hypothesis in selected:
        if hypothesis.bbox is None:
            continue
        draw.rectangle((hypothesis.bbox.x0, hypothesis.bbox.y0, hypothesis.bbox.x1, hypothesis.bbox.y1), outline=(34, 139, 34), width=2)
    return overlay
