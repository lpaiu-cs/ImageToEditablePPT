"""Create the Phase 16.0 freeze lock, refusing incomplete or dirty evidence."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path
from statistics import median
import subprocess
import sys
from typing import Any

from image_to_editable_ppt.ml.phase16.artifacts import (
    bound_file_set_digest,
    pptx_semantic_digest,
)
from image_to_editable_ppt.ml.phase16.validation import (
    sha256_file,
    validate_phase16_manifests,
)


LOCK_SCHEMA = "phase16_experiment_lock_v1"
CALIBRATION_SCHEMA = "phase16_operation_time_calibration_v1"
BASELINE_COMMIT = "3ae7caf2c6160bd84e4bc851212b22c536cb3348"


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _file_binding(path: Path, root: Path) -> dict[str, object]:
    return {"path": _relative(path, root), "sha256": sha256_file(path)}


def _git_output(root: Path, *arguments: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(root), *arguments], text=True, stderr=subprocess.STDOUT
    ).strip()


def _package_versions() -> dict[str, str | None]:
    result: dict[str, str | None] = {}
    for package in (
        "numpy",
        "opencv-python-headless",
        "Pillow",
        "python-pptx",
        "rapidocr-onnxruntime",
    ):
        try:
            result[package] = version(package)
        except PackageNotFoundError:
            result[package] = None
    return result


def validate_calibration(
    protocol_path: Path, calibration_path: Path
) -> tuple[dict[str, object] | None, list[str]]:
    """Validate measured human operation times and every file they bind."""

    blockers: list[str] = []
    if not calibration_path.is_file():
        return None, [f"human operation-time calibration is missing: {calibration_path}"]
    protocol = _load(protocol_path)
    calibration = _load(calibration_path)
    if calibration.get("schema_version") != CALIBRATION_SCHEMA:
        blockers.append("unsupported operation-time calibration schema")
    if calibration.get("status") != "completed":
        blockers.append("operation-time calibration status is not completed")
    protocol_sha = sha256_file(protocol_path)
    if calibration.get("protocol_sha256") != protocol_sha:
        blockers.append("operation-time calibration protocol hash mismatch")
    minimum = int(protocol["minimum_repetitions_per_operation"])
    if calibration.get("minimum_repetitions_per_operation") != minimum:
        blockers.append("operation-time calibration repetition contract mismatch")
    expected = {str(item["id"]) for item in protocol["operations"]}
    operation_times = calibration.get("operation_times")
    if not isinstance(operation_times, dict) or set(operation_times) != expected:
        blockers.append("operation-time calibration operation set mismatch")
    else:
        for operation_id in sorted(expected):
            record = operation_times[operation_id]
            if not isinstance(record, dict):
                blockers.append(f"{operation_id}: calibration record is not an object")
                continue
            raw = record.get("raw_seconds")
            if not isinstance(raw, list) or len(raw) < minimum:
                blockers.append(f"{operation_id}: fewer than {minimum} valid trials")
                continue
            try:
                seconds = [float(item) for item in raw]
                reported = float(record["median_seconds"])
            except (TypeError, ValueError, KeyError):
                blockers.append(f"{operation_id}: invalid timing values")
                continue
            if any(item <= 0.0 for item in seconds):
                blockers.append(f"{operation_id}: non-positive timing value")
            if abs(median(seconds) - reported) > 1e-6:
                blockers.append(f"{operation_id}: median does not match raw trials")
            if record.get("valid_trials") != len(seconds):
                blockers.append(f"{operation_id}: valid trial count mismatch")
    for label in ("deck", "measurements"):
        path_value = calibration.get(f"{label}_path")
        expected_sha = calibration.get(f"{label}_sha256")
        if not isinstance(path_value, str) or not path_value:
            blockers.append(f"operation-time calibration {label} path is missing")
            continue
        path = Path(path_value)
        if not path.is_file():
            blockers.append(f"operation-time calibration {label} file is missing")
        elif sha256_file(path) != expected_sha:
            blockers.append(f"operation-time calibration {label} hash mismatch")
    if not isinstance(calibration.get("participant_id"), str) or not calibration["participant_id"]:
        blockers.append("operation-time calibration participant id is missing")
    if not isinstance(calibration.get("powerpoint_version"), str) or not calibration["powerpoint_version"]:
        blockers.append("operation-time calibration PowerPoint version is missing")
    binding = {
        "path": str(calibration_path),
        "sha256": sha256_file(calibration_path),
        "status": calibration.get("status"),
        "participant_id": calibration.get("participant_id"),
        "powerpoint_version": calibration.get("powerpoint_version"),
        "operation_median_seconds": {
            operation_id: operation_times[operation_id]["median_seconds"]
            for operation_id in sorted(expected)
        }
        if isinstance(operation_times, dict) and set(operation_times) == expected
        else {},
    }
    return binding, blockers


def _validate_visual_calibration_review(path: Path, root: Path) -> list[str]:
    review = _load(path)
    blockers: list[str] = []
    if review.get("status") != "visually_accepted_before_measurement":
        blockers.append("calibration deck visual review is not accepted")
    deck = review.get("deck")
    if not isinstance(deck, dict):
        return [*blockers, "calibration visual review deck binding is missing"]
    deck_path = root / str(deck.get("path", ""))
    if not deck_path.is_file():
        blockers.append("calibration visual review deck is missing")
    else:
        if pptx_semantic_digest(deck_path) != deck.get("semantic_sha256"):
            blockers.append("calibration visual review deck semantic hash mismatch")
    renders = review.get("renders")
    if not isinstance(renders, list) or len(renders) != 9:
        blockers.append("calibration visual review must bind all nine task renders")
    else:
        for record in renders:
            render_path = root / str(record.get("path", ""))
            if not render_path.is_file() or sha256_file(render_path) != record.get("sha256"):
                blockers.append(
                    f"calibration visual review render hash mismatch: {record.get('path')}"
                )
    return blockers


def build_lock(root: Path, calibration_path: Path) -> dict[str, object]:
    root = root.resolve()
    paths = {
        "specification": root / "docs/phase16_multiscale_evidence_graph_spec.md",
        "selection": root / "benchmarks/phase16_selection_v1.json",
        "annotation_review": root / "benchmarks/phase16_annotation_review_v1.json",
        "dev_manifest": root / "benchmarks/phase16_dev_v1/manifest.json",
        "holdout_manifest": root / "benchmarks/phase16_holdout_v1/manifest.json",
        "baseline_manifest": root / "benchmarks/phase16_baseline_v1.json",
        "visual_audit_rubric": root / "benchmarks/phase16_visual_audit_rubric_v1.json",
        "calibration_protocol": root / "benchmarks/phase16_operation_time_calibration_protocol_v1.json",
        "calibration_visual_review": root
        / "benchmarks/phase16_operation_time_calibration_visual_review_v1.json",
        "candidate_bundle": root / "workbench-ml/model_bundle.candidate.json",
    }
    for label, path in paths.items():
        if not path.is_file():
            raise ValueError(f"required {label} is missing: {path}")
    validate_phase16_manifests(
        paths["dev_manifest"], paths["holdout_manifest"], root=root, require_frozen=True
    )
    baseline = _load(paths["baseline_manifest"])
    if baseline.get("baseline", {}).get("git_commit") != BASELINE_COMMIT:
        raise ValueError("baseline manifest does not bind the frozen Phase 15 commit")

    blockers = _validate_visual_calibration_review(paths["calibration_visual_review"], root)
    calibration, calibration_blockers = validate_calibration(
        paths["calibration_protocol"], calibration_path
    )
    blockers.extend(calibration_blockers)
    if calibration is not None:
        calibration_raw = _load(calibration_path)
        measured_deck = Path(str(calibration_raw.get("deck_path", "")))
        reviewed_deck = _load(paths["calibration_visual_review"]).get("deck", {})
        if (
            not measured_deck.is_file()
            or pptx_semantic_digest(measured_deck) != reviewed_deck.get("semantic_sha256")
        ):
            blockers.append("measured calibration deck differs from the visually reviewed deck")

    annotation_paths: list[Path] = []
    review_sha = sha256_file(paths["annotation_review"])
    for manifest_key in ("dev_manifest", "holdout_manifest"):
        manifest = _load(paths[manifest_key])
        for sample in manifest["samples"]:
            annotation_path = root / str(sample["annotation"])
            annotation_paths.append(annotation_path)
            annotation = _load(annotation_path)
            note_text = " ".join(str(item) for item in annotation.get("ambiguity_notes", []))
            if review_sha not in note_text:
                blockers.append(f"{sample['id']}: annotation is not bound to current visual review")
    annotation_digest = bound_file_set_digest(annotation_paths, root=root)
    baseline_annotation_digest = (
        baseline.get("dataset_bindings", {}).get("annotation_set_sha256")
    )
    if annotation_digest != baseline_annotation_digest:
        blockers.append("baseline annotation-set digest no longer matches frozen annotations")

    bundle = _load(paths["candidate_bundle"])
    checkpoint_bindings: dict[str, object] = {}
    for name, checkpoint in bundle.get("checkpoints", {}).items():
        if checkpoint is None:
            checkpoint_bindings[name] = None
            continue
        checkpoint_path = paths["candidate_bundle"].parent / str(checkpoint["path"])
        actual_sha = sha256_file(checkpoint_path)
        if actual_sha != checkpoint.get("sha256"):
            blockers.append(f"candidate bundle checkpoint hash mismatch: {name}")
        checkpoint_bindings[name] = {
            "path": _relative(checkpoint_path, root),
            "sha256": actual_sha,
            "bytes": checkpoint_path.stat().st_size,
        }

    head = _git_output(root, "rev-parse", "HEAD")
    dirty_output = _git_output(root, "status", "--porcelain", "--untracked-files=all")
    dirty_paths = [line for line in dirty_output.splitlines() if line]
    if dirty_paths:
        blockers.append("working tree is not clean; candidate Git SHA cannot bind current files")

    selection = _load(paths["selection"])
    rubric = _load(paths["visual_audit_rubric"])
    bindings = {label: _file_binding(path, root) for label, path in paths.items()}
    calibration_binding = None
    if calibration is not None:
        calibration_binding = {
            **calibration,
            "path": _relative(calibration_path, root),
        }
    return {
        "schema_version": LOCK_SCHEMA,
        "status": "frozen" if not blockers else "blocked",
        "stage": "phase16.0_preregistration_data_freeze",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git": {
            "baseline_commit": BASELINE_COMMIT,
            "candidate_preregistration_commit": head,
            "worktree_clean": not dirty_paths,
            "dirty_paths": dirty_paths,
        },
        "file_bindings": bindings,
        "annotation_set_sha256": annotation_digest,
        "candidate_bundle": {
            "path": bindings["candidate_bundle"]["path"],
            "sha256": bindings["candidate_bundle"]["sha256"],
            "status": bundle.get("status"),
            "settings": bundle.get("settings"),
            "checkpoints": checkpoint_bindings,
        },
        "seeds": {
            "sample_selection": selection.get("pool", {}).get("selection_seed"),
            "visual_ab_display_order": rubric.get("display_order_seed"),
        },
        "environment": {
            "python": sys.version.split()[0],
            "packages": _package_versions(),
            "powerpoint": baseline.get("baseline", {}).get("powerpoint_version"),
        },
        "operation_time_calibration": calibration_binding,
        "algorithm": {
            "status": "not_started",
            "tuning_allowed_only_when_lock_status": "frozen",
        },
        "blockers": blockers,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--calibration",
        type=Path,
        default=Path("artifacts/phase16-operation-calibration/operation_time_calibration.json"),
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--pending",
        action="store_true",
        help="write a diagnostic pending lock even when blockers remain",
    )
    args = parser.parse_args()
    root = args.root.resolve()
    calibration = args.calibration if args.calibration.is_absolute() else root / args.calibration
    try:
        payload = build_lock(root, calibration)
        if payload["blockers"] and not args.pending:
            raise ValueError("; ".join(str(item) for item in payload["blockers"]))
        default_output = (
            Path("artifacts/phase16-experiment-lock.pending.json")
            if args.pending
            else Path("benchmarks/phase16_experiment.lock.json")
        )
        output_arg = args.output or default_output
        output = output_arg if output_arg.is_absolute() else root / output_arg
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(
            json.dumps(
                {"output": str(output), "status": payload["status"], "blockers": payload["blockers"]},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0 if not payload["blockers"] else 3
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        parser.error(str(error))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
