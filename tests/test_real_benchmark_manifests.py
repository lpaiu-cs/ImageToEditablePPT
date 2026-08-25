from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load(relative: str) -> dict[str, object]:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def _external_keys(manifest: dict[str, object]) -> set[tuple[str, str, int]]:
    keys: set[tuple[str, str, int]] = set()
    for sample in manifest["samples"]:
        source = sample["source"]
        if source["type"] == "huggingface_parquet":
            keys.add((source["revision"], source["shard"], int(source["row"])))
    return keys


def test_real_benchmark_manifests_have_conservative_bounds_and_hashes() -> None:
    for relative in ("benchmarks/real_v1/manifest.json", "benchmarks/real_holdout_v1/manifest.json"):
        manifest = _load(relative)
        assert manifest["schema_version"] == "real_figure_benchmark_v1"
        ids = [sample["id"] for sample in manifest["samples"]]
        assert len(ids) == len(set(ids))
        assert {sample["kind"] for sample in manifest["samples"]} == {"diagram", "non_diagram"}
        for sample in manifest["samples"]:
            assert len(sample["sha256"]) == 64
            if sample["kind"] == "diagram":
                truth = sample["ground_truth"]
                assert 0 < truth["verified_min_primitives"] <= truth["verified_max_primitives"]
                assert 0 < truth["verified_min_connectors"] <= truth["verified_max_connectors"]


def test_confirmatory_holdout_has_no_external_source_overlap() -> None:
    primary = _load("benchmarks/real_v1/manifest.json")
    holdout = _load("benchmarks/real_holdout_v1/manifest.json")

    assert _external_keys(primary).isdisjoint(_external_keys(holdout))
