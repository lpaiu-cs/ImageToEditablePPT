from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageDraw

from .diagnostics import DiagnosticsRecorder
from .ir import BBox
from .schema import Guide, GuideField, RectCandidate, SizeCluster, SpacingCluster, validate_stage_entities


@dataclass(slots=True)
class GuideStageResult:
    guide_field: GuideField
    snapped_candidates: list[RectCandidate]
    snap_records: list[dict[str, object]]


def infer_guides(
    image: Image.Image,
    candidates: list[RectCandidate],
    *,
    tolerance: float,
    diagnostics: DiagnosticsRecorder | None = None,
    stage: str = "02_guides",
) -> GuideStageResult:
    recorder = diagnostics or DiagnosticsRecorder()
    if not candidates:
        empty = GuideField(id="guide-field", kind="guide_field", bbox=None, score_total=0.0)
        result = GuideStageResult(guide_field=empty, snapped_candidates=[], snap_records=[])
        if recorder.enabled:
            recorder.summary(stage, {"guide_count": 0, "snapped_candidate_count": 0})
            recorder.items(stage, "rect_candidates", [])
            recorder.artifact(stage, "snap_records", [])
        return result
    xs = [candidate.bbox.x0 for candidate in candidates if candidate.bbox is not None] + [
        candidate.bbox.x1 for candidate in candidates if candidate.bbox is not None
    ]
    ys = [candidate.bbox.y0 for candidate in candidates if candidate.bbox is not None] + [
        candidate.bbox.y1 for candidate in candidates if candidate.bbox is not None
    ]
    widths = [candidate.bbox.width for candidate in candidates if candidate.bbox is not None]
    heights = [candidate.bbox.height for candidate in candidates if candidate.bbox is not None]
    x_guides = build_guides("x", xs, tolerance=tolerance)
    y_guides = build_guides("y", ys, tolerance=tolerance)
    size_clusters = build_size_clusters("x", widths, tolerance=tolerance) + build_size_clusters("y", heights, tolerance=tolerance)
    spacing_clusters = build_spacing_clusters(candidates, tolerance=tolerance)
    guide_field = GuideField(
        id="guide-field",
        kind="guide_field",
        bbox=BBox(0.0, 0.0, float(image.size[0]), float(image.size[1])),
        score_total=float(len(x_guides) + len(y_guides)),
        score_terms={
            "x_guides": float(len(x_guides)),
            "y_guides": float(len(y_guides)),
            "size_clusters": float(len(size_clusters)),
            "spacing_clusters": float(len(spacing_clusters)),
        },
        guides=x_guides + y_guides,
        size_clusters=size_clusters,
        spacing_clusters=spacing_clusters,
    )
    snapped_candidates: list[RectCandidate] = []
    snap_records: list[dict[str, object]] = []
    for candidate in candidates:
        if candidate.bbox is None:
            snapped_candidates.append(candidate)
            continue
        snapped_bbox = BBox(
            snap_value(candidate.bbox.x0, [guide.position for guide in x_guides]),
            snap_value(candidate.bbox.y0, [guide.position for guide in y_guides]),
            snap_value(candidate.bbox.x1, [guide.position for guide in x_guides]),
            snap_value(candidate.bbox.y1, [guide.position for guide in y_guides]),
        )
        assigned_guides = [
            guide.id
            for guide in guide_field.guides
            if abs(guide.position - candidate.bbox.x0) <= tolerance
            or abs(guide.position - candidate.bbox.x1) <= tolerance
            or abs(guide.position - candidate.bbox.y0) <= tolerance
            or abs(guide.position - candidate.bbox.y1) <= tolerance
        ]
        snapped = RectCandidate(
            id=f"{candidate.id}:snapped",
            kind=candidate.kind,
            bbox=snapped_bbox,
            score_total=candidate.score_total,
            score_terms={
                **candidate.score_terms,
                "snap_dx0": abs(snapped_bbox.x0 - candidate.bbox.x0),
                "snap_dy0": abs(snapped_bbox.y0 - candidate.bbox.y0),
                "snap_dx1": abs(snapped_bbox.x1 - candidate.bbox.x1),
                "snap_dy1": abs(snapped_bbox.y1 - candidate.bbox.y1),
            },
            source_ids=[candidate.id, *candidate.source_ids],
            provenance={**candidate.provenance, "guide_ids": assigned_guides},
            guide_ids=assigned_guides,
            object_type=candidate.object_type,
            corner_radius=candidate.corner_radius,
        )
        snapped_candidates.append(snapped)
        snap_records.append(
            {
                "candidate_id": candidate.id,
                "snapped_id": snapped.id,
                "before_bbox": candidate.bbox.to_dict(),
                "after_bbox": snapped_bbox.to_dict(),
                "guide_ids": assigned_guides,
            }
        )
    result = GuideStageResult(
        guide_field=guide_field,
        snapped_candidates=snapped_candidates,
        snap_records=snap_records,
    )
    result.guide_field.guides = list(validate_stage_entities(stage, "guides", result.guide_field.guides))
    result.guide_field.size_clusters = list(validate_stage_entities(stage, "size_clusters", result.guide_field.size_clusters))
    result.guide_field.spacing_clusters = list(validate_stage_entities(stage, "spacing_clusters", result.guide_field.spacing_clusters))
    result.snapped_candidates = list(validate_stage_entities(stage, "rect_candidates", result.snapped_candidates, require_bbox=True))
    if recorder.enabled:
        recorder.summary(
            stage,
            {
                "guide_count": len(guide_field.guides),
                "size_cluster_count": len(size_clusters),
                "spacing_cluster_count": len(spacing_clusters),
                "snapped_candidate_count": len(snapped_candidates),
            },
        )
        recorder.items(stage, "guides", guide_field.guides)
        recorder.items(stage, "size_clusters", size_clusters)
        recorder.items(stage, "spacing_clusters", spacing_clusters)
        recorder.items(stage, "rect_candidates", snapped_candidates)
        recorder.artifact(stage, "snap_records", snap_records)
        recorder.overlay(stage, "overlay", draw_guides_overlay(image, guide_field, snapped_candidates))
    return result


def build_guides(axis: str, values: list[float], *, tolerance: float) -> list[Guide]:
    clusters = cluster_values(values, tolerance=tolerance)
    guides: list[Guide] = []
    for index, cluster in enumerate(clusters, start=1):
        position = sum(cluster) / max(1, len(cluster))
        guides.append(
            Guide(
                id=f"guide-{axis}-{index:03d}",
                kind="guide",
                bbox=None,
                score_total=float(len(cluster)),
                score_terms={"support": float(len(cluster))},
                source_ids=[],
                axis=axis,
                position=position,
                member_ids=[f"{axis}:{value:.2f}" for value in cluster],
            )
        )
    return guides


def build_size_clusters(axis: str, values: list[float], *, tolerance: float) -> list[SizeCluster]:
    clusters = cluster_values(values, tolerance=tolerance)
    return [
        SizeCluster(
            id=f"size-{axis}-{index:03d}",
            kind="size_cluster",
            bbox=None,
            score_total=float(len(cluster)),
            score_terms={"support": float(len(cluster))},
            source_ids=[],
            axis=axis,
            value=sum(cluster) / max(1, len(cluster)),
            member_ids=[f"{axis}:{value:.2f}" for value in cluster],
        )
        for index, cluster in enumerate(clusters, start=1)
    ]


def build_spacing_clusters(candidates: list[RectCandidate], *, tolerance: float) -> list[SpacingCluster]:
    xs = sorted(candidate.bbox.center.x for candidate in candidates if candidate.bbox is not None)
    ys = sorted(candidate.bbox.center.y for candidate in candidates if candidate.bbox is not None)
    x_spacings = [second - first for first, second in zip(xs[:-1], xs[1:], strict=True)]
    y_spacings = [second - first for first, second in zip(ys[:-1], ys[1:], strict=True)]
    clusters = [
        *[
            SpacingCluster(
                id=f"spacing-x-{index:03d}",
                kind="spacing_cluster",
                bbox=None,
                score_total=float(len(cluster)),
                score_terms={"support": float(len(cluster))},
                source_ids=[],
                axis="x",
                value=sum(cluster) / max(1, len(cluster)),
                member_ids=[f"x:{value:.2f}" for value in cluster],
            )
            for index, cluster in enumerate(cluster_values(x_spacings, tolerance=tolerance), start=1)
        ],
        *[
            SpacingCluster(
                id=f"spacing-y-{index:03d}",
                kind="spacing_cluster",
                bbox=None,
                score_total=float(len(cluster)),
                score_terms={"support": float(len(cluster))},
                source_ids=[],
                axis="y",
                value=sum(cluster) / max(1, len(cluster)),
                member_ids=[f"y:{value:.2f}" for value in cluster],
            )
            for index, cluster in enumerate(cluster_values(y_spacings, tolerance=tolerance), start=1)
        ],
    ]
    return clusters


def cluster_values(values: list[float], *, tolerance: float) -> list[list[float]]:
    if not values:
        return []
    ordered = sorted(values)
    clusters: list[list[float]] = [[ordered[0]]]
    for value in ordered[1:]:
        if abs(value - clusters[-1][-1]) <= tolerance:
            clusters[-1].append(value)
        else:
            clusters.append([value])
    return clusters


def snap_value(value: float, guides: list[float]) -> float:
    if not guides:
        return value
    return min(guides, key=lambda guide: abs(guide - value))


def draw_guides_overlay(
    image: Image.Image,
    guide_field: GuideField,
    candidates: list[RectCandidate],
) -> Image.Image:
    overlay = image.convert("RGB").copy()
    draw = ImageDraw.Draw(overlay)
    for guide in guide_field.guides:
        if guide.axis == "x":
            draw.line((guide.position, 0, guide.position, image.size[1]), fill=(160, 32, 240), width=1)
        else:
            draw.line((0, guide.position, image.size[0], guide.position), fill=(160, 32, 240), width=1)
    for candidate in candidates:
        if candidate.bbox is None:
            continue
        draw.rectangle(
            (candidate.bbox.x0, candidate.bbox.y0, candidate.bbox.x1, candidate.bbox.y1),
            outline=(34, 139, 34),
            width=2,
        )
    return overlay
