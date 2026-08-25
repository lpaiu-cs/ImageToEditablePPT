"""Combine generated detector datasets without copying their sample files.

The output manifest rebases every sample path relative to the combined dataset
directory and records the SHA-256 of each source manifest.  Dataset loaders can
therefore consume a PIL/LibreOffice mixture while the provenance remains
auditable and regenerable.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from pathlib import Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def combine_manifests(manifest_paths: list[Path], output_dir: Path) -> dict[str, object]:
    if len(manifest_paths) < 2:
        raise ValueError("at least two source manifests are required")

    documents: list[tuple[Path, dict[str, object]]] = []
    for raw_path in manifest_paths:
        path = raw_path.resolve()
        document = json.loads(path.read_text(encoding="utf-8"))
        documents.append((path, document))

    schema_versions = {str(document.get("schema_version")) for _, document in documents}
    image_sizes = {
        json.dumps(document.get("generator", {}).get("image_size"), sort_keys=True)
        for _, document in documents
    }
    if len(schema_versions) != 1:
        raise ValueError(f"source schema versions differ: {sorted(schema_versions)}")
    if len(image_sizes) != 1:
        raise ValueError("source image sizes differ")

    output_root = output_dir.resolve()
    samples: list[dict[str, object]] = []
    source_records: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    for manifest_path, document in documents:
        source_root = manifest_path.parent
        generator = document.get("generator", {})
        source_records.append(
            {
                "manifest": Path(os.path.relpath(manifest_path, output_root)).as_posix(),
                "sha256": _sha256(manifest_path),
                "renderer": generator.get("renderer"),
                "seed": generator.get("seed"),
                "count": generator.get("count"),
            }
        )
        for raw_sample in document.get("samples", []):
            sample = dict(raw_sample)
            sample_id = str(sample["id"])
            if sample_id in seen_ids:
                raise ValueError(f"duplicate sample id: {sample_id}")
            seen_ids.add(sample_id)
            for key in ("image", "annotation", "pptx"):
                value = sample.get(key)
                if value:
                    target = (source_root / str(value)).resolve()
                    sample[key] = Path(os.path.relpath(target, output_root)).as_posix()
            samples.append(sample)

    split_counts = Counter(str(sample["split"]) for sample in samples)
    family_counts = Counter(str(sample["family"]) for sample in samples)
    families = sorted(family_counts)
    image_size = documents[0][1]["generator"]["image_size"]
    return {
        "schema_version": schema_versions.pop(),
        "generator": {
            "name": "combined_renderer_dataset_v1",
            "renderer": "mixed",
            "count": len(samples),
            "image_size": image_size,
            "families": families,
            "sources": source_records,
        },
        "split_counts": dict(sorted(split_counts.items())),
        "family_counts": dict(sorted(family_counts.items())),
        "samples": samples,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifests", nargs="+", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        document = combine_manifests(args.manifests, args.output_dir)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        parser.error(str(error))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_dir / "dataset_manifest.json"
    output_path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output_path), "split_counts": document["split_counts"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
