from __future__ import annotations

from dataclasses import dataclass
import json
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


@dataclass(slots=True, frozen=True)
class EvalItem:
    id: str
    kind: str
    bbox: BBox | None
    source_ids: tuple[str, ...] = ()
    attachment_ids: tuple[str, ...] = ()
    parent_id: str | None = None


@dataclass(slots=True, frozen=True)
class GroundTruthAnnotation:
    version: int
    path: Path
    objects: tuple[EvalItem, ...]


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
    return EvalItem(
        id=str(payload.get("id", "")).strip(),
        kind=str(payload.get("kind") or payload.get("object_type") or "").strip(),
        bbox=bbox,
        source_ids=tuple(str(item) for item in payload.get("source_ids", []) or []),
        attachment_ids=tuple(str(item) for item in (payload.get("attachment_ids") or payload.get("attachments") or []) or []),
        parent_id=None if payload.get("parent_id") in {None, ""} else str(payload.get("parent_id")),
    )


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
            if best is not None and same_object(gt, best, iou_threshold=iou_threshold, require_attachment=False):
                recovered += 1
                matches.append({"gt_id": gt.id, "artifact_id": best.id, "iou": iou(gt.bbox, best.bbox)})
            else:
                matches.append({"gt_id": gt.id, "artifact_id": None, "iou": 0.0})
        output[stage] = {
            "status": "ok",
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
        if best is not None and same_object(gt, best, iou_threshold=iou_threshold):
            continue
        gt_rows.append({"gt_id": gt.id, "tag": classify_gt_failure(gt, gt_items, pred_items, best).value, "best_prediction_id": None if best is None else best.id})
    pred_rows = []
    for pred in pred_items:
        best = best_match(pred, gt_items)
        if best is not None and same_object(best, pred, iou_threshold=iou_threshold):
            continue
        pred_rows.append({"prediction_id": pred.id, "tag": classify_prediction_failure(pred, gt_items, pred_items, best).value, "best_gt_id": None if best is None else best.id})
    return {"status": "ok", "ground_truth": gt_rows, "predictions": pred_rows}


def attrition_by_stage(
    ground_truth: Iterable[EvalItem],
    stage_artifacts: dict[str, Iterable[EvalItem]],
    *,
    iou_threshold: float = 0.5,
) -> dict[str, object]:
    stage_names = list(stage_artifacts.keys())
    gt_items = list(ground_truth)
    output = {"status": "ok", "ground_truth": []}
    stage_rows = {stage: list(items) for stage, items in stage_artifacts.items()}
    for gt in gt_items:
        stage_presence = {}
        for stage, items in stage_rows.items():
            best = best_match(gt, items)
            stage_presence[stage] = bool(best is not None and same_object(gt, best, iou_threshold=iou_threshold, require_attachment=False))
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
        for name in ("oracle_by_stage.json", "failure_taxonomy.json", "attrition_by_stage.json"):
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
    (target / "oracle_by_stage.json").write_text(json.dumps(as_serializable(oracle), indent=2), encoding="utf-8")
    (target / "failure_taxonomy.json").write_text(json.dumps(as_serializable(failure), indent=2), encoding="utf-8")
    (target / "attrition_by_stage.json").write_text(json.dumps(as_serializable(attrition), indent=2), encoding="utf-8")
    return {"oracle": oracle, "failure": failure, "attrition": attrition}


def stage_items_from_entities(items: Iterable[StageEntity]) -> list[EvalItem]:
    rows: list[EvalItem] = []
    for item in items:
        attachment_ids = ()
        parent_id = None
        if isinstance(item, EmissionRecord):
            attachment_ids = tuple(item.graph_node_ids)
        elif isinstance(item, ObjectHypothesis):
            attachment_ids = tuple(item.parent_ids)
        rows.append(
            EvalItem(
                id=item.id,
                kind=canonical_eval_kind(item),
                bbox=item.bbox,
                source_ids=tuple(item.source_ids),
                attachment_ids=attachment_ids,
                parent_id=parent_id,
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
        return object_type or item.kind
    return item.kind


def same_object(
    ground_truth: EvalItem,
    prediction: EvalItem,
    *,
    iou_threshold: float,
    require_attachment: bool = True,
) -> bool:
    if ground_truth.kind != prediction.kind:
        return False
    if iou(ground_truth.bbox, prediction.bbox) < iou_threshold:
        return False
    if not require_attachment or not ground_truth.attachment_ids:
        return True
    return set(ground_truth.attachment_ids) == set(prediction.attachment_ids)


def best_match(item: EvalItem, pool: Iterable[EvalItem]) -> EvalItem | None:
    best = None
    best_iou = -1.0
    for candidate in pool:
        overlap = iou(item.bbox, candidate.bbox)
        if overlap > best_iou:
            best = candidate
            best_iou = overlap
    return best


def classify_gt_failure(gt: EvalItem, ground_truth: list[EvalItem], predictions: list[EvalItem], best: EvalItem | None) -> FailureTag:
    same_kind_predictions = [prediction for prediction in predictions if prediction.kind == gt.kind and iou(gt.bbox, prediction.bbox) >= 0.1]
    if gt.attachment_ids and best is not None and best.kind == gt.kind and iou(gt.bbox, best.bbox) >= 0.3:
        if set(gt.attachment_ids) != set(best.attachment_ids):
            return FailureTag.WRONG_ATTACHMENT
    if best is not None and best.kind != gt.kind and iou(gt.bbox, best.bbox) >= 0.3:
        return FailureTag.WRONG_TYPE
    for prediction in predictions:
        if prediction.bbox is None or gt.bbox is None:
            continue
        if contains(prediction.bbox, gt.bbox):
            sibling_hits = [other for other in ground_truth if other.id != gt.id and other.kind == gt.kind and other.bbox is not None and contains(prediction.bbox, other.bbox)]
            if sibling_hits:
                return FailureTag.MERGED_SIBLINGS
            if prediction.bbox.area > gt.bbox.area * 1.35:
                return FailureTag.MERGED_INTO_PARENT
    if len(same_kind_predictions) > 1 and covered_area_ratio(gt, same_kind_predictions) >= 0.7:
        return FailureTag.SPLIT_FRAGMENTS
    if same_kind_predictions and max(iou(gt.bbox, prediction.bbox) for prediction in same_kind_predictions) >= 0.2:
        return FailureTag.NEAR_MISS_GEOMETRY
    return FailureTag.MISSING


def classify_prediction_failure(prediction: EvalItem, ground_truth: list[EvalItem], predictions: list[EvalItem], best: EvalItem | None) -> FailureTag:
    same_kind_gt = [gt for gt in ground_truth if gt.kind == prediction.kind and iou(prediction.bbox, gt.bbox) >= 0.1]
    if prediction.attachment_ids and best is not None and best.kind == prediction.kind and iou(prediction.bbox, best.bbox) >= 0.3:
        if set(prediction.attachment_ids) != set(best.attachment_ids):
            return FailureTag.WRONG_ATTACHMENT
    if best is not None and best.kind != prediction.kind and iou(prediction.bbox, best.bbox) >= 0.3:
        return FailureTag.WRONG_TYPE
    overlapping_gt = [gt for gt in ground_truth if gt.bbox is not None and prediction.bbox is not None and contains(prediction.bbox, gt.bbox)]
    if len(overlapping_gt) > 1:
        return FailureTag.MERGED_SIBLINGS
    if len(same_kind_gt) == 1:
        fragments = [other for other in predictions if other.id != prediction.id and other.kind == prediction.kind and iou(prediction.bbox, same_kind_gt[0].bbox) >= 0.1 and iou(other.bbox, same_kind_gt[0].bbox) >= 0.1]
        if fragments:
            return FailureTag.SPLIT_FRAGMENTS
    if same_kind_gt and max(iou(prediction.bbox, gt.bbox) for gt in same_kind_gt) >= 0.2:
        return FailureTag.NEAR_MISS_GEOMETRY
    return FailureTag.HALLUCINATED_PREDICTION


def covered_area_ratio(target: EvalItem, predictions: list[EvalItem]) -> float:
    if target.bbox is None:
        return 0.0
    total = 0.0
    for prediction in predictions:
        total += iou(target.bbox, prediction.bbox)
    return min(1.0, total)


def iou(first: BBox | None, second: BBox | None) -> float:
    if first is None or second is None:
        return 0.0
    return first.iou(second)


def contains(outer: BBox, inner: BBox) -> bool:
    return outer.x0 <= inner.x0 and outer.y0 <= inner.y0 and outer.x1 >= inner.x1 and outer.y1 >= inner.y1
