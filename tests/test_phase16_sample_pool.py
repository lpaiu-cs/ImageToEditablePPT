from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from tools.build_phase16_sample_pool import (
    caption_suggestion,
    difference_hash,
    discover_consumed_shards,
    source_group_from_file_name,
)


def test_caption_suggestion_is_only_a_manual_review_hint() -> None:
    assert caption_suggestion("Architecture of the proposed model") == "diagram_candidate"
    assert caption_suggestion("Microscopy images and intensity distribution") == "non_diagram_candidate"
    assert caption_suggestion("Results for the first experiment") == "ambiguous"


def test_source_group_prefers_arxiv_identifier() -> None:
    assert (
        source_group_from_file_name("figures/1908.05227_encoder.png", "blob_data_1.parquet")
        == "arxiv:1908.05227"
    )
    assert source_group_from_file_name("unknown.png", "sub/blob_data_42.parquet") == "shard:blob_data_42"


def test_difference_hash_is_stable_and_visual() -> None:
    first = Image.new("RGB", (32, 32), "white")
    second = first.copy()
    for x in range(16, 32):
        for y in range(32):
            second.putpixel((x, y), (0, 0, 0))

    assert difference_hash(first) == difference_hash(first.copy())
    assert len(difference_hash(first)) == 16
    assert difference_hash(first) != difference_hash(second)


def test_discover_consumed_shards_reads_benchmark_and_artifact_manifests(tmp_path: Path) -> None:
    benchmark = tmp_path / "benchmarks" / "one" / "manifest.json"
    artifact = tmp_path / "artifacts" / "probe" / "pool.json"
    benchmark.parent.mkdir(parents=True)
    artifact.parent.mkdir(parents=True)
    benchmark.write_text(json.dumps({"source": {"shard": "blob_data_1.parquet"}}))
    artifact.write_text(json.dumps({"source": {"shard": "subdir/blob_data_2.parquet"}}))

    assert discover_consumed_shards(tmp_path) == {
        "blob_data_1.parquet",
        "subdir/blob_data_2.parquet",
    }
