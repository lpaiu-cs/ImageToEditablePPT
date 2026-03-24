from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Iterable

from .ir import BBox
from .schema import FailureTag, StageEntity, as_serializable


@dataclass(slots=True, frozen=True)
class EvalItem:
    id: str
    kind: str
    bbox: BBox | None
    source_ids: tuple[str, ...] = ()


def oracle_upper_bound_by_stage(
    ground_truth: Iterable[EvalItem],
    stage_artifacts: dict[str, Iterable[EvalItem]],
    *,
    iou_threshold: float = 0.5,
) -> dict[str, object]:
    gt_items = list(ground_truth)
    output: dict[str, object] = {}
    for stage, artifacts in stage_artifacts.items():
        rows = list(artifacts)
        matches = []
        recovered = 0
        for gt in gt_items:
            best = best_match(gt, rows)
            if best is not None and best.kind == gt.kind and iou(gt.bbox, best.bbox) >= iou_threshold:
                recovered += 1
                matches.append({"gt_id": gt.id, "artifact_id": best.id, "iou": iou(gt.bbox, best.bbox)})
            else:
                matches.append({"gt_id": gt.id, "artifact_id": None, "iou": 0.0})
        output[stage] = {
            "ground_truth_count": len(gt_items),
            "artifact_count": len(rows),
            "recoverable_count": recovered,
            "recoverable_ratio": recovered / max(1, len(gt_items)),
            "matches": matches,
        }
    return output


def failure_taxonomy(
    ground_truth: Iterable[EvalItem],
    predictions: Iterable[EvalItem],
    *,
    iou_threshold: float = 0.5,
) -> dict[str, object]:
    gt_items = list(ground_truth)
    pred_items = list(predictions)
    gt_rows = []
    for gt in gt_items:
        best = best_match(gt, pred_items)
        if best is not None and iou(gt.bbox, best.bbox) >= iou_threshold and best.kind == gt.kind:
            continue
        tag = classify_gt_failure(gt, pred_items, best)
        gt_rows.append({"gt_id": gt.id, "tag": tag.value, "best_prediction_id": None if best is None else best.id})
    pred_rows = []
    for pred in pred_items:
        best = best_match(pred, gt_items)
        if best is not None and iou(pred.bbox, best.bbox) >= iou_threshold and pred.kind == best.kind:
            continue
        pred_rows.append(
            {
                "prediction_id": pred.id,
                "tag": classify_prediction_failure(pred, gt_items, best).value,
                "best_gt_id": None if best is None else best.id,
            }
        )
    return {"ground_truth": gt_rows, "predictions": pred_rows}


def attrition_by_stage(
    ground_truth: Iterable[EvalItem],
    stage_artifacts: dict[str, Iterable[EvalItem]],
    *,
    iou_threshold: float = 0.5,
) -> dict[str, object]:
    stage_names = list(stage_artifacts.keys())
    gt_items = list(ground_truth)
    output = {"ground_truth": []}
    stage_rows = {stage: list(items) for stage, items in stage_artifacts.items()}
    for gt in gt_items:
        stage_presence = {
            stage: bool(
                best_match(gt, items) is not None
                and best_match(gt, items).kind == gt.kind
                and iou(gt.bbox, best_match(gt, items).bbox) >= iou_threshold
            )
            for stage, items in stage_rows.items()
        }
        lost_at = None
        seen = False
        for stage in stage_names:
            if stage_presence[stage]:
                seen = True
                continue
            if seen:
                lost_at = stage
                break
        output["ground_truth"].append({"gt_id": gt.id, "presence": stage_presence, "lost_at": lost_at})
    return output


def write_eval_debug_artifacts(
    output_dir: str | Path,
    ground_truth: Iterable[EvalItem] | None,
    stage_artifacts: dict[str, Iterable[EvalItem]],
) -> dict[str, object]:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    if ground_truth is None:
        unavailable = {"available": False, "reason": "ground_truth_annotations_missing"}
        for name in ("oracle_by_stage.json", "failure_taxonomy.json", "attrition_by_stage.json"):
            (target / name).write_text(json.dumps(unavailable, indent=2), encoding="utf-8")
        return unavailable
    oracle = oracle_upper_bound_by_stage(ground_truth, stage_artifacts)
    failure = failure_taxonomy(ground_truth, stage_artifacts.get("07_emit", []))
    attrition = attrition_by_stage(ground_truth, stage_artifacts)
    (target / "oracle_by_stage.json").write_text(json.dumps(as_serializable(oracle), indent=2), encoding="utf-8")
    (target / "failure_taxonomy.json").write_text(json.dumps(as_serializable(failure), indent=2), encoding="utf-8")
    (target / "attrition_by_stage.json").write_text(json.dumps(as_serializable(attrition), indent=2), encoding="utf-8")
    return {"oracle": oracle, "failure": failure, "attrition": attrition}


def stage_items_from_entities(items: Iterable[StageEntity]) -> list[EvalItem]:
    return [EvalItem(id=item.id, kind=item.kind, bbox=item.bbox, source_ids=tuple(item.source_ids)) for item in items]


def best_match(item: EvalItem, pool: Iterable[EvalItem]):
    best = None
    best_iou = -1.0
    for candidate in pool:
        overlap = iou(item.bbox, candidate.bbox)
        if overlap > best_iou:
            best = candidate
            best_iou = overlap
    return best


def classify_gt_failure(gt: EvalItem, predictions: list[EvalItem], best: EvalItem | None) -> FailureTag:
    overlaps = [prediction for prediction in predictions if iou(gt.bbox, prediction.bbox) >= 0.1]
    if best is None:
        return FailureTag.MISSING
    if best.kind != gt.kind and iou(gt.bbox, best.bbox) >= 0.3:
        return FailureTag.WRONG_TYPE
    if len(overlaps) > 1:
        total_overlap = sum(iou(gt.bbox, prediction.bbox) for prediction in overlaps)
        if total_overlap >= 0.8:
            return FailureTag.SPLIT_FRAGMENTS
    covering = [prediction for prediction in predictions if prediction.bbox is not None and gt.bbox is not None and contains(prediction.bbox, gt.bbox)]
    if len(covering) >= 1:
        for prediction in covering:
            siblings = [other for other in predictions if other.id != prediction.id and prediction.bbox is not None and other.bbox is not None and prediction.bbox.overlaps(other.bbox)]
            if siblings:
                return FailureTag.MERGED_SIBLINGS
        return FailureTag.MERGED_INTO_PARENT
    if iou(gt.bbox, best.bbox) >= 0.2:
        return FailureTag.NEAR_MISS_GEOMETRY
    return FailureTag.MISSING


def classify_prediction_failure(prediction: EvalItem, ground_truth: list[EvalItem], best: EvalItem | None) -> FailureTag:
    if best is None:
        return FailureTag.HALLUCINATED_PREDICTION
    if best.kind != prediction.kind and iou(prediction.bbox, best.bbox) >= 0.3:
        return FailureTag.WRONG_TYPE
    if iou(prediction.bbox, best.bbox) >= 0.2:
        return FailureTag.NEAR_MISS_GEOMETRY
    return FailureTag.HALLUCINATED_PREDICTION


def iou(first: BBox | None, second: BBox | None) -> float:
    if first is None or second is None:
        return 0.0
    return first.iou(second)


def contains(outer: BBox, inner: BBox) -> bool:
    return outer.x0 <= inner.x0 and outer.y0 <= inner.y0 and outer.x1 >= inner.x1 and outer.y1 >= inner.y1
