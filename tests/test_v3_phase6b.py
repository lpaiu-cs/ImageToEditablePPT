from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw

from image_to_editable_ppt.eval_runtime import build_v3_eval_adapter_result
from image_to_editable_ppt.v3.app.convert import convert_image
from image_to_editable_ppt.v3.diagnostics import run_v3_debug
from image_to_editable_ppt.v3.emit import build_emit_scene, diff_emit_scene


def test_eval_adapter_builds_manifest_and_stage_artifacts_for_synthetic_orthogonal_flow() -> None:
    result = convert_image(make_synthetic_orthogonal_flow_image())
    scene = result.slide_ir.primitive_scene
    assert scene is not None

    emit_scene = build_emit_scene(
        primitive_scene=scene,
        connectors=result.slide_ir.connectors,
    )
    adapter = build_v3_eval_adapter_result(
        slide_ir=result.slide_ir,
        stage_records=result.stage_records,
        emit_scene=emit_scene,
    )

    assert tuple(adapter.stage_artifacts) == ("03_objects", "05_selection", "07_emit")
    assert len(adapter.stage_artifacts["03_objects"]) == 8
    assert len(adapter.stage_artifacts["05_selection"]) == 8
    assert len(adapter.stage_artifacts["07_emit"]) == 8
    assert adapter.manifest["adapter_scope"]["coordinate_space"] == "image_space"
    assert adapter.manifest["emit_accounting"]["native_object_count"] == 8
    assert adapter.manifest["emit_accounting"]["raster_region_count"] == 0
    assert adapter.manifest["source_attribution"]["07_emit"]["native_count_by_source_bucket"]["geometry_only"] == 8
    assert adapter.manifest["source_attribution"]["07_emit"]["matched_gt_by_source_bucket"]["geometry_only"] == 0


def test_emit_diff_reports_lossless_adapter_bridge_for_synthetic_orthogonal_flow() -> None:
    result = convert_image(make_synthetic_orthogonal_flow_image())
    scene = result.slide_ir.primitive_scene
    assert scene is not None

    emit_scene = build_emit_scene(
        primitive_scene=scene,
        connectors=result.slide_ir.connectors,
    )
    emit_diff = diff_emit_scene(
        primitive_scene=scene,
        connectors=result.slide_ir.connectors,
        emit_scene=emit_scene,
    )

    assert emit_diff.lossless is True
    assert emit_diff.coordinate_space == "image_space"
    assert emit_diff.missing_shape_ids == ()
    assert emit_diff.extra_shape_ids == ()
    assert emit_diff.missing_text_ids == ()
    assert emit_diff.extra_text_ids == ()
    assert emit_diff.missing_connector_ids == ()
    assert emit_diff.extra_connector_ids == ()
    assert emit_diff.connector_path_mismatch_ids == ()


def test_debug_runner_writes_eval_adapter_manifest_eval_payload_and_emit_diff(tmp_path: Path) -> None:
    image_path = tmp_path / "orthogonal_flow.png"
    make_synthetic_orthogonal_flow_image().save(image_path)

    baseline = convert_image(image_path)
    scene = baseline.slide_ir.primitive_scene
    assert scene is not None
    emit_scene = build_emit_scene(
        primitive_scene=scene,
        connectors=baseline.slide_ir.connectors,
    )
    adapter = build_v3_eval_adapter_result(
        slide_ir=baseline.slide_ir,
        stage_records=baseline.stage_records,
        emit_scene=emit_scene,
    )
    gt_payload = {
        "version": 1,
        "objects": [
            {
                "id": f"gt:{item.id}",
                "kind": item.kind,
                "bbox": None if item.bbox is None else item.bbox.to_dict(),
                "attachment_ids": list(item.attachment_ids),
            }
            for item in adapter.stage_artifacts["07_emit"]
        ],
    }
    (tmp_path / "orthogonal_flow.gt.json").write_text(json.dumps(gt_payload), encoding="utf-8")

    run = run_v3_debug(image_path, output_dir=tmp_path / "debug")

    assert run.artifacts.manifest_json.exists()
    assert run.artifacts.eval_stage_artifacts_json.exists()
    assert run.artifacts.emit_diff_json.exists()
    assert run.artifacts.overlay_emit_diff_png.exists()
    assert run.artifacts.eval_dir.exists()
    assert (run.artifacts.eval_dir / "oracle_by_stage.json").exists()

    manifest = json.loads(run.artifacts.manifest_json.read_text(encoding="utf-8"))
    stage_artifacts = json.loads(run.artifacts.eval_stage_artifacts_json.read_text(encoding="utf-8"))
    emit_diff = json.loads(run.artifacts.emit_diff_json.read_text(encoding="utf-8"))
    oracle = json.loads((run.artifacts.eval_dir / "oracle_by_stage.json").read_text(encoding="utf-8"))

    assert manifest["gt_available"] is True
    assert stage_artifacts["supported_stages"] == ["03_objects", "05_selection", "07_emit"]
    assert emit_diff["emit_diff"]["lossless"] is True
    assert oracle["gt_available"] is True
    assert oracle["stages"]["07_emit"]["recoverable_count"] == len(gt_payload["objects"])
    assert manifest["source_attribution"]["07_emit"]["matched_gt_by_source_bucket"]["geometry_only"] == len(
        gt_payload["objects"]
    )


def make_synthetic_orthogonal_flow_image() -> Image.Image:
    image = Image.new("RGB", (260, 150), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((18, 42, 96, 96), outline="black", width=2)
    draw.rectangle((164, 42, 242, 96), outline="black", width=2)
    draw.line((96, 69, 164, 69), fill="black", width=2)
    draw.text((38, 58), "Source", fill="black")
    draw.text((182, 58), "Sink", fill="black")
    return image
