from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageDraw

from ..config import PipelineConfig
from ..diagnostics import DiagnosticsRecorder
from ..ir import BBox
from ..schema import GuideField, MotifHypothesis, ObjectHypothesis, validate_stage_entities


@dataclass(slots=True)
class MotifBuildResult:
    motifs: list[MotifHypothesis]
    effects: list[dict[str, object]]
    rejected: list[dict[str, object]]
    summary: dict[str, dict[str, int]]


def build_motif_hypotheses(
    image: Image.Image,
    hypotheses: list[ObjectHypothesis],
    guide_field: GuideField,
    config: PipelineConfig,
    *,
    diagnostics: DiagnosticsRecorder | None = None,
    stage: str = "04_motifs",
) -> MotifBuildResult:
    recorder = diagnostics or DiagnosticsRecorder()
    if not config.enable_motifs:
        result = MotifBuildResult(
            motifs=[],
            effects=[],
            rejected=[],
            summary={
                "titled_panel": {"proposed": 0, "accepted": 0, "rejected": 0},
                "repeated_cards": {"proposed": 0, "accepted": 0, "rejected": 0},
            },
        )
        if recorder.enabled:
            recorder.summary(stage, {"motif_count": 0, "builder_count": 2, "disabled": True})
            recorder.artifact(stage, "motif_summary", result.summary)
        return result

    titled_panel_motifs, titled_panel_rejections = build_titled_panel_motifs(hypotheses, config)
    repeated_card_motifs, repeated_card_rejections = build_repeated_card_motifs(hypotheses, guide_field, config)
    motifs = dedupe_motifs(titled_panel_motifs + repeated_card_motifs)
    motifs = list(validate_stage_entities(stage, "motifs", motifs))
    effects = [
        {
            "motif_id": motif.id,
            "motif_kind": motif.kind,
            "promoted_member_ids": list(motif.member_ids),
            "absorbed_member_ids": list(motif.member_ids[1:] if len(motif.member_ids) > 1 else []),
            "suppressed_member_ids": [],
        }
        for motif in motifs
    ]
    rejected = titled_panel_rejections + repeated_card_rejections
    summary = {
        "titled_panel": {
            "proposed": len(titled_panel_motifs) + len(titled_panel_rejections),
            "accepted": len(titled_panel_motifs),
            "rejected": len(titled_panel_rejections),
        },
        "repeated_cards": {
            "proposed": len(repeated_card_motifs) + len(repeated_card_rejections),
            "accepted": len(repeated_card_motifs),
            "rejected": len(repeated_card_rejections),
        },
    }
    result = MotifBuildResult(motifs=motifs, effects=effects, rejected=rejected, summary=summary)
    if recorder.enabled:
        recorder.summary(stage, {"motif_count": len(motifs), "builder_count": 2, "rejected_count": len(rejected)})
        recorder.items(stage, "motifs", motifs)
        recorder.artifact(stage, "effects", effects)
        recorder.artifact(stage, "rejected_motifs", rejected)
        recorder.artifact(stage, "motif_summary", summary)
        recorder.overlay(stage, "overlay", draw_motif_overlay(image, motifs))
    return result


def build_titled_panel_motifs(
    hypotheses: list[ObjectHypothesis],
    config: PipelineConfig,
) -> tuple[list[MotifHypothesis], list[dict[str, object]]]:
    if not config.enable_titled_panel_motif:
        return [], [{"motif_kind": "titled_panel", "reason": "family_disabled", "member_ids": []}]
    containers = [hypothesis for hypothesis in hypotheses if hypothesis.object_type == "container" and hypothesis.bbox is not None]
    textboxes = [hypothesis for hypothesis in hypotheses if hypothesis.object_type == "textbox" and hypothesis.bbox is not None]
    motifs: list[MotifHypothesis] = []
    rejections: list[dict[str, object]] = []
    next_index = 1
    for panel in containers:
        child_blocks = [
            candidate
            for candidate in containers
            if candidate.id != panel.id
            and candidate.bbox is not None
            and contains(panel.bbox, candidate.bbox)
            and candidate.bbox.area <= panel.bbox.area * 0.7
        ]
        if len(child_blocks) < config.motif_titled_panel_min_children:
            rejections.append(
                {
                    "motif_kind": "titled_panel",
                    "reason": "insufficient_children",
                    "member_ids": [panel.id, *[child.id for child in child_blocks]],
                    "panel_id": panel.id,
                }
            )
            continue
        title, title_score = find_panel_title(panel, textboxes)
        if title is None:
            rejections.append(
                {
                    "motif_kind": "titled_panel",
                    "reason": "missing_title",
                    "member_ids": [panel.id, *[child.id for child in child_blocks]],
                    "panel_id": panel.id,
                }
            )
            continue
        if title_score < config.motif_titled_panel_min_title_score:
            rejections.append(
                {
                    "motif_kind": "titled_panel",
                    "reason": "weak_title_alignment",
                    "member_ids": [panel.id, title.id, *[child.id for child in child_blocks]],
                    "panel_id": panel.id,
                    "title_id": title.id,
                    "title_score": round(title_score, 4),
                }
            )
            continue
        member_ids = [panel.id, title.id, *[child.id for child in child_blocks]]
        motifs.append(
            MotifHypothesis(
                id=f"motif-titled-panel-{next_index:03d}",
                kind="titled_panel",
                bbox=panel.bbox,
                score_total=4.0 + len(child_blocks) + title_score,
                score_terms={
                    "has_title": 2.0,
                    "title_alignment": title_score,
                    "child_count": float(len(child_blocks)),
                    "containment": 1.0,
                },
                source_ids=member_ids,
                provenance={"builder": ["titled_panel"], "panel_id": [panel.id], "title_id": [title.id], "child_ids": [child.id for child in child_blocks]},
                member_ids=member_ids,
            )
        )
        next_index += 1
    return motifs, rejections


def build_repeated_card_motifs(
    hypotheses: list[ObjectHypothesis],
    guide_field: GuideField,
    config: PipelineConfig,
) -> tuple[list[MotifHypothesis], list[dict[str, object]]]:
    if not config.enable_repeated_cards_motif:
        return [], [{"motif_kind": "repeated_cards", "reason": "family_disabled", "member_ids": []}]
    containers = [hypothesis for hypothesis in hypotheses if hypothesis.object_type == "container" and hypothesis.bbox is not None]
    groups: dict[str, list[ObjectHypothesis]] = {}
    for hypothesis in containers:
        key = f"{round(hypothesis.bbox.width / 24.0)}:{round(hypothesis.bbox.height / 24.0)}:{round(hypothesis.bbox.y0 / 24.0)}"
        groups.setdefault(key, []).append(hypothesis)
    motifs: list[MotifHypothesis] = []
    rejections: list[dict[str, object]] = []
    next_index = 1
    for members in groups.values():
        ordered = sorted(members, key=lambda hypothesis: hypothesis.bbox.x0)
        member_ids = [member.id for member in ordered]
        if len(ordered) < config.motif_repeated_cards_min_members:
            rejections.append({"motif_kind": "repeated_cards", "reason": "insufficient_members", "member_ids": member_ids})
            continue
        width_values = [member.bbox.width for member in ordered]
        height_values = [member.bbox.height for member in ordered]
        width_delta_ratio = spread_ratio(width_values)
        height_delta_ratio = spread_ratio(height_values)
        if max(width_delta_ratio, height_delta_ratio) > config.motif_repeated_cards_max_size_delta_ratio:
            rejections.append(
                {
                    "motif_kind": "repeated_cards",
                    "reason": "weak_size_consistency",
                    "member_ids": member_ids,
                    "width_delta_ratio": round(width_delta_ratio, 4),
                    "height_delta_ratio": round(height_delta_ratio, 4),
                }
            )
            continue
        spacings = [
            ordered[index + 1].bbox.x0 - ordered[index].bbox.x1
            for index in range(len(ordered) - 1)
        ]
        spacing_delta = max(spacings) - min(spacings) if spacings else 0.0
        if spacings and spacing_delta > config.motif_repeated_cards_max_spacing_delta:
            rejections.append(
                {
                    "motif_kind": "repeated_cards",
                    "reason": "weak_spacing_consistency",
                    "member_ids": member_ids,
                    "spacing_delta": round(spacing_delta, 4),
                }
            )
            continue
        shared_guides = shared_guide_count(ordered)
        if shared_guides < config.motif_repeated_cards_min_shared_guides:
            rejections.append(
                {
                    "motif_kind": "repeated_cards",
                    "reason": "insufficient_shared_guides",
                    "member_ids": member_ids,
                    "shared_guides": int(shared_guides),
                }
            )
            continue
        bbox = union_bbox([member.bbox for member in ordered if member.bbox is not None])
        motifs.append(
            MotifHypothesis(
                id=f"motif-repeated-cards-{next_index:03d}",
                kind="repeated_cards",
                bbox=bbox,
                score_total=3.0 + len(ordered),
                score_terms={
                    "member_count": float(len(ordered)),
                    "spacing_consistency": 1.0 if spacings else 0.5,
                    "shared_guides": shared_guides,
                    "size_consistency": 1.0 - max(width_delta_ratio, height_delta_ratio),
                },
                source_ids=member_ids,
                provenance={"builder": ["repeated_cards"], "member_ids": member_ids},
                member_ids=member_ids,
            )
        )
        next_index += 1
    return motifs, rejections


def find_panel_title(
    panel: ObjectHypothesis,
    textboxes: list[ObjectHypothesis],
) -> tuple[ObjectHypothesis | None, float]:
    best = None
    best_score = -1.0
    for textbox in textboxes:
        if textbox.bbox is None or panel.bbox is None:
            continue
        if textbox.bbox.center.x < panel.bbox.x0 - 8.0 or textbox.bbox.center.x > panel.bbox.x1 + 8.0:
            continue
        if textbox.bbox.y0 > panel.bbox.y0 + panel.bbox.height * 0.28:
            continue
        vertical_distance = abs(textbox.bbox.center.y - max(panel.bbox.y0, textbox.bbox.center.y))
        score = 1.0 - min(1.0, vertical_distance / max(12.0, panel.bbox.height * 0.18))
        if textbox.bbox.center.y <= panel.bbox.center.y:
            score += 0.5
        if score > best_score:
            best = textbox
            best_score = score
    return best, max(0.0, best_score)


def dedupe_motifs(motifs: list[MotifHypothesis]) -> list[MotifHypothesis]:
    deduped: list[MotifHypothesis] = []
    for motif in motifs:
        if any(set(motif.member_ids) == set(other.member_ids) and motif.kind == other.kind for other in deduped):
            continue
        deduped.append(motif)
    return deduped


def shared_guide_count(members: list[ObjectHypothesis]) -> float:
    if not members:
        return 0.0
    shared = set(members[0].guide_ids)
    for member in members[1:]:
        shared &= set(member.guide_ids)
    return float(len(shared))


def spread_ratio(values: list[float]) -> float:
    if not values:
        return 0.0
    maximum = max(values)
    minimum = min(values)
    return 0.0 if maximum <= 0.0 else (maximum - minimum) / maximum


def union_bbox(boxes: list[BBox]) -> BBox | None:
    if not boxes:
        return None
    return BBox(
        min(box.x0 for box in boxes),
        min(box.y0 for box in boxes),
        max(box.x1 for box in boxes),
        max(box.y1 for box in boxes),
    )


def contains(outer: BBox, inner: BBox) -> bool:
    return outer.x0 <= inner.x0 and outer.y0 <= inner.y0 and outer.x1 >= inner.x1 and outer.y1 >= inner.y1


def draw_motif_overlay(
    image: Image.Image,
    motifs: list[MotifHypothesis],
) -> Image.Image:
    overlay = image.convert("RGB").copy()
    draw = ImageDraw.Draw(overlay)
    palette = {
        "titled_panel": (0, 191, 255),
        "repeated_cards": (255, 99, 71),
    }
    for motif in motifs:
        if motif.bbox is None:
            continue
        draw.rectangle(
            (motif.bbox.x0, motif.bbox.y0, motif.bbox.x1, motif.bbox.y1),
            outline=palette.get(motif.kind, (0, 191, 255)),
            width=2,
        )
    return overlay
