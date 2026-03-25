from __future__ import annotations

import json
from pathlib import Path

from image_to_editable_ppt.benchmark_report import summarize_benchmark, write_benchmark_summary


def write_slide(root: Path, slide_id: str, *, gt_available: bool) -> None:
    slide_dir = root / slide_id
    iteration_dir = slide_dir / "iter_00"
    diagnostics_dir = root / "_diagnostics" / slide_id / "iter_00"
    iteration_dir.mkdir(parents=True, exist_ok=True)
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    (slide_dir / "input.png").write_bytes(b"placeholder")
    (iteration_dir / "comparison.json").write_text("{}", encoding="utf-8")
    manifest = {
        "status": "ok",
        "gt_available": gt_available,
        "ablation_flags": {
            "grow_fallback_enabled": gt_available,
            "motifs_enabled": True,
            "titled_panel_motif_enabled": True,
            "repeated_cards_motif_enabled": True,
        },
        "emit_accounting": {
            "native_object_count": 3 if gt_available else 1,
            "raster_region_count": 1 if gt_available else 0,
            "native_area_ratio": 0.2,
            "raster_area_ratio": 0.1 if gt_available else 0.0,
            "raster_native_overlap_area_ratio": 0.02 if gt_available else 0.0,
            "dropped_hypothesis_count": 2 if gt_available else 0,
        },
        "motif_accounting": {
            "repeated_cards": {
                "proposed": 2,
                "accepted": 1 if gt_available else 0,
                "rejected": 1 if gt_available else 0,
                "absorbed_members": 2 if gt_available else 0,
                "suppressed_members": 0,
            }
        },
        "fallback_accounting": {"grow_fallback_hypothesis_count": 1 if gt_available else 0},
        "source_attribution": {
            "03_objects": {
                "count_by_source_bucket": {"geometry_only": 2, "fallback_only": 1 if gt_available else 0},
                "count_by_source_bucket_by_kind": {
                    "container": {"geometry_only": 1, "fallback_only": 1 if gt_available else 0},
                    "connector": {"geometry_only": 1, "fallback_only": 0},
                },
                "recoverable_gt_by_source_bucket": {"geometry_only": 1, "fallback_only": 1 if gt_available else 0},
                "recoverable_gt_by_source_bucket_by_kind": {
                    "container": {"geometry_only": 1, "fallback_only": 1 if gt_available else 0},
                    "connector": {"geometry_only": 0, "fallback_only": 0},
                },
            },
            "05_selection": {
                "selected_count_by_source_bucket": {"geometry_only": 2, "fallback_only": 1 if gt_available else 0},
                "selected_count_by_source_bucket_by_kind": {
                    "container": {"geometry_only": 1, "fallback_only": 1 if gt_available else 0},
                    "connector": {"geometry_only": 1, "fallback_only": 0},
                },
            },
            "07_emit": {
                "native_count_by_source_bucket": {"geometry_only": 2, "fallback_only": 1 if gt_available else 0},
                "native_count_by_source_bucket_by_kind": {
                    "container": {"geometry_only": 1, "fallback_only": 1 if gt_available else 0},
                    "connector": {"geometry_only": 1, "fallback_only": 0},
                },
                "matched_gt_by_source_bucket": {"geometry_only": 2, "fallback_only": 1 if gt_available else 0},
                "matched_gt_by_source_bucket_by_kind": {
                    "container": {"geometry_only": 1, "fallback_only": 1 if gt_available else 0},
                    "connector": {"geometry_only": 1, "fallback_only": 0},
                },
            },
        },
        "stages": {"07_emit": {"status": "ok", "entity_count": 4}},
    }
    (diagnostics_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    eval_dir = diagnostics_dir / "08_eval"
    eval_dir.mkdir(parents=True, exist_ok=True)
    if gt_available:
        (eval_dir / "oracle_by_stage.json").write_text(
            json.dumps(
                {
                    "status": "ok",
                    "gt_available": True,
                    "stages": {
                        "01_geometry_raw": {"recoverable_count": 2, "ground_truth_count": 4, "recoverable_ratio": 0.5},
                        "02_guides": {
                            "recoverable_count": 1,
                            "ground_truth_count": 2,
                            "recoverable_ratio": 0.5,
                            "ground_truth_count_by_kind": {"container": 2},
                            "recoverable_by_kind": {"container": 1},
                            "recoverable_by_source_bucket": {"geometry_only": 1},
                            "recoverable_by_source_bucket_by_kind": {"container": {"geometry_only": 1}},
                        },
                        "03_objects": {
                            "recoverable_count": 3,
                            "ground_truth_count": 4,
                            "recoverable_ratio": 0.75,
                            "ground_truth_count_by_kind": {"container": 2, "connector": 2},
                            "recoverable_by_kind": {"container": 2, "connector": 1},
                            "recoverable_by_source_bucket": {"geometry_only": 2, "fallback_only": 1},
                            "recoverable_by_source_bucket_by_kind": {
                                "container": {"geometry_only": 1, "fallback_only": 1},
                                "connector": {"geometry_only": 1, "fallback_only": 0},
                            },
                        },
                        "07_emit": {
                            "recoverable_count": 3,
                            "ground_truth_count": 4,
                            "recoverable_ratio": 0.75,
                            "ground_truth_count_by_kind": {"container": 2, "connector": 2},
                            "recoverable_by_kind": {"container": 2, "connector": 1},
                            "recoverable_by_source_bucket": {"geometry_only": 2, "fallback_only": 1},
                            "recoverable_by_source_bucket_by_kind": {
                                "container": {"geometry_only": 1, "fallback_only": 1},
                                "connector": {"geometry_only": 1, "fallback_only": 0},
                            },
                        },
                    },
                }
            ),
            encoding="utf-8",
        )
        (eval_dir / "attrition_by_stage.json").write_text(
            json.dumps(
                {
                    "status": "ok",
                    "ground_truth": [
                        {"gt_id": "a", "lost_at": "01_geometry_raw"},
                        {"gt_id": "b", "lost_at": "03_objects"},
                    ],
                }
            ),
            encoding="utf-8",
        )
        (eval_dir / "failure_taxonomy.json").write_text(
            json.dumps(
                {
                    "status": "ok",
                    "ground_truth": [{"gt_id": "a", "kind": "container", "tag": "missing"}],
                    "predictions": [{"prediction_id": "p1", "kind": "connector", "tag": "hallucinated_prediction"}],
                }
            ),
            encoding="utf-8",
        )
        (eval_dir / "geometry_audit.json").write_text(
            json.dumps(
                {
                    "status": "ok",
                    "ground_truth": [
                        {"gt_id": "a", "kind": "container", "status": "oversized_or_merged_candidate"},
                        {"gt_id": "b", "kind": "connector", "status": "raw_candidate_below_threshold"},
                    ],
                    "container_snap_effect_counts": {"worsened_by_snap": 1},
                }
            ),
            encoding="utf-8",
        )
        (eval_dir / "container_geometry_audit.json").write_text(
            json.dumps(
                {
                    "status": "ok",
                    "ground_truth": [
                        {"gt_id": "a", "kind": "container", "status": "oversized_or_merged_candidate", "snap_effect": "unchanged_by_snap"},
                        {"gt_id": "b", "kind": "container", "status": "snap_hurt", "snap_effect": "worsened_by_snap"},
                    ],
                    "status_counts": {"oversized_or_merged_candidate": 1, "snap_hurt": 1},
                    "snap_effect_counts": {"unchanged_by_snap": 1, "worsened_by_snap": 1},
                }
            ),
            encoding="utf-8",
        )
    else:
        unavailable = {"status": "unavailable", "gt_available": False, "reason": "ground_truth_annotations_missing"}
        for name in ("oracle_by_stage.json", "attrition_by_stage.json", "failure_taxonomy.json", "geometry_audit.json", "container_geometry_audit.json"):
            (eval_dir / name).write_text(json.dumps(unavailable), encoding="utf-8")

def test_benchmark_aggregation_distinguishes_gt_backed_and_unavailable_slides(tmp_path: Path) -> None:
    write_slide(tmp_path, "slide-a", gt_available=True)
    write_slide(tmp_path, "slide-b", gt_available=False)

    summary_path, rollup_path, summary, rows = write_benchmark_summary(tmp_path)

    assert summary_path.exists()
    assert rollup_path.exists()
    assert summary["gt_backed_slide_count"] == 1
    assert summary["gt_unavailable_slide_count"] == 1
    assert summary["gt_coverage_notice"] == "single_gt_backed_slide_only"
    assert len(rows) == 2
    assert {row["gt_available"] for row in rows} == {True, False}


def test_benchmark_aggregation_contains_stage_native_raster_and_motif_fields(tmp_path: Path) -> None:
    write_slide(tmp_path, "slide-a", gt_available=True)

    summary, rows = summarize_benchmark(tmp_path)
    row = rows[0]

    assert "stage_oracle" in summary
    assert "stage_attrition" in summary
    assert "failure_taxonomy" in summary
    assert "geometry_audit_status_counts" in summary
    assert "native_object_count" in summary
    assert "raster_region_count" in summary
    assert "stage_oracle_by_source_bucket" in summary
    assert "stage_oracle_by_kind" in summary
    assert "selection_count_by_source_bucket" in summary
    assert "native_emit_count_by_source_bucket" in summary
    assert "final_matched_gt_by_source_bucket" in summary
    assert "final_matched_gt_by_kind" in summary
    assert "failure_taxonomy_by_kind" in summary
    assert "geometry_audit_status_counts_by_kind" in summary
    assert "source_bucket_counts_by_kind" in summary
    assert "container_snap_effect_counts" in summary
    assert "ablation_counts" in summary
    assert "motif_accounting" in summary
    assert row["dominant_loss_stage"] == "01_geometry_raw"
    assert row["native_object_count"] == 3
    assert row["raster_region_count"] == 1
    assert row["motif_accounting"]["repeated_cards"]["accepted"] == 1
    assert row["geometry_audit_status_counts"]["oversized_or_merged_candidate"] == 1
    assert row["source_attribution"]["07_emit"]["matched_gt_by_source_bucket"]["geometry_only"] == 2
    assert summary["stage_oracle_by_kind"]["07_emit"]["container"]["recoverable_count"] == 2
    assert summary["stage_oracle_by_kind"]["07_emit"]["connector"]["recoverable_count"] == 1
    assert summary["failure_taxonomy_by_kind"]["ground_truth"]["container"]["missing"] == 1
    assert summary["geometry_audit_status_counts_by_kind"]["container"]["oversized_or_merged_candidate"] == 1
    assert summary["source_bucket_counts_by_kind"]["07_emit"]["matched_gt_by_source_bucket_by_kind"]["container"]["fallback_only"] == 1
    assert row["container_snap_effect_counts"]["worsened_by_snap"] == 1
    assert row["ablation_flags"]["grow_fallback_enabled"] is True
