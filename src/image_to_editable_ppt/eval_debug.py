from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Iterable

from .ir import BBox
from .schema import (
    ConnectorCandidate,
    EmissionRecord,
    FailureTag,
    FallbackRegion,
    LinePrimitive,
    MotifHypothesis,
    ObjectHypothesis,
    RectCandidate,
    RegionPrimitive,
    StageEntity,
    as_serializable,
)
from .source_attribution import SourceBucket, classify_source_bucket


@dataclass(slots=True, frozen=True)
class EvalItem:
    id: str
    kind: str
    bbox: BBox | None
    source_ids: tuple[str, ...] = ()
    attachment_ids: tuple[str, ...] = ()
    parent_id: str | None = None
    score_total: float = 0.0
    source_bucket: str = SourceBucket.OTHER.value
    evaluable: bool = True


@dataclass(slots=True, frozen=True)
class GroundTruthAnnotation:
    version: int
    path: Path
    objects: tuple[EvalItem, ...]


@dataclass(slots=True, frozen=True)
class MatchResult:
    gt_id: str
    artifact_id: str
    similarity: float
    source_bucket: str


@dataclass(slots=True, frozen=True)
class BestCandidate:
    item: EvalItem | None
    similarity: float
    passes: bool


def discover_ground_truth(input_path: str | Path) -> GroundTruthAnnotation | None:
    image_path = Path(input_path)
    candidates = [
        image_path.with_name(f"{image_path.stem}.gt.json"),
        image_path.with_suffix(f"{image_path.suffix}.gt.json"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return load_ground_truth(candidate)
    return None


def load_ground_truth(path: str | Path) -> GroundTruthAnnotation:
    gt_path = Path(path)
    payload = json.loads(gt_path.read_text(encoding="utf-8"))
    objects_payload = payload.get("objects")
    if not isinstance(objects_payload, list):
        raise ValueError("ground truth annotation must contain an 'objects' list")
    objects = tuple(parse_eval_item(item) for item in objects_payload)
    version = int(payload.get("version", 1))
    return GroundTruthAnnotation(version=version, path=gt_path, objects=objects)


def parse_eval_item(payload: dict[str, object]) -> EvalItem:
    bbox_payload = payload.get("bbox")
    if isinstance(bbox_payload, list) and len(bbox_payload) == 4:
        bbox = BBox(*(float(value) for value in bbox_payload))
    elif isinstance(bbox_payload, dict):
        bbox = BBox(
            float(bbox_payload["x0"]),
            float(bbox_payload["y0"]),
            float(bbox_payload["x1"]),
            float(bbox_payload["y1"]),
        )
    else:
        bbox = None
    source_ids = tuple(str(item) for item in payload.get("source_ids", []) or [])
    return EvalItem(
        id=str(payload.get("id", "")).strip(),
        kind=str(payload.get("kind") or payload.get("object_type") or "").strip(),
        bbox=bbox,
        source_ids=source_ids,
        attachment_ids=tuple(str(item) for item in (payload.get("attachment_ids") or payload.get("attachments") or []) or []),
        parent_id=None if payload.get("parent_id") in {None, ""} else str(payload.get("parent_id")),
        score_total=float(payload.get("score_total", 0.0) or 0.0),
        source_bucket=classify_source_bucket(source_ids).value,
    )


def oracle_upper_bound_by_stage(
    ground_truth: Iterable[EvalItem],
    stage_artifacts: dict[str, Iterable[EvalItem]],
) -> dict[str, object]:
    gt_items = list(ground_truth)
    output: dict[str, object] = {}
    for stage, artifacts in stage_artifacts.items():
        applicable_gt = [gt for gt in gt_items if stage_supports_kind(stage, gt.kind)]
        rows = [artifact for artifact in artifacts if artifact.evaluable]
        matches = unique_stage_matches(stage, applicable_gt, rows)
        by_gt = {match.gt_id: match for match in matches}
        recoverable_by_source_bucket: Counter[str] = Counter(match.source_bucket for match in matches)
        output[stage] = {
            "status": "ok",
            "ground_truth_count": len(applicable_gt),
            "artifact_count": len(rows),
            "recoverable_count": len(matches),
            "recoverable_ratio": len(matches) / max(1, len(applicable_gt)),
            "recoverable_by_source_bucket": {
                bucket.value: int(recoverable_by_source_bucket.get(bucket.value, 0))
                for bucket in SourceBucket
            },
            "matches": [
                {
                    "gt_id": gt.id,
                    "artifact_id": None if gt.id not in by_gt else by_gt[gt.id].artifact_id,
                    "similarity": 0.0 if gt.id not in by_gt else by_gt[gt.id].similarity,
                    "source_bucket": None if gt.id not in by_gt else by_gt[gt.id].source_bucket,
                }
                for gt in applicable_gt
            ],
        }
    return output


def failure_taxonomy(
    ground_truth: Iterable[EvalItem],
    predictions: Iterable[EvalItem],
) -> dict[str, object]:
    gt_items = list(ground_truth)
    pred_items = [prediction for prediction in predictions if prediction.evaluable]
    matches = unique_stage_matches("07_emit", gt_items, pred_items, require_attachment=True)
    matched_gt_ids = {match.gt_id for match in matches}
    matched_prediction_ids = {match.artifact_id for match in matches}
    gt_rows = []
    for gt in gt_items:
        if gt.id in matched_gt_ids:
            continue
        best = best_contextual_match(gt, pred_items)
        gt_rows.append(
            {
                "gt_id": gt.id,
                "tag": classify_gt_failure(gt, gt_items, pred_items, best).value,
                "best_prediction_id": None if best.item is None else best.item.id,
                "best_similarity": best.similarity,
            }
        )
    pred_rows = []
    for prediction in pred_items:
        if prediction.id in matched_prediction_ids:
            continue
        best = best_contextual_match(prediction, gt_items)
        pred_rows.append(
            {
                "prediction_id": prediction.id,
                "tag": classify_prediction_failure(prediction, gt_items, pred_items, best).value,
                "best_gt_id": None if best.item is None else best.item.id,
                "best_similarity": best.similarity,
                "source_bucket": prediction.source_bucket,
            }
        )
    return {
        "status": "ok",
        "ground_truth": gt_rows,
        "predictions": pred_rows,
        "matched_count": len(matches),
    }


def attrition_by_stage(
    ground_truth: Iterable[EvalItem],
    stage_artifacts: dict[str, Iterable[EvalItem]],
) -> dict[str, object]:
    stage_names = list(stage_artifacts.keys())
    gt_items = list(ground_truth)
    stage_presence: dict[str, dict[str, MatchResult]] = {}
    for stage, items in stage_artifacts.items():
        applicable_gt = [gt for gt in gt_items if stage_supports_kind(stage, gt.kind)]
        matches = unique_stage_matches(stage, applicable_gt, [item for item in items if item.evaluable])
        stage_presence[stage] = {match.gt_id: match for match in matches}
    output = {"status": "ok", "ground_truth": []}
    for gt in gt_items:
        presence = {
            stage: (gt.id in stage_presence[stage]) if stage_supports_kind(stage, gt.kind) else None
            for stage in stage_names
        }
        applicable = {stage: stage_supports_kind(stage, gt.kind) for stage in stage_names}
        matched_artifact_ids = {
            stage: stage_presence[stage][gt.id].artifact_id
            for stage in stage_names
            if gt.id in stage_presence[stage]
        }
        lost_at = None
        seen = False
        for stage in stage_names:
            if not applicable[stage]:
                continue
            if presence[stage]:
                seen = True
                continue
            if seen:
                lost_at = stage
                break
        output["ground_truth"].append(
            {
                "gt_id": gt.id,
                "presence": presence,
                "applicable": applicable,
                "matched_artifact_ids": matched_artifact_ids,
                "lost_at": lost_at,
            }
        )
    return output


def geometry_audit(
    ground_truth: Iterable[EvalItem],
    stage_artifacts: dict[str, Iterable[EvalItem]],
) -> dict[str, object]:
    gt_items = list(ground_truth)
    raw_items = [item for item in stage_artifacts.get("01_geometry_raw", []) if item.evaluable]
    snapped_items = [item for item in stage_artifacts.get("02_guides", []) if item.evaluable]
    object_items = [item for item in stage_artifacts.get("03_objects", []) if item.evaluable]
    selected_items = [item for item in stage_artifacts.get("05_selection", []) if item.evaluable]
    emit_items = [item for item in stage_artifacts.get("07_emit", []) if item.evaluable]

    selected_matches = {match.gt_id: match for match in unique_stage_matches("05_selection", gt_items, selected_items)}
    emit_matches = {match.gt_id: match for match in unique_stage_matches("07_emit", gt_items, emit_items, require_attachment=True)}

    rows = []
    for gt in gt_items:
        raw_best = best_stage_candidate("01_geometry_raw", gt, raw_items)
        snapped_best = best_stage_candidate("02_guides", gt, snapped_items)
        object_best = best_stage_candidate("03_objects", gt, object_items)
        selected_best = best_stage_candidate("05_selection", gt, selected_items)
        emit_best = best_stage_candidate("07_emit", gt, emit_items, require_attachment=True)

        fallback_rescued = (
            (object_best.item is not None and object_best.passes and object_best.item.source_bucket in {SourceBucket.FALLBACK_ONLY.value, SourceBucket.MIXED_GEOMETRY_FALLBACK.value} and not raw_best.passes)
            or (gt.id in emit_matches and emit_matches[gt.id].source_bucket in {SourceBucket.FALLBACK_ONLY.value, SourceBucket.MIXED_GEOMETRY_FALLBACK.value})
        )
        status = audit_status(
            raw_best=raw_best,
            snapped_best=snapped_best,
            object_best=object_best,
            gt_id=gt.id,
            selected_matches=selected_matches,
            emit_matches=emit_matches,
            fallback_rescued=fallback_rescued,
        )
        rows.append(
            {
                "gt_id": gt.id,
                "kind": normalize_eval_kind(gt.kind),
                "raw_geometry": audit_row_for_candidate(raw_best),
                "guide_snapped": audit_row_for_candidate(snapped_best),
                "object_hypothesis": audit_row_for_candidate(object_best),
                "selected_hypothesis": audit_row_for_candidate(selected_best, matched=gt.id in selected_matches),
                "emit_record": audit_row_for_candidate(emit_best, matched=gt.id in emit_matches),
                "fallback_rescued": fallback_rescued,
                "status": status,
            }
        )
    return {"status": "ok", "ground_truth": rows}


def unavailable_eval_payload(reason: str) -> dict[str, object]:
    return {
        "status": "unavailable",
        "gt_available": False,
        "reason": reason,
    }


def write_eval_debug_artifacts(
    output_dir: str | Path,
    ground_truth: GroundTruthAnnotation | Iterable[EvalItem] | None,
    stage_artifacts: dict[str, Iterable[EvalItem]],
) -> dict[str, object]:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    if ground_truth is None:
        unavailable = unavailable_eval_payload("ground_truth_annotations_missing")
        for name in ("oracle_by_stage.json", "failure_taxonomy.json", "attrition_by_stage.json", "geometry_audit.json"):
            (target / name).write_text(json.dumps(unavailable, indent=2), encoding="utf-8")
        return unavailable
    gt_items = list(ground_truth.objects if isinstance(ground_truth, GroundTruthAnnotation) else ground_truth)
    oracle = {
        "status": "ok",
        "gt_available": True,
        "ground_truth_count": len(gt_items),
        "stages": oracle_upper_bound_by_stage(gt_items, stage_artifacts),
    }
    failure = {
        "status": "ok",
        "gt_available": True,
        "ground_truth_count": len(gt_items),
        **failure_taxonomy(gt_items, stage_artifacts.get("07_emit", [])),
    }
    attrition = {
        "status": "ok",
        "gt_available": True,
        "ground_truth_count": len(gt_items),
        **attrition_by_stage(gt_items, stage_artifacts),
    }
    audit = {
        "status": "ok",
        "gt_available": True,
        "ground_truth_count": len(gt_items),
        **geometry_audit(gt_items, stage_artifacts),
    }
    (target / "oracle_by_stage.json").write_text(json.dumps(as_serializable(oracle), indent=2), encoding="utf-8")
    (target / "failure_taxonomy.json").write_text(json.dumps(as_serializable(failure), indent=2), encoding="utf-8")
    (target / "attrition_by_stage.json").write_text(json.dumps(as_serializable(attrition), indent=2), encoding="utf-8")
    (target / "geometry_audit.json").write_text(json.dumps(as_serializable(audit), indent=2), encoding="utf-8")
    return {"oracle": oracle, "failure": failure, "attrition": attrition, "geometry_audit": audit}


def stage_items_from_entities(items: Iterable[StageEntity]) -> list[EvalItem]:
    rows: list[EvalItem] = []
    for item in items:
        attachment_ids = ()
        parent_id = None
        if isinstance(item, EmissionRecord):
            attachment_ids = tuple(item.graph_node_ids)
        elif isinstance(item, ObjectHypothesis):
            attachment_ids = tuple(item.parent_ids)
            parent_id = item.parent_ids[0] if item.parent_ids else None
        rows.append(
            EvalItem(
                id=item.id,
                kind=canonical_eval_kind(item),
                bbox=item.bbox,
                source_ids=tuple(dict.fromkeys([item.id, *item.source_ids])),
                attachment_ids=attachment_ids,
                parent_id=parent_id,
                score_total=float(item.score_total),
                source_bucket=classify_source_bucket([item.id, *item.source_ids]).value,
            )
        )
    return rows


def canonical_eval_kind(item: StageEntity) -> str:
    if isinstance(item, (RectCandidate, RegionPrimitive)):
        return "container"
    if isinstance(item, (ConnectorCandidate, LinePrimitive)):
        return "connector"
    if isinstance(item, (ObjectHypothesis, EmissionRecord, FallbackRegion, MotifHypothesis)):
        object_type = getattr(item, "object_type", "")
        return normalize_eval_kind(object_type or item.kind)
    return normalize_eval_kind(item.kind)


def unique_stage_matches(
    stage: str,
    ground_truth: list[EvalItem],
    artifacts: list[EvalItem],
    *,
    require_attachment: bool = False,
) -> list[MatchResult]:
    candidates: list[tuple[float, str, str, str, str, EvalItem, EvalItem]] = []
    for gt in ground_truth:
        for artifact in artifacts:
            similarity = stage_similarity(stage, gt, artifact)
            if similarity < stage_threshold(stage, gt, artifact):
                continue
            if require_attachment and gt.attachment_ids and artifact.attachment_ids and set(gt.attachment_ids) != set(artifact.attachment_ids):
                continue
            candidates.append(
                (
                    -similarity,
                    gt.id,
                    artifact.id,
                    normalize_eval_kind(gt.kind),
                    artifact.source_bucket,
                    gt,
                    artifact,
                )
            )
    candidates.sort()
    matched_gt_ids: set[str] = set()
    matched_artifact_ids: set[str] = set()
    matches: list[MatchResult] = []
    for negative_similarity, gt_id, artifact_id, _, source_bucket, gt, artifact in candidates:
        if gt_id in matched_gt_ids or artifact_id in matched_artifact_ids:
            continue
        matched_gt_ids.add(gt_id)
        matched_artifact_ids.add(artifact_id)
        matches.append(
            MatchResult(
                gt_id=gt.id,
                artifact_id=artifact.id,
                similarity=-negative_similarity,
                source_bucket=source_bucket,
            )
        )
    return matches


def best_stage_candidate(
    stage: str,
    target: EvalItem,
    items: list[EvalItem],
    *,
    require_attachment: bool = False,
) -> BestCandidate:
    compatible_items = [item for item in items if are_kinds_compatible(target.kind, item.kind)]
    if not compatible_items:
        return BestCandidate(item=None, similarity=0.0, passes=False)
    best = max(compatible_items, key=lambda item: (stage_similarity(stage, target, item), item.score_total, item.id))
    similarity = stage_similarity(stage, target, best)
    passes = similarity >= stage_threshold(stage, target, best)
    if require_attachment and target.attachment_ids and best.attachment_ids and set(target.attachment_ids) != set(best.attachment_ids):
        passes = False
    return BestCandidate(item=best, similarity=similarity, passes=passes)


def best_contextual_match(target: EvalItem, pool: Iterable[EvalItem]) -> BestCandidate:
    best_item = None
    best_similarity = -1.0
    for candidate in pool:
        similarity = contextual_similarity(target, candidate)
        if similarity > best_similarity or (math.isclose(similarity, best_similarity) and candidate.id < (best_item.id if best_item is not None else "~")):
            best_item = candidate
            best_similarity = similarity
    if best_item is None:
        return BestCandidate(item=None, similarity=0.0, passes=False)
    return BestCandidate(item=best_item, similarity=max(0.0, best_similarity), passes=False)


def normalize_eval_kind(kind: str) -> str:
    normalized = kind.strip().lower()
    if normalized in {"rect", "rounded_rect", "box", "container", "panel"}:
        return "container"
    if normalized in {"line", "orthogonal_connector", "arrow", "connector", "solid_arrow"}:
        return "connector"
    return normalized


def stage_supports_kind(stage: str, kind: str) -> bool:
    normalized = normalize_eval_kind(kind)
    if stage == "01_geometry_raw":
        return normalized in {"container", "connector"}
    if stage == "02_guides":
        return normalized == "container"
    if stage in {"03_objects", "05_selection", "06_graph"}:
        return normalized in {"container", "textbox", "connector"}
    return normalized in {"container", "textbox", "connector"}


def are_kinds_compatible(left: str, right: str) -> bool:
    return normalize_eval_kind(left) == normalize_eval_kind(right)


def stage_threshold(stage: str, ground_truth: EvalItem, artifact: EvalItem) -> float:
    kind = normalize_eval_kind(ground_truth.kind)
    if kind == "connector":
        return 0.46 if stage in {"01_geometry_raw", "02_guides"} else 0.54
    if stage in {"01_geometry_raw", "02_guides"}:
        return 0.42
    return 0.5


def stage_similarity(stage: str, ground_truth: EvalItem, artifact: EvalItem) -> float:
    if not are_kinds_compatible(ground_truth.kind, artifact.kind):
        return 0.0
    kind = normalize_eval_kind(ground_truth.kind)
    if kind == "connector":
        return connector_similarity(ground_truth.bbox, artifact.bbox)
    return iou(ground_truth.bbox, artifact.bbox)


def contextual_similarity(left: EvalItem, right: EvalItem) -> float:
    if normalize_eval_kind(left.kind) == "connector" or normalize_eval_kind(right.kind) == "connector":
        return connector_similarity(left.bbox, right.bbox)
    return iou(left.bbox, right.bbox)


def connector_similarity(first: BBox | None, second: BBox | None) -> float:
    if first is None or second is None:
        return 0.0
    first_axis = connector_axis(first)
    second_axis = connector_axis(second)
    if first_axis != second_axis:
        return expanded_iou(first, second, padding=8.0) * 0.5
    if first_axis == "horizontal":
        overlap = interval_overlap(first.x0, first.x1, second.x0, second.x1)
        reference = max(first.width, second.width, 1.0)
        axis_ratio = overlap / reference
        orth_gap = abs(first.center.y - second.center.y)
        endpoint_gap = abs(first.x0 - second.x0) + abs(first.x1 - second.x1)
    else:
        overlap = interval_overlap(first.y0, first.y1, second.y0, second.y1)
        reference = max(first.height, second.height, 1.0)
        axis_ratio = overlap / reference
        orth_gap = abs(first.center.x - second.center.x)
        endpoint_gap = abs(first.y0 - second.y0) + abs(first.y1 - second.y1)
    orth_score = max(0.0, 1.0 - orth_gap / 26.0)
    endpoint_score = max(0.0, 1.0 - endpoint_gap / max(24.0, reference * 0.7))
    return max(expanded_iou(first, second, padding=6.0), axis_ratio * 0.55 + orth_score * 0.25 + endpoint_score * 0.20)


def connector_axis(bbox: BBox) -> str:
    return "horizontal" if bbox.width >= bbox.height else "vertical"


def expanded_iou(first: BBox, second: BBox, *, padding: float) -> float:
    return iou(first.expand(padding), second.expand(padding))


def interval_overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def classify_gt_failure(gt: EvalItem, ground_truth: list[EvalItem], predictions: list[EvalItem], best: BestCandidate) -> FailureTag:
    best_item = best.item
    same_kind_predictions = [prediction for prediction in predictions if are_kinds_compatible(gt.kind, prediction.kind) and contextual_similarity(gt, prediction) >= 0.1]
    if gt.attachment_ids and best_item is not None and are_kinds_compatible(gt.kind, best_item.kind) and best.similarity >= 0.35:
        if set(gt.attachment_ids) != set(best_item.attachment_ids):
            return FailureTag.WRONG_ATTACHMENT
    if best_item is not None and not are_kinds_compatible(gt.kind, best_item.kind) and best.similarity >= 0.3:
        return FailureTag.WRONG_TYPE
    for prediction in predictions:
        if prediction.bbox is None or gt.bbox is None or not are_kinds_compatible(gt.kind, prediction.kind):
            continue
        if contains(prediction.bbox, gt.bbox):
            sibling_hits = [
                other
                for other in ground_truth
                if other.id != gt.id and are_kinds_compatible(gt.kind, other.kind) and other.bbox is not None and contains(prediction.bbox, other.bbox)
            ]
            if sibling_hits:
                return FailureTag.MERGED_SIBLINGS
            if prediction.bbox.area > gt.bbox.area * 1.35:
                return FailureTag.MERGED_INTO_PARENT
    if len(same_kind_predictions) > 1 and covered_area_ratio(gt, same_kind_predictions) >= 0.7:
        return FailureTag.SPLIT_FRAGMENTS
    if same_kind_predictions and max(contextual_similarity(gt, prediction) for prediction in same_kind_predictions) >= 0.2:
        return FailureTag.NEAR_MISS_GEOMETRY
    return FailureTag.MISSING


def classify_prediction_failure(prediction: EvalItem, ground_truth: list[EvalItem], predictions: list[EvalItem], best: BestCandidate) -> FailureTag:
    best_item = best.item
    same_kind_gt = [gt for gt in ground_truth if are_kinds_compatible(gt.kind, prediction.kind) and contextual_similarity(prediction, gt) >= 0.1]
    if prediction.attachment_ids and best_item is not None and are_kinds_compatible(prediction.kind, best_item.kind) and best.similarity >= 0.35:
        if set(prediction.attachment_ids) != set(best_item.attachment_ids):
            return FailureTag.WRONG_ATTACHMENT
    if best_item is not None and not are_kinds_compatible(prediction.kind, best_item.kind) and best.similarity >= 0.3:
        return FailureTag.WRONG_TYPE
    overlapping_gt = [
        gt
        for gt in ground_truth
        if gt.bbox is not None and prediction.bbox is not None and are_kinds_compatible(gt.kind, prediction.kind) and contains(prediction.bbox, gt.bbox)
    ]
    if len(overlapping_gt) > 1:
        return FailureTag.MERGED_SIBLINGS
    if len(same_kind_gt) == 1:
        fragments = [
            other
            for other in predictions
            if other.id != prediction.id and are_kinds_compatible(other.kind, prediction.kind) and contextual_similarity(prediction, same_kind_gt[0]) >= 0.1 and contextual_similarity(other, same_kind_gt[0]) >= 0.1
        ]
        if fragments:
            return FailureTag.SPLIT_FRAGMENTS
    if same_kind_gt and max(contextual_similarity(prediction, gt) for gt in same_kind_gt) >= 0.2:
        return FailureTag.NEAR_MISS_GEOMETRY
    return FailureTag.HALLUCINATED_PREDICTION


def audit_row_for_candidate(candidate: BestCandidate, *, matched: bool | None = None) -> dict[str, object]:
    if candidate.item is None:
        row = {"artifact_id": None, "score_total": 0.0, "similarity": 0.0, "passes": False, "source_bucket": None}
    else:
        row = {
            "artifact_id": candidate.item.id,
            "score_total": round(candidate.item.score_total, 4),
            "similarity": round(candidate.similarity, 4),
            "passes": candidate.passes,
            "source_bucket": candidate.item.source_bucket,
        }
    if matched is not None:
        row["matched"] = matched
    return row


def audit_status(
    *,
    raw_best: BestCandidate,
    snapped_best: BestCandidate,
    object_best: BestCandidate,
    gt_id: str,
    selected_matches: dict[str, MatchResult],
    emit_matches: dict[str, MatchResult],
    fallback_rescued: bool,
) -> str:
    if not raw_best.item:
        return "no_raw_candidate"
    if not raw_best.passes:
        return "raw_candidate_below_threshold"
    if snapped_best.item and raw_best.passes and not snapped_best.passes and snapped_best.similarity + 0.05 < raw_best.similarity:
        return "guide_snap_hurt"
    if not object_best.item:
        return "object_conversion_absent"
    if not object_best.passes:
        return "object_conversion_rejected"
    if gt_id not in selected_matches:
        return "selection_suppressed"
    if gt_id not in emit_matches:
        return "emit_missing"
    if fallback_rescued:
        return "fallback_rescued"
    return "recovered"


def covered_area_ratio(target: EvalItem, predictions: list[EvalItem]) -> float:
    if target.bbox is None:
        return 0.0
    total = 0.0
    for prediction in predictions:
        total += contextual_similarity(target, prediction)
    return min(1.0, total)


def iou(first: BBox | None, second: BBox | None) -> float:
    if first is None or second is None:
        return 0.0
    return first.iou(second)


def contains(outer: BBox, inner: BBox) -> bool:
    return outer.x0 <= inner.x0 and outer.y0 <= inner.y0 and outer.x1 >= inner.x1 and outer.y1 >= inner.y1
