from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from image_to_editable_ppt.eval_debug import EvalItem, discover_ground_truth, write_eval_debug_artifacts
from image_to_editable_ppt.source_attribution import (
    SourceBucket,
    count_source_buckets,
    count_source_buckets_by_kind,
)
from image_to_editable_ppt.v3.emit import build_emit_scene
from image_to_editable_ppt.v3.emit.models import EmitScene
from image_to_editable_ppt.v3.ir.models import SlideIR

if TYPE_CHECKING:
    from image_to_editable_ppt.v3.core.contracts import StageRecord


SUPPORTED_EVAL_STAGES = ("03_objects", "05_selection", "07_emit")


@dataclass(slots=True, frozen=True)
class V3EvalAdapterResult:
    manifest: dict[str, object]
    stage_artifacts: dict[str, tuple[EvalItem, ...]]


def build_v3_eval_adapter_result(
    *,
    slide_ir: SlideIR,
    stage_records: tuple["StageRecord", ...] = (),
    emit_scene: EmitScene | None = None,
) -> V3EvalAdapterResult:
    primitive_scene = slide_ir.primitive_scene
    resolved_emit_scene = emit_scene
    if resolved_emit_scene is None and primitive_scene is not None:
        resolved_emit_scene = build_emit_scene(
            primitive_scene=primitive_scene,
            connectors=slide_ir.connectors,
        )

    object_items = () if primitive_scene is None else _primitive_scene_eval_items(slide_ir)
    selection_items = object_items
    emit_items = () if resolved_emit_scene is None else _emit_scene_eval_items(resolved_emit_scene)

    stage_artifacts = {
        "03_objects": object_items,
        "05_selection": selection_items,
        "07_emit": emit_items,
    }
    manifest = _build_manifest(
        slide_ir=slide_ir,
        stage_records=stage_records,
        emit_scene=resolved_emit_scene,
        stage_artifacts=stage_artifacts,
    )
    return V3EvalAdapterResult(manifest=manifest, stage_artifacts=stage_artifacts)


def merge_eval_debug_payload(
    *,
    adapter_result: V3EvalAdapterResult,
    eval_payload: dict[str, object],
) -> V3EvalAdapterResult:
    manifest = deepcopy(adapter_result.manifest)
    source_attribution = manifest.get("source_attribution", {})
    if not isinstance(source_attribution, dict):
        return V3EvalAdapterResult(manifest=manifest, stage_artifacts=adapter_result.stage_artifacts)

    gt_available = _eval_gt_available(eval_payload)
    manifest["gt_available"] = gt_available
    if not gt_available:
        return V3EvalAdapterResult(manifest=manifest, stage_artifacts=adapter_result.stage_artifacts)

    oracle_stages = _oracle_stages(eval_payload)
    source_attribution["03_objects"]["recoverable_gt_by_source_bucket"] = _bucket_counts(
        oracle_stages.get("03_objects", {}).get("recoverable_by_source_bucket", {})
    )
    source_attribution["03_objects"]["recoverable_gt_by_source_bucket_by_kind"] = _bucket_counts_by_kind(
        oracle_stages.get("03_objects", {}).get("recoverable_by_source_bucket_by_kind", {}),
        stage_artifacts=adapter_result.stage_artifacts["03_objects"],
    )
    source_attribution["07_emit"]["matched_gt_by_source_bucket"] = _bucket_counts(
        oracle_stages.get("07_emit", {}).get("recoverable_by_source_bucket", {})
    )
    source_attribution["07_emit"]["matched_gt_by_source_bucket_by_kind"] = _bucket_counts_by_kind(
        oracle_stages.get("07_emit", {}).get("recoverable_by_source_bucket_by_kind", {}),
        stage_artifacts=adapter_result.stage_artifacts["07_emit"],
    )
    return V3EvalAdapterResult(manifest=manifest, stage_artifacts=adapter_result.stage_artifacts)


def stage_artifacts_to_json(stage_artifacts: dict[str, tuple[EvalItem, ...]]) -> dict[str, object]:
    return {
        "supported_stages": list(SUPPORTED_EVAL_STAGES),
        "stage_artifacts": {
            stage: [_eval_item_to_json(item) for item in stage_artifacts.get(stage, ())]
            for stage in SUPPORTED_EVAL_STAGES
        },
    }


def write_v3_eval_debug_artifacts(
    *,
    output_dir: str | Path,
    input_path: str | Path | None,
    adapter_result: V3EvalAdapterResult,
) -> tuple[V3EvalAdapterResult, dict[str, object]]:
    eval_payload = write_eval_debug_artifacts(
        output_dir,
        discover_ground_truth(input_path) if input_path is not None else None,
        adapter_result.stage_artifacts,
    )
    merged = merge_eval_debug_payload(
        adapter_result=adapter_result,
        eval_payload=eval_payload,
    )
    return merged, eval_payload


def _build_manifest(
    *,
    slide_ir: SlideIR,
    stage_records: tuple["StageRecord", ...],
    emit_scene: EmitScene | None,
    stage_artifacts: dict[str, tuple[EvalItem, ...]],
) -> dict[str, object]:
    primitive_scene = slide_ir.primitive_scene
    image_area = max(1.0, float(slide_ir.image_size.width * slide_ir.image_size.height))
    residual_items = () if primitive_scene is None else primitive_scene.residuals
    emit_items = stage_artifacts["07_emit"]

    return {
        "status": "ok",
        "pipeline": "v3",
        "adapter_version": "phase6b_eval_adapter_v1",
        "gt_available": False,
        "adapter_scope": {
            "supported_stages": list(SUPPORTED_EVAL_STAGES),
            "selection_stage_note": "05_selection currently mirrors 03_objects until a dedicated selection stage exists.",
            "coordinate_space": None if emit_scene is None else emit_scene.coordinate_space,
        },
        "stages": {
            stage: {
                "status": "ok",
                "entity_count": len(stage_artifacts[stage]),
            }
            for stage in SUPPORTED_EVAL_STAGES
        },
        "stage_records": [
            {
                "stage": record.stage.value,
                "summary": record.summary,
                "notes": list(record.notes),
            }
            for record in stage_records
        ],
        "ablation_flags": {
            "grow_fallback_enabled": False,
            "motifs_enabled": False,
            "emit_adapter_enabled": emit_scene is not None,
        },
        "emit_accounting": {
            "native_object_count": len(emit_items),
            "raster_region_count": len(residual_items),
            "native_area_ratio": _bbox_area_sum(emit_items) / image_area,
            "raster_area_ratio": _bbox_area_sum(residual_items) / image_area,
            "raster_native_overlap_area_ratio": _pairwise_overlap_area(residual_items, emit_items) / image_area,
            "dropped_hypothesis_count": len(slide_ir.unattached_connector_evidence),
        },
        "motif_accounting": {},
        "fallback_accounting": {
            "grow_fallback_hypothesis_count": 0,
        },
        "source_attribution": {
            "03_objects": {
                "count_by_source_bucket": _bucket_counts(count_source_buckets(stage_artifacts["03_objects"])),
                "count_by_source_bucket_by_kind": count_source_buckets_by_kind(stage_artifacts["03_objects"]),
                "recoverable_gt_by_source_bucket": _zero_bucket_counts(),
                "recoverable_gt_by_source_bucket_by_kind": _zero_bucket_counts_by_kind(stage_artifacts["03_objects"]),
            },
            "05_selection": {
                "selected_count_by_source_bucket": _bucket_counts(count_source_buckets(stage_artifacts["05_selection"])),
                "selected_count_by_source_bucket_by_kind": count_source_buckets_by_kind(stage_artifacts["05_selection"]),
            },
            "07_emit": {
                "native_count_by_source_bucket": _bucket_counts(count_source_buckets(stage_artifacts["07_emit"])),
                "native_count_by_source_bucket_by_kind": count_source_buckets_by_kind(stage_artifacts["07_emit"]),
                "matched_gt_by_source_bucket": _zero_bucket_counts(),
                "matched_gt_by_source_bucket_by_kind": _zero_bucket_counts_by_kind(stage_artifacts["07_emit"]),
            },
        },
    }


def _primitive_scene_eval_items(slide_ir: SlideIR) -> tuple[EvalItem, ...]:
    scene = slide_ir.primitive_scene
    if scene is None:
        return ()

    items: list[EvalItem] = []
    for container in scene.containers:
        items.append(
            EvalItem(
                id=container.id,
                kind="container",
                bbox=container.bbox,
                source_ids=_shape_source_ids(container.id, container.source),
                score_total=container.confidence,
                source_bucket=SourceBucket.GEOMETRY_ONLY.value,
            )
        )
    for node in scene.nodes:
        items.append(
            EvalItem(
                id=node.id,
                kind="container",
                bbox=node.bbox,
                source_ids=_shape_source_ids(node.id, node.source),
                score_total=node.confidence,
                source_bucket=SourceBucket.GEOMETRY_ONLY.value,
            )
        )
    for text in scene.texts:
        items.append(
            EvalItem(
                id=text.id,
                kind="textbox",
                bbox=text.bbox,
                source_ids=_text_source_ids(text.id, text.source),
                parent_id=None if not text.owner_ids else text.owner_ids[0],
                score_total=text.confidence,
                source_bucket=SourceBucket.GEOMETRY_ONLY.value,
            )
        )
    for connector in slide_ir.connectors:
        items.append(
            EvalItem(
                id=connector.id,
                kind="connector",
                bbox=_path_bbox(connector.path_points),
                source_ids=_connector_source_ids(connector.id, connector.source_candidate_id, connector.source_evidence_id, connector.source),
                attachment_ids=(connector.source_owner_id, connector.target_owner_id),
                score_total=connector.confidence,
                source_bucket=SourceBucket.GEOMETRY_ONLY.value,
            )
        )
    return tuple(items)


def _emit_scene_eval_items(scene: EmitScene) -> tuple[EvalItem, ...]:
    items: list[EvalItem] = []
    for shape in scene.shapes:
        items.append(
            EvalItem(
                id=shape.id,
                kind="container",
                bbox=shape.bbox,
                source_ids=_shape_source_ids(shape.id, shape.source),
                score_total=shape.confidence,
                source_bucket=SourceBucket.GEOMETRY_ONLY.value,
            )
        )
    for text in scene.texts:
        items.append(
            EvalItem(
                id=text.id,
                kind="textbox",
                bbox=text.bbox,
                source_ids=_text_source_ids(text.id, text.source),
                parent_id=None if not text.owner_ids else text.owner_ids[0],
                score_total=text.confidence,
                source_bucket=SourceBucket.GEOMETRY_ONLY.value,
            )
        )
    for connector in scene.connectors:
        items.append(
            EvalItem(
                id=connector.id,
                kind="connector",
                bbox=_path_bbox(connector.path_points),
                source_ids=_connector_source_ids(
                    connector.id,
                    connector.source_candidate_id,
                    connector.source_evidence_id,
                    connector.source,
                ),
                attachment_ids=(connector.source_owner_id, connector.target_owner_id),
                score_total=connector.confidence,
                source_bucket=SourceBucket.GEOMETRY_ONLY.value,
            )
        )
    return tuple(items)


def _shape_source_ids(item_id: str, source: str) -> tuple[str, ...]:
    return (f"rect-candidate:v3:{item_id}", source)


def _text_source_ids(item_id: str, source: str) -> tuple[str, ...]:
    return (f"region-primitive:v3:{item_id}", source)


def _connector_source_ids(
    item_id: str,
    source_candidate_id: str | None,
    source_evidence_id: str | None,
    source: str,
) -> tuple[str, ...]:
    ids = [f"connector-candidate:v3:{item_id}"]
    if source_candidate_id:
        ids.append(f"connector-candidate:v3:{source_candidate_id}")
    if source_evidence_id:
        ids.append(f"connector-candidate:v3:{source_evidence_id}")
    ids.append(source)
    return tuple(ids)


def _bucket_counts(payload: dict[str, object]) -> dict[str, int]:
    return {
        bucket.value: int(payload.get(bucket.value, 0)) if isinstance(payload, dict) else 0
        for bucket in SourceBucket
    }


def _zero_bucket_counts() -> dict[str, int]:
    return {bucket.value: 0 for bucket in SourceBucket}


def _zero_bucket_counts_by_kind(items: tuple[EvalItem, ...]) -> dict[str, dict[str, int]]:
    return {
        kind: _zero_bucket_counts()
        for kind in sorted(count_source_buckets_by_kind(items))
    }


def _bucket_counts_by_kind(
    payload: object,
    *,
    stage_artifacts: tuple[EvalItem, ...],
) -> dict[str, dict[str, int]]:
    if not isinstance(payload, dict):
        return _zero_bucket_counts_by_kind(stage_artifacts)
    result: dict[str, dict[str, int]] = {}
    known_kinds = set(count_source_buckets_by_kind(stage_artifacts))
    known_kinds.update(str(kind) for kind in payload)
    for kind in sorted(known_kinds):
        bucket_counts = payload.get(kind, {}) if isinstance(payload, dict) else {}
        result[kind] = _bucket_counts(bucket_counts if isinstance(bucket_counts, dict) else {})
    return result


def _path_bbox(points) -> object | None:
    if not points:
        return None
    x_values = [point.x for point in points]
    y_values = [point.y for point in points]
    from image_to_editable_ppt.shared.geometry import BBox

    return BBox(min(x_values), min(y_values), max(x_values), max(y_values))


def _bbox_area_sum(items) -> float:
    total = 0.0
    for item in items:
        bbox = getattr(item, "bbox", None)
        if bbox is not None:
            total += float(bbox.area)
    return total


def _pairwise_overlap_area(first_items, second_items) -> float:
    total = 0.0
    for first in first_items:
        bbox_a = getattr(first, "bbox", None)
        if bbox_a is None:
            continue
        for second in second_items:
            bbox_b = getattr(second, "bbox", None)
            if bbox_b is None or not bbox_a.overlaps(bbox_b):
                continue
            x0 = max(bbox_a.x0, bbox_b.x0)
            y0 = max(bbox_a.y0, bbox_b.y0)
            x1 = min(bbox_a.x1, bbox_b.x1)
            y1 = min(bbox_a.y1, bbox_b.y1)
            if x1 > x0 and y1 > y0:
                total += (x1 - x0) * (y1 - y0)
    return total


def _oracle_stages(eval_payload: dict[str, object]) -> dict[str, object]:
    if "oracle" in eval_payload and isinstance(eval_payload.get("oracle"), dict):
        return eval_payload["oracle"].get("stages", {}) if isinstance(eval_payload["oracle"], dict) else {}
    return eval_payload.get("stages", {}) if isinstance(eval_payload, dict) else {}


def _eval_gt_available(eval_payload: dict[str, object]) -> bool:
    if "oracle" in eval_payload and isinstance(eval_payload.get("oracle"), dict):
        return bool(eval_payload["oracle"].get("gt_available", False))
    return bool(eval_payload.get("gt_available", False))


def _eval_item_to_json(item: EvalItem) -> dict[str, object]:
    return {
        "id": item.id,
        "kind": item.kind,
        "bbox": None if item.bbox is None else item.bbox.to_dict(),
        "source_ids": list(item.source_ids),
        "attachment_ids": list(item.attachment_ids),
        "parent_id": item.parent_id,
        "score_total": item.score_total,
        "source_bucket": item.source_bucket,
        "evaluable": item.evaluable,
    }
