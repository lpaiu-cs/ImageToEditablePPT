from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.combine_dataset_manifests import combine_manifests


def _write_manifest(root: Path, *, seed: int, sample_id: str, split: str) -> Path:
    root.mkdir()
    (root / split).mkdir()
    (root / split / f"{sample_id}.png").write_bytes(b"png")
    (root / split / f"{sample_id}.json").write_text("{}", encoding="utf-8")
    manifest = {
        "schema_version": "phase7_ml_annotation_v1",
        "generator": {
            "renderer": "pil_raster_v1",
            "seed": seed,
            "count": 1,
            "image_size": {"width": 640, "height": 360},
        },
        "samples": [
            {
                "id": sample_id,
                "split": split,
                "family": "orthogonal_flow",
                "image": f"{split}/{sample_id}.png",
                "annotation": f"{split}/{sample_id}.json",
                "pptx": None,
            }
        ],
    }
    path = root / "dataset_manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_combine_manifests_rebases_paths_and_binds_sources(tmp_path):
    first = _write_manifest(tmp_path / "pil", seed=1, sample_id="sample:1", split="train")
    second = _write_manifest(tmp_path / "soffice", seed=2, sample_id="sample:2", split="test")
    output_dir = tmp_path / "mixed"

    combined = combine_manifests([first, second], output_dir)

    assert combined["split_counts"] == {"test": 1, "train": 1}
    assert combined["family_counts"] == {"orthogonal_flow": 2}
    assert combined["generator"]["renderer"] == "mixed"
    assert len(combined["generator"]["sources"]) == 2
    assert all(len(source["sha256"]) == 64 for source in combined["generator"]["sources"])
    for sample in combined["samples"]:
        assert (output_dir / sample["image"]).resolve().exists()
        assert (output_dir / sample["annotation"]).resolve().exists()


def test_combine_manifests_rejects_duplicate_ids(tmp_path):
    first = _write_manifest(tmp_path / "one", seed=1, sample_id="duplicate", split="train")
    second = _write_manifest(tmp_path / "two", seed=2, sample_id="duplicate", split="val")

    with pytest.raises(ValueError, match="duplicate sample id"):
        combine_manifests([first, second], tmp_path / "mixed")
