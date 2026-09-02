"""Materialize visually selected Phase 16 splits and annotation-v2 drafts."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
from typing import Mapping


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_object(path: Path) -> Mapping[str, object]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError(f"{path} must contain a JSON object")
    return raw


def _excluded_kind(stratum: str) -> str:
    return {
        "plot": "plot",
        "table": "table",
        "application_screenshot": "application_screenshot",
        "photo": "photo",
        "multi_panel_illustration": "illustration",
    }[stratum]


def _annotation_draft(
    *,
    sample_id: str,
    image_path: str,
    image_sha256: str,
    width: int,
    height: int,
    kind: str,
    stratum: str,
) -> dict[str, object]:
    excluded_regions: list[dict[str, object]] = []
    if kind == "non_diagram":
        excluded_regions.append(
            {
                "id": "excluded:scene",
                "kind": _excluded_kind(stratum),
                "bbox": {"x0": 0, "y0": 0, "x1": width, "y1": height},
                "note": f"Whole scene was visually classified as non-diagram hard negative: {stratum}.",
            }
        )
    return {
        "schema_version": "phase16_annotation_v2",
        "sample_id": sample_id,
        "image": {
            "path": image_path,
            "sha256": image_sha256,
            "width": width,
            "height": height,
        },
        "kind": kind,
        "objects": [],
        "connectors": [],
        "excluded_regions": excluded_regions,
        "allowed_omissions": (
            [
                "icons, logos, photos, illustrations, decoration, and unsupported free curves",
                "secondary structure explicitly marked optional during manual annotation",
            ]
            if kind == "diagram"
            else ["all scene content; expected PowerPoint output is blank"]
        ),
        "ambiguity_notes": [
            "Draft created from the frozen visual selection. Structural annotation is not yet complete."
        ],
        "review": {
            "status": "draft",
            "passes": [
                {
                    "pass_id": "visual-selection",
                    "reviewer": "gpt-5.6-sol",
                    "completed_at": "2026-09-02T00:00:00+09:00",
                    "focus": ["scene_kind", "split_stratum"],
                }
            ],
        },
    }


def prepare_splits(
    selection_path: Path,
    *,
    root: Path,
    allow_update: bool = False,
) -> dict[str, object]:
    root = root.resolve()
    selection_path = selection_path.resolve()
    selection = _load_object(selection_path)
    if selection.get("schema_version") != "phase16_visual_selection_v1":
        raise ValueError("unsupported Phase 16 visual selection schema")
    pool_binding = selection.get("pool")
    if not isinstance(pool_binding, Mapping):
        raise ValueError("selection has no pool binding")
    pool_path_value = pool_binding.get("path")
    expected_pool_sha = pool_binding.get("sha256")
    if not isinstance(pool_path_value, str) or not isinstance(expected_pool_sha, str):
        raise ValueError("selection pool path/SHA binding is incomplete")
    pool_path = (root / pool_path_value).resolve()
    actual_pool_sha = _sha256(pool_path)
    if actual_pool_sha != expected_pool_sha:
        raise ValueError(f"sample-pool SHA mismatch: {actual_pool_sha}")
    pool = _load_object(pool_path)
    records_raw = pool.get("records")
    if not isinstance(records_raw, list):
        raise ValueError("sample pool has no record list")
    by_pool_id: dict[str, Mapping[str, object]] = {}
    for record in records_raw:
        if not isinstance(record, Mapping) or not isinstance(record.get("pool_id"), str):
            raise ValueError("invalid sample-pool record")
        by_pool_id[str(record["pool_id"])] = record

    splits_raw = selection.get("splits")
    if not isinstance(splits_raw, Mapping):
        raise ValueError("selection has no splits")
    summary: dict[str, object] = {
        "selection": str(selection_path),
        "selection_sha256": _sha256(selection_path),
        "pool_sha256": actual_pool_sha,
        "splits": {},
    }
    seen_pool_ids: set[str] = set()
    for split in ("dev", "holdout"):
        split_selection = splits_raw.get(split)
        if not isinstance(split_selection, Mapping):
            raise ValueError(f"selection has no {split} split")
        benchmark_dir = root / "benchmarks" / f"phase16_{split}_v1"
        annotation_dir = benchmark_dir / "annotations"
        data_dir = root / "data" / f"phase16_{split}_v1"
        manifest_path = benchmark_dir / "manifest.json"
        if manifest_path.exists() and not allow_update:
            raise ValueError(f"refusing to overwrite {manifest_path}; pass --allow-update")
        annotation_dir.mkdir(parents=True, exist_ok=True)
        data_dir.mkdir(parents=True, exist_ok=True)
        samples: list[dict[str, object]] = []
        counts: dict[str, int] = {}
        for kind in ("diagram", "non_diagram"):
            chosen = split_selection.get(kind)
            if not isinstance(chosen, list):
                raise ValueError(f"selection {split}.{kind} must be a list")
            counts[kind] = len(chosen)
            for decision in chosen:
                if not isinstance(decision, Mapping):
                    raise ValueError(f"selection {split}.{kind} contains a non-object")
                pool_id = decision.get("pool_id")
                stratum = decision.get("stratum")
                if not isinstance(pool_id, str) or not isinstance(stratum, str):
                    raise ValueError(f"selection {split}.{kind} has invalid pool id/stratum")
                if pool_id in seen_pool_ids:
                    raise ValueError(f"pool sample selected more than once: {pool_id}")
                seen_pool_ids.add(pool_id)
                record = by_pool_id.get(pool_id)
                if record is None:
                    raise ValueError(f"selection references missing pool sample {pool_id}")
                source_path_value = record.get("path")
                if not isinstance(source_path_value, str):
                    raise ValueError(f"pool sample {pool_id} has no image path")
                source_image = (pool_path.parent / source_path_value).resolve()
                sample_id = f"phase16-{split}-{pool_id.lower()}"
                image_relative = f"data/phase16_{split}_v1/{sample_id}.png"
                annotation_relative = (
                    f"benchmarks/phase16_{split}_v1/annotations/{sample_id}.json"
                )
                target_image = root / image_relative
                shutil.copyfile(source_image, target_image)
                actual_image_sha = _sha256(target_image)
                if actual_image_sha != record.get("sha256"):
                    raise ValueError(f"pool image SHA mismatch for {pool_id}")
                width = record.get("width")
                height = record.get("height")
                if not isinstance(width, int) or not isinstance(height, int):
                    raise ValueError(f"pool sample {pool_id} has invalid dimensions")
                annotation_path = root / annotation_relative
                if not annotation_path.exists() or allow_update:
                    annotation_path.write_text(
                        json.dumps(
                            _annotation_draft(
                                sample_id=sample_id,
                                image_path=image_relative,
                                image_sha256=actual_image_sha,
                                width=width,
                                height=height,
                                kind=kind,
                                stratum=stratum,
                            ),
                            indent=2,
                        )
                        + "\n",
                        encoding="utf-8",
                    )
                source = record.get("source")
                if not isinstance(source, Mapping):
                    raise ValueError(f"pool sample {pool_id} has no source binding")
                sample = {
                    "id": sample_id,
                    "pool_id": pool_id,
                    "kind": kind,
                    "stratum": stratum,
                    "low_connectivity": bool(decision.get("low_connectivity", False)),
                    "path": image_relative,
                    "annotation": annotation_relative,
                    "caption": record.get("caption", ""),
                    "file_name": record.get("file_name", ""),
                    "sha256": actual_image_sha,
                    "perceptual_hash": record.get("perceptual_hash"),
                    "source_group": record.get("source_group"),
                    "redistribution": "external_image_not_committed; upstream license not declared",
                    "source": dict(source),
                }
                samples.append(sample)
        manifest = {
            "schema_version": "phase16_benchmark_manifest_v1",
            "created_at": "2026-09-02",
            "split": split,
            "purpose": (
                "Development split frozen before Phase 16 algorithm tuning."
                if split == "dev"
                else "One-shot confirmatory holdout frozen before Phase 16 algorithm tuning."
            ),
            "selection": {
                "path": str(selection_path.relative_to(root)).replace("\\", "/"),
                "sha256": _sha256(selection_path),
                "pool_sha256": actual_pool_sha,
            },
            "redistribution": "External images are materialized locally and are not committed.",
            "samples": samples,
        }
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        summary["splits"][split] = {
            "manifest": str(manifest_path.relative_to(root)).replace("\\", "/"),
            "manifest_sha256": _sha256(manifest_path),
            "counts": counts,
        }
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--selection",
        type=Path,
        default=Path("benchmarks/phase16_selection_v1.json"),
    )
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--allow-update", action="store_true")
    args = parser.parse_args(argv)
    try:
        summary = prepare_splits(
            args.selection,
            root=args.root,
            allow_update=args.allow_update,
        )
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        parser.error(str(error))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
