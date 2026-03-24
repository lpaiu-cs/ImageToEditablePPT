from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageDraw

from ..diagnostics import DiagnosticsRecorder
from ..schema import GuideField, MotifHypothesis, ObjectHypothesis


@dataclass(slots=True)
class MotifBuildResult:
    motifs: list[MotifHypothesis]


def build_motif_hypotheses(
    image: Image.Image,
    hypotheses: list[ObjectHypothesis],
    guide_field: GuideField,
    *,
    diagnostics: DiagnosticsRecorder | None = None,
    stage: str = "04_motifs",
) -> MotifBuildResult:
    recorder = diagnostics or DiagnosticsRecorder()
    motifs: list[MotifHypothesis] = []
    row_groups: dict[str, list[ObjectHypothesis]] = {}
    for hypothesis in hypotheses:
        if hypothesis.bbox is None or hypothesis.object_type != "container":
            continue
        key = f"{round(hypothesis.bbox.y0 / 24.0)}:{round(hypothesis.bbox.height / 24.0)}"
        row_groups.setdefault(key, []).append(hypothesis)
    next_index = 1
    for members in row_groups.values():
        if len(members) < 2:
            continue
        bbox = None
        xs = [member.bbox.x0 for member in members if member.bbox is not None]
        ys = [member.bbox.y0 for member in members if member.bbox is not None]
        x1s = [member.bbox.x1 for member in members if member.bbox is not None]
        y1s = [member.bbox.y1 for member in members if member.bbox is not None]
        if xs and ys and x1s and y1s:
            from ..ir import BBox

            bbox = BBox(min(xs), min(ys), max(x1s), max(y1s))
        motifs.append(
            MotifHypothesis(
                id=f"motif-{next_index:03d}",
                kind="motif",
                bbox=bbox,
                score_total=float(len(members)),
                score_terms={"member_count": float(len(members))},
                source_ids=[member.id for member in members],
                provenance={"hypothesis_ids": [member.id for member in members]},
                member_ids=[member.id for member in members],
            )
        )
        next_index += 1
    if recorder.enabled:
        recorder.summary(stage, {"motif_count": len(motifs)})
        recorder.items(stage, "motifs", motifs)
        recorder.overlay(stage, "overlay", draw_motif_overlay(image, motifs))
    return MotifBuildResult(motifs=motifs)


def draw_motif_overlay(
    image: Image.Image,
    motifs: list[MotifHypothesis],
) -> Image.Image:
    overlay = image.convert("RGB").copy()
    draw = ImageDraw.Draw(overlay)
    for motif in motifs:
        if motif.bbox is None:
            continue
        draw.rectangle((motif.bbox.x0, motif.bbox.y0, motif.bbox.x1, motif.bbox.y1), outline=(0, 191, 255), width=2)
    return overlay
