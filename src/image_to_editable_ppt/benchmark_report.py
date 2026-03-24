from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def find_latest_iteration(slide_dir: Path) -> Path | None:
    iterations = sorted(path for path in slide_dir.glob("iter_*") if path.is_dir())
    return iterations[-1] if iterations else None


def resolve_diagnostics_dir(benchmark_root: Path, slide_id: str, iteration_name: str) -> Path | None:
    candidates = [
        benchmark_root / "_diagnostics" / slide_id / iteration_name,
        Path("artifacts") / "diagnostics" / slide_id / iteration_name,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def summarize_benchmark(benchmark_root: str | Path) -> tuple[dict[str, object], list[dict[str, object]]]:
    root = Path(benchmark_root)
    slide_rows: list[dict[str, object]] = []
    oracle_totals: dict[str, dict[str, float]] = defaultdict(lambda: {"recoverable_count": 0.0, "ground_truth_count": 0.0})
    oracle_source_totals: dict[str, Counter[str]] = defaultdict(Counter)
    attrition_totals: Counter[str] = Counter()
    gt_failure_counts: Counter[str] = Counter()
    pred_failure_counts: Counter[str] = Counter()
    geometry_audit_status_totals: Counter[str] = Counter()
    motif_family_totals: dict[str, Counter[str]] = defaultdict(Counter)
    selection_source_totals: Counter[str] = Counter()
    emit_source_totals: Counter[str] = Counter()
    final_match_source_totals: Counter[str] = Counter()
    ablation_totals: Counter[str] = Counter()
    native_object_count = 0
    raster_region_count = 0
    dropped_hypothesis_count = 0
    grow_fallback_count = 0
    total_native_area_ratio = 0.0
    total_raster_area_ratio = 0.0
    total_raster_native_overlap_ratio = 0.0
    gt_backed_slide_count = 0
    gt_unavailable_slide_count = 0

    for slide_dir in sorted(path for path in root.iterdir() if path.is_dir() and path.name != "_diagnostics"):
        iteration_dir = find_latest_iteration(slide_dir)
        if iteration_dir is None:
            continue
        diagnostics_dir = resolve_diagnostics_dir(root, slide_dir.name, iteration_dir.name)
        manifest = {} if diagnostics_dir is None or not (diagnostics_dir / "manifest.json").exists() else load_json(diagnostics_dir / "manifest.json")
        oracle_payload = {}
        attrition_payload = {}
        failure_payload = {}
        geometry_audit_payload = {}
        if diagnostics_dir is not None and (diagnostics_dir / "08_eval" / "oracle_by_stage.json").exists():
            oracle_payload = load_json(diagnostics_dir / "08_eval" / "oracle_by_stage.json")
            attrition_payload = load_json(diagnostics_dir / "08_eval" / "attrition_by_stage.json")
            failure_payload = load_json(diagnostics_dir / "08_eval" / "failure_taxonomy.json")
            if (diagnostics_dir / "08_eval" / "geometry_audit.json").exists():
                geometry_audit_payload = load_json(diagnostics_dir / "08_eval" / "geometry_audit.json")
        gt_available = bool(oracle_payload.get("gt_available", manifest.get("gt_available", False)))
        if gt_available:
            gt_backed_slide_count += 1
        else:
            gt_unavailable_slide_count += 1
        accounting = manifest.get("emit_accounting", {}) if isinstance(manifest, dict) else {}
        motif_accounting = manifest.get("motif_accounting", {}) if isinstance(manifest, dict) else {}
        fallback_accounting = manifest.get("fallback_accounting", {}) if isinstance(manifest, dict) else {}
        source_attribution = manifest.get("source_attribution", {}) if isinstance(manifest, dict) else {}
        ablation_flags = manifest.get("ablation_flags", {}) if isinstance(manifest, dict) else {}
        for stage, payload in (oracle_payload.get("stages", {}) if isinstance(oracle_payload, dict) else {}).items():
            oracle_totals[stage]["recoverable_count"] += float(payload.get("recoverable_count", 0.0))
            oracle_totals[stage]["ground_truth_count"] += float(payload.get("ground_truth_count", 0.0))
            for bucket, count in (payload.get("recoverable_by_source_bucket", {}) if isinstance(payload, dict) else {}).items():
                oracle_source_totals[stage][str(bucket)] += int(count)
        for row in attrition_payload.get("ground_truth", []) if isinstance(attrition_payload, dict) else []:
            lost_at = row.get("lost_at")
            if lost_at:
                attrition_totals[str(lost_at)] += 1
        for row in failure_payload.get("ground_truth", []) if isinstance(failure_payload, dict) else []:
            gt_failure_counts[str(row.get("tag", "unknown"))] += 1
        for row in failure_payload.get("predictions", []) if isinstance(failure_payload, dict) else []:
            pred_failure_counts[str(row.get("tag", "unknown"))] += 1
        for row in geometry_audit_payload.get("ground_truth", []) if isinstance(geometry_audit_payload, dict) else []:
            geometry_audit_status_totals[str(row.get("status", "unknown"))] += 1
        for family, payload in motif_accounting.items() if isinstance(motif_accounting, dict) else []:
            if not isinstance(payload, dict):
                continue
            motif_family_totals[family]["proposed"] += int(payload.get("proposed", 0))
            motif_family_totals[family]["accepted"] += int(payload.get("accepted", 0))
            motif_family_totals[family]["rejected"] += int(payload.get("rejected", 0))
            motif_family_totals[family]["absorbed_members"] += int(payload.get("absorbed_members", 0))
            motif_family_totals[family]["suppressed_members"] += int(payload.get("suppressed_members", 0))
        native_object_count += int(accounting.get("native_object_count", 0))
        raster_region_count += int(accounting.get("raster_region_count", 0))
        dropped_hypothesis_count += int(accounting.get("dropped_hypothesis_count", 0))
        grow_fallback_count += int(fallback_accounting.get("grow_fallback_hypothesis_count", 0))
        total_native_area_ratio += float(accounting.get("native_area_ratio", 0.0))
        total_raster_area_ratio += float(accounting.get("raster_area_ratio", 0.0))
        total_raster_native_overlap_ratio += float(accounting.get("raster_native_overlap_area_ratio", 0.0))
        for bucket, count in (source_attribution.get("05_selection", {}).get("selected_count_by_source_bucket", {}) if isinstance(source_attribution.get("05_selection", {}), dict) else {}).items():
            selection_source_totals[str(bucket)] += int(count)
        for bucket, count in (source_attribution.get("07_emit", {}).get("native_count_by_source_bucket", {}) if isinstance(source_attribution.get("07_emit", {}), dict) else {}).items():
            emit_source_totals[str(bucket)] += int(count)
        for bucket, count in (source_attribution.get("07_emit", {}).get("matched_gt_by_source_bucket", {}) if isinstance(source_attribution.get("07_emit", {}), dict) else {}).items():
            final_match_source_totals[str(bucket)] += int(count)
        ablation_totals[ablation_key(ablation_flags)] += 1
        stage_oracle = oracle_payload.get("stages", {}) if isinstance(oracle_payload, dict) else {}
        slide_attrition_counts = dict(Counter(row["lost_at"] for row in attrition_payload.get("ground_truth", []) if row.get("lost_at"))) if isinstance(attrition_payload, dict) else {}
        slide_geometry_status_counts = dict(Counter(row["status"] for row in geometry_audit_payload.get("ground_truth", []) if row.get("status"))) if isinstance(geometry_audit_payload, dict) else {}
        dominant_loss_stage = dominant_stage_from_aggregate(stage_oracle, slide_attrition_counts)
        slide_rows.append(
            {
                "slide_id": slide_dir.name,
                "iteration": iteration_dir.name,
                "gt_available": gt_available,
                "dominant_loss_stage": dominant_loss_stage,
                "native_object_count": int(accounting.get("native_object_count", 0)),
                "raster_region_count": int(accounting.get("raster_region_count", 0)),
                "raster_area_ratio": float(accounting.get("raster_area_ratio", 0.0)),
                "native_area_ratio": float(accounting.get("native_area_ratio", 0.0)),
                "raster_native_overlap_area_ratio": float(accounting.get("raster_native_overlap_area_ratio", 0.0)),
                "dropped_hypothesis_count": int(accounting.get("dropped_hypothesis_count", 0)),
                "grow_fallback_hypothesis_count": int(fallback_accounting.get("grow_fallback_hypothesis_count", 0)),
                "source_attribution": source_attribution,
                "ablation_flags": ablation_flags,
                "motif_accounting": motif_accounting,
                "oracle_stages": stage_oracle,
                "attrition_counts": slide_attrition_counts,
                "geometry_audit_status_counts": slide_geometry_status_counts,
            }
        )

    slide_count = len(slide_rows)
    stage_oracle_summary = {
        stage: {
            "recoverable_count": totals["recoverable_count"],
            "ground_truth_count": totals["ground_truth_count"],
            "recoverable_ratio": 0.0 if totals["ground_truth_count"] == 0 else totals["recoverable_count"] / totals["ground_truth_count"],
        }
        for stage, totals in sorted(oracle_totals.items())
    }
    summary = {
        "status": "ok",
        "benchmark_root": str(root),
        "slide_count": slide_count,
        "gt_backed_slide_count": gt_backed_slide_count,
        "gt_unavailable_slide_count": gt_unavailable_slide_count,
        "gt_coverage_notice": gt_coverage_notice(gt_backed_slide_count),
        "stage_oracle": stage_oracle_summary,
        "stage_oracle_by_source_bucket": {stage: dict(counter) for stage, counter in sorted(oracle_source_totals.items())},
        "stage_attrition": dict(attrition_totals),
        "failure_taxonomy": {
            "ground_truth": dict(gt_failure_counts),
            "predictions": dict(pred_failure_counts),
        },
        "geometry_audit_status_counts": dict(geometry_audit_status_totals),
        "native_object_count": native_object_count,
        "raster_region_count": raster_region_count,
        "dropped_hypothesis_count": dropped_hypothesis_count,
        "grow_fallback_hypothesis_count": grow_fallback_count,
        "native_area_ratio_mean": 0.0 if slide_count == 0 else total_native_area_ratio / slide_count,
        "raster_area_ratio_mean": 0.0 if slide_count == 0 else total_raster_area_ratio / slide_count,
        "raster_native_overlap_area_ratio_mean": 0.0 if slide_count == 0 else total_raster_native_overlap_ratio / slide_count,
        "selection_count_by_source_bucket": dict(selection_source_totals),
        "native_emit_count_by_source_bucket": dict(emit_source_totals),
        "final_matched_gt_by_source_bucket": dict(final_match_source_totals),
        "ablation_counts": dict(ablation_totals),
        "motif_accounting": {family: dict(counter) for family, counter in sorted(motif_family_totals.items())},
        "dominant_loss_stage": dominant_stage_from_aggregate(stage_oracle_summary, dict(attrition_totals)),
    }
    return summary, slide_rows


def dominant_stage_from_oracle(stage_oracle: dict[str, object]) -> str | None:
    ordered = [(stage, payload) for stage, payload in sorted(stage_oracle.items()) if isinstance(payload, dict)]
    best_stage = None
    best_drop = 0.0
    previous_ratio = None
    for stage, payload in ordered:
        ratio = float(payload.get("recoverable_ratio", 0.0))
        if previous_ratio is not None:
            drop = previous_ratio - ratio
            if drop > best_drop:
                best_drop = drop
                best_stage = stage
        previous_ratio = ratio
    if best_stage is None and ordered:
        best_stage = min(ordered, key=lambda item: float(item[1].get("recoverable_ratio", 0.0)))[0]
    return best_stage


def dominant_stage_from_aggregate(stage_oracle: dict[str, dict[str, float]], attrition: dict[str, int]) -> str | None:
    if attrition:
        return max(attrition.items(), key=lambda item: item[1])[0]
    ordered = [(stage, payload) for stage, payload in sorted(stage_oracle.items())]
    best_stage = None
    best_drop = 0.0
    previous_ratio = None
    for stage, payload in ordered:
        ratio = float(payload.get("recoverable_ratio", 0.0))
        if previous_ratio is not None:
            drop = previous_ratio - ratio
            if drop > best_drop:
                best_drop = drop
                best_stage = stage
        previous_ratio = ratio
    if best_stage is None and ordered:
        best_stage = min(ordered, key=lambda item: float(item[1].get("recoverable_ratio", 0.0)))[0]
    return best_stage


def write_benchmark_summary(benchmark_root: str | Path) -> tuple[Path, Path, dict[str, object], list[dict[str, object]]]:
    root = Path(benchmark_root)
    summary, rows = summarize_benchmark(root)
    summary_path = root / "benchmark_stage_summary.json"
    rollup_path = root / "benchmark_stage_rollup.jsonl"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    with rollup_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return summary_path, rollup_path, summary, rows


def format_benchmark_summary(summary: dict[str, object]) -> str:
    return (
        f"slides={summary.get('slide_count', 0)} "
        f"gt_backed={summary.get('gt_backed_slide_count', 0)} "
        f"gt_unavailable={summary.get('gt_unavailable_slide_count', 0)} "
        f"gt_notice={summary.get('gt_coverage_notice')} "
        f"dominant_loss_stage={summary.get('dominant_loss_stage')} "
        f"native={summary.get('native_object_count', 0)} "
        f"raster={summary.get('raster_region_count', 0)} "
        f"raster_area_mean={summary.get('raster_area_ratio_mean', 0.0):.3f}"
    )


def ablation_key(flags: dict[str, object]) -> str:
    grow = "grow" if bool(flags.get("grow_fallback_enabled", True)) else "no-grow"
    motifs = "motifs" if bool(flags.get("motifs_enabled", True)) else "no-motifs"
    return f"{grow}+{motifs}"


def gt_coverage_notice(gt_backed_slide_count: int) -> str | None:
    if gt_backed_slide_count <= 0:
        return "no_gt_backed_slides"
    if gt_backed_slide_count == 1:
        return "single_gt_backed_slide_only"
    if gt_backed_slide_count < 3:
        return "low_gt_backed_coverage"
    return None
