from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image
import pytest

from image_to_editable_ppt.ml.phase16.validation import (
    ValidationError,
    validate_phase16_manifest,
    validate_phase16_manifests,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _annotation(
    *,
    sample_id: str,
    image_path: str,
    image_sha256: str,
    kind: str,
    objects: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "schema_version": "phase16_annotation_v2",
        "sample_id": sample_id,
        "image": {
            "path": image_path,
            "sha256": image_sha256,
            "width": 64,
            "height": 48,
        },
        "kind": kind,
        "objects": objects or [],
        "connectors": [],
        "excluded_regions": [],
        "allowed_omissions": [],
        "ambiguity_notes": [],
        "review": {
            "status": "resolved",
            "passes": [
                {
                    "pass_id": "geometry-pass",
                    "reviewer": "fixture",
                    "completed_at": "2026-09-02T00:00:00Z",
                    "focus": ["object_roles"],
                },
                {
                    "pass_id": "relations-pass",
                    "reviewer": "fixture",
                    "completed_at": "2026-09-02T00:01:00Z",
                    "focus": ["connector_endpoints", "excluded_regions"],
                },
            ],
        },
    }


def _write_split(
    root: Path,
    *,
    split: str,
    sample_id: str,
    kind: str,
    source_group: str,
    perceptual_hash: str,
    objects: list[dict[str, object]] | None = None,
) -> Path:
    image_relative = f"data/{split}/{sample_id}.png"
    annotation_relative = f"benchmarks/{split}/annotations/{sample_id}.json"
    image_path = root / image_relative
    annotation_path = root / annotation_relative
    image_path.parent.mkdir(parents=True, exist_ok=True)
    annotation_path.parent.mkdir(parents=True, exist_ok=True)
    color_seed = hashlib.sha256(sample_id.encode("utf-8")).digest()
    Image.new("RGB", (64, 48), tuple(color_seed[:3])).save(image_path)
    image_sha = _sha256(image_path)
    annotation_path.write_text(
        json.dumps(
            _annotation(
                sample_id=sample_id,
                image_path=image_relative,
                image_sha256=image_sha,
                kind=kind,
                objects=objects,
            )
        ),
        encoding="utf-8",
    )
    manifest = {
        "schema_version": "phase16_benchmark_manifest_v1",
        "split": "dev" if split == "phase16_dev_v1" else "holdout",
        "created_at": "2026-09-02",
        "samples": [
            {
                "id": sample_id,
                "kind": kind,
                "stratum": "simple_direct_orthogonal" if kind == "diagram" else "plot",
                "low_connectivity": False,
                "path": image_relative,
                "annotation": annotation_relative,
                "sha256": image_sha,
                "perceptual_hash": perceptual_hash,
                "source_group": source_group,
                "source": {
                    "type": "huggingface_parquet",
                    "dataset": "fixture/dataset",
                    "revision": "0123456789abcdef",
                    "shard": f"{sample_id}.parquet",
                    "row": 0,
                    "sha256": "a" * 64,
                },
            }
        ],
    }
    manifest_path = root / f"benchmarks/{split}/manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path


def test_phase16_manifests_bind_images_and_isolate_splits(tmp_path: Path) -> None:
    dev = _write_split(
        tmp_path,
        split="phase16_dev_v1",
        sample_id="dev-1",
        kind="non_diagram",
        source_group="paper-dev",
        perceptual_hash="0000000000000000",
    )
    holdout = _write_split(
        tmp_path,
        split="phase16_holdout_v1",
        sample_id="holdout-1",
        kind="non_diagram",
        source_group="paper-holdout",
        perceptual_hash="ffffffffffffffff",
    )

    report = validate_phase16_manifests(dev, holdout, root=tmp_path)

    assert report["dev"]["counts"] == {"non_diagram": 1}
    assert report["holdout"]["samples"] == 1


def test_phase16_manifest_rejects_containment_cycle(tmp_path: Path) -> None:
    objects = [
        {
            "id": "a",
            "role": "container",
            "shape_kind": "rectangle",
            "bbox": {"x0": 1, "y0": 1, "x1": 60, "y1": 44},
            "parent_id": "b",
            "importance": "core",
            "label": None,
            "ambiguity_note": None,
        },
        {
            "id": "b",
            "role": "container",
            "shape_kind": "rectangle",
            "bbox": {"x0": 1, "y0": 1, "x1": 60, "y1": 44},
            "parent_id": "a",
            "importance": "core",
            "label": None,
            "ambiguity_note": None,
        },
    ]
    manifest = _write_split(
        tmp_path,
        split="phase16_dev_v1",
        sample_id="cycle",
        kind="diagram",
        source_group="paper-cycle",
        perceptual_hash="0000000000000000",
        objects=objects,
    )

    with pytest.raises(ValidationError, match="containment cycle"):
        validate_phase16_manifest(manifest, root=tmp_path)


def test_phase16_manifests_reject_perceptual_near_duplicate(tmp_path: Path) -> None:
    dev = _write_split(
        tmp_path,
        split="phase16_dev_v1",
        sample_id="dev-near",
        kind="non_diagram",
        source_group="paper-dev",
        perceptual_hash="0000000000000000",
    )
    holdout = _write_split(
        tmp_path,
        split="phase16_holdout_v1",
        sample_id="holdout-near",
        kind="non_diagram",
        source_group="paper-holdout",
        perceptual_hash="0000000000000001",
    )

    with pytest.raises(ValidationError, match="perceptual near-duplicate"):
        validate_phase16_manifests(dev, holdout, root=tmp_path)


def test_phase16_frozen_contract_requires_minimum_sample_count(tmp_path: Path) -> None:
    manifest = _write_split(
        tmp_path,
        split="phase16_dev_v1",
        sample_id="small-dev",
        kind="non_diagram",
        source_group="paper-small",
        perceptual_hash="0000000000000000",
    )

    with pytest.raises(ValidationError, match="at least 20"):
        validate_phase16_manifest(manifest, root=tmp_path, require_frozen=True)
