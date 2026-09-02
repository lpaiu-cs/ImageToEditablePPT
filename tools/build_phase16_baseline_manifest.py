"""Freeze the exact Phase 15 outputs used as the Phase 16 comparison baseline."""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import subprocess
from typing import Any, Mapping

from image_to_editable_ppt.ml.phase16.artifacts import (
    bound_file_set_digest,
    pptx_semantic_digest,
    pptx_shape_counts,
)
from image_to_editable_ppt.ml.phase16.validation import (
    sha256_file,
    validate_phase16_manifests,
)


BASELINE_COMMIT = "3ae7caf2c6160bd84e4bc851212b22c536cb3348"
BASELINE_BUNDLE_SHA256 = "d9d232c44eed893e7c63baa30059f1728da9946077467d2d2e6a664f740023ac"


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _repo_relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _git_head(worktree: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(worktree), "rev-parse", "HEAD"], text=True
    ).strip()


def _summary(records: list[Mapping[str, object]]) -> dict[str, object]:
    grouped: dict[tuple[str, str], list[Mapping[str, object]]] = defaultdict(list)
    for record in records:
        grouped[(str(record["split"]), str(record["kind"]))].append(record)
    result: dict[str, object] = {}
    for (split, kind), items in sorted(grouped.items()):
        counts = [item["shape_counts"] for item in items]
        blank = sum(bool(item["blank"]) for item in counts)  # type: ignore[index]
        result.setdefault(split, {})[kind] = {  # type: ignore[index]
            "samples": len(items),
            "blank": blank,
            "nonblank": len(items) - blank,
            "native_objects": sum(int(item["total"]) for item in counts),  # type: ignore[index]
            "semantic_connectors": sum(
                int(item["semantic_connectors"]) for item in counts  # type: ignore[index]
            ),
        }
    return result


def build_baseline_manifest(
    *,
    root: Path,
    dev_manifest_path: Path,
    holdout_manifest_path: Path,
    baseline_worktree: Path,
    bundle_path: Path,
    pptx_dir: Path,
    render_manifest_path: Path,
    regenerated_probe_pptx: Path,
    frozen_probe_pptx: Path,
    regenerated_probe_render: Path,
    frozen_probe_render: Path,
) -> dict[str, object]:
    root = root.resolve()
    validate_phase16_manifests(
        dev_manifest_path, holdout_manifest_path, root=root, require_frozen=True
    )
    baseline_head = _git_head(baseline_worktree)
    if baseline_head != BASELINE_COMMIT:
        raise ValueError(f"baseline worktree is {baseline_head}, expected {BASELINE_COMMIT}")
    bundle_sha = sha256_file(bundle_path)
    if bundle_sha != BASELINE_BUNDLE_SHA256:
        raise ValueError(f"candidate bundle is {bundle_sha}, expected {BASELINE_BUNDLE_SHA256}")

    bundle = _load_json(bundle_path)
    render_manifest = _load_json(render_manifest_path)
    render_records_raw = render_manifest.get("records")
    if not isinstance(render_records_raw, list):
        raise ValueError("render manifest records must be a list")
    render_records = {str(record["id"]): record for record in render_records_raw}

    manifests = [
        ("dev", dev_manifest_path, _load_json(dev_manifest_path)),
        ("holdout", holdout_manifest_path, _load_json(holdout_manifest_path)),
    ]
    annotation_paths: list[Path] = []
    records: list[dict[str, object]] = []
    expected_ids: set[str] = set()
    for split, _manifest_path, manifest in manifests:
        for sample in manifest["samples"]:
            sample_id = str(sample["id"])
            expected_ids.add(sample_id)
            pptx_path = (pptx_dir / f"{sample_id}.pptx").resolve()
            annotation_path = (root / str(sample["annotation"])).resolve()
            source_path = (root / str(sample["path"])).resolve()
            annotation_paths.append(annotation_path)
            if sample_id not in render_records:
                raise ValueError(f"missing PowerPoint render for {sample_id}")
            render_record = render_records[sample_id]
            render_path = Path(str(render_record["render_path"])).resolve()
            if sha256_file(pptx_path) != str(render_record["pptx_sha256"]):
                raise ValueError(f"PowerPoint manifest PPTX hash mismatch for {sample_id}")
            if sha256_file(render_path) != str(render_record["render_sha256"]):
                raise ValueError(f"PowerPoint manifest PNG hash mismatch for {sample_id}")
            records.append(
                {
                    "id": sample_id,
                    "split": split,
                    "kind": sample["kind"],
                    "stratum": sample["stratum"],
                    "low_connectivity": bool(sample.get("low_connectivity", False)),
                    "source": {
                        "path": str(sample["path"]),
                        "sha256": sha256_file(source_path),
                    },
                    "annotation": {
                        "path": str(sample["annotation"]),
                        "sha256": sha256_file(annotation_path),
                    },
                    "pptx": {
                        "path": _repo_relative(pptx_path, root),
                        "sha256": sha256_file(pptx_path),
                        "semantic_sha256": pptx_semantic_digest(pptx_path),
                    },
                    "powerpoint_render": {
                        "path": _repo_relative(render_path, root),
                        "sha256": sha256_file(render_path),
                        "width": int(render_record["width"]),
                        "height": int(render_record["height"]),
                    },
                    "shape_counts": pptx_shape_counts(pptx_path),
                }
            )
    extra_render_ids = set(render_records) - expected_ids
    if extra_render_ids:
        raise ValueError(f"render manifest has unexpected ids: {sorted(extra_render_ids)}")

    regenerated_semantic = pptx_semantic_digest(regenerated_probe_pptx)
    frozen_semantic = pptx_semantic_digest(frozen_probe_pptx)
    regenerated_render_sha = sha256_file(regenerated_probe_render)
    frozen_render_sha = sha256_file(frozen_probe_render)
    if regenerated_semantic != frozen_semantic:
        raise ValueError("regenerated input.pptx does not match the frozen semantic baseline")
    if regenerated_render_sha != frozen_render_sha:
        raise ValueError("regenerated PowerPoint render does not match the frozen pixels")

    checkpoint_bindings: dict[str, object] = {}
    for name, checkpoint in bundle.get("checkpoints", {}).items():
        if checkpoint is not None:
            checkpoint_bindings[name] = {
                "path": checkpoint["path"],
                "sha256": checkpoint["sha256"],
                "bytes": checkpoint["bytes"],
            }

    return {
        "schema_version": "phase16_baseline_manifest_v1",
        "frozen_at": "2026-09-02",
        "baseline": {
            "phase": 15,
            "git_commit": baseline_head,
            "candidate_bundle": {
                "path": _repo_relative(bundle_path, root),
                "sha256": bundle_sha,
                "status": bundle.get("status"),
                "settings": bundle.get("settings"),
                "checkpoints": checkpoint_bindings,
            },
            "powerpoint_version": render_manifest.get("powerpoint_version"),
            "normalized_width": 768,
        },
        "input_probe_reproduction": {
            "source": {"path": "input.png", "sha256": sha256_file(root / "input.png")},
            "regenerated_pptx": {
                "path": _repo_relative(regenerated_probe_pptx, root),
                "sha256": sha256_file(regenerated_probe_pptx),
                "semantic_sha256": regenerated_semantic,
            },
            "frozen_pptx": {
                "path": _repo_relative(frozen_probe_pptx, root),
                "sha256": sha256_file(frozen_probe_pptx),
                "semantic_sha256": frozen_semantic,
            },
            "semantic_match": True,
            "regenerated_powerpoint_render": {
                "path": _repo_relative(regenerated_probe_render, root),
                "sha256": regenerated_render_sha,
            },
            "frozen_powerpoint_render": {
                "path": _repo_relative(frozen_probe_render, root),
                "sha256": frozen_render_sha,
            },
            "powerpoint_pixel_match": True,
        },
        "dataset_bindings": {
            "dev_manifest": {
                "path": _repo_relative(dev_manifest_path, root),
                "sha256": sha256_file(dev_manifest_path),
            },
            "holdout_manifest": {
                "path": _repo_relative(holdout_manifest_path, root),
                "sha256": sha256_file(holdout_manifest_path),
            },
            "annotation_set_sha256": bound_file_set_digest(annotation_paths, root=root),
            "powerpoint_render_manifest": {
                "path": _repo_relative(render_manifest_path, root),
                "sha256": sha256_file(render_manifest_path),
            },
        },
        "summary": _summary(records),
        "records": sorted(records, key=lambda item: str(item["id"])),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--dev-manifest", type=Path, default=Path("benchmarks/phase16_dev_v1/manifest.json"))
    parser.add_argument("--holdout-manifest", type=Path, default=Path("benchmarks/phase16_holdout_v1/manifest.json"))
    parser.add_argument("--baseline-worktree", type=Path, default=Path("artifacts/phase16-baseline-src"))
    parser.add_argument("--bundle", type=Path, default=Path("workbench-ml/model_bundle.candidate.json"))
    parser.add_argument("--pptx-dir", type=Path, default=Path("artifacts/phase16-baseline-v1/official"))
    parser.add_argument("--render-manifest", type=Path, default=Path("artifacts/phase16-baseline-v1/official-renders/powerpoint_render_manifest.json"))
    parser.add_argument("--regenerated-probe-pptx", type=Path, default=Path("artifacts/phase16-baseline-v1/input.pptx"))
    parser.add_argument("--frozen-probe-pptx", type=Path, default=Path("artifacts/visual-first/boundary-v3/input.pptx"))
    parser.add_argument("--regenerated-probe-render", type=Path, default=Path("artifacts/phase16-baseline-v1/input.powerpoint.png"))
    parser.add_argument("--frozen-probe-render", type=Path, default=Path("artifacts/visual-first/boundary-v3/input.png"))
    parser.add_argument("--output", type=Path, default=Path("benchmarks/phase16_baseline_v1.json"))
    args = parser.parse_args()
    root = args.root.resolve()

    def resolved(path: Path) -> Path:
        return path if path.is_absolute() else root / path

    payload = build_baseline_manifest(
        root=root,
        dev_manifest_path=resolved(args.dev_manifest),
        holdout_manifest_path=resolved(args.holdout_manifest),
        baseline_worktree=resolved(args.baseline_worktree),
        bundle_path=resolved(args.bundle),
        pptx_dir=resolved(args.pptx_dir),
        render_manifest_path=resolved(args.render_manifest),
        regenerated_probe_pptx=resolved(args.regenerated_probe_pptx),
        frozen_probe_pptx=resolved(args.frozen_probe_pptx),
        regenerated_probe_render=resolved(args.regenerated_probe_render),
        frozen_probe_render=resolved(args.frozen_probe_render),
    )
    output = resolved(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "summary": payload["summary"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
