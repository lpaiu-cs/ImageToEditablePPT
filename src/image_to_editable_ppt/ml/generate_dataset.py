"""CLI entrypoint that materializes a synthetic detector dataset.

Each sample is a (png, annotation json, pptx) triplet produced from one
``SyntheticSlideSpec``; ``dataset_manifest.json`` pins seed, split
assignment, family coverage, and schema version so a dataset build is fully
reproducible from its manifest.
"""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass
from pathlib import Path

from image_to_editable_ppt.ml.annotation_schema import SCHEMA_VERSION, AnnotationImageSize
from image_to_editable_ppt.ml.synthesize import (
    GENERATOR_NAME,
    RENDERER_NAME,
    SUPPORTED_FAMILIES,
    generate_slide_spec,
    render_spec_image,
    validate_spec_contract,
    write_spec_pptx,
)
from image_to_editable_ppt.v3.core.enums import DiagramFamily

MANIFEST_FILENAME = "dataset_manifest.json"
SPLIT_NAMES = ("train", "val", "test")


@dataclass(slots=True, frozen=True)
class GenerateDatasetConfig:
    output_dir: Path
    count: int
    seed: int
    image_width: int
    image_height: int
    families: tuple[DiagramFamily, ...]
    train_ratio: float
    val_ratio: float
    write_pptx: bool


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a synthetic img/pptx/annotation detector dataset.")
    parser.add_argument("--output-dir", type=Path, required=True, help="Dataset root directory.")
    parser.add_argument("--count", type=int, default=100, help="Number of samples to generate.")
    parser.add_argument("--seed", type=int, default=7, help="Generator seed; pins the dataset content.")
    parser.add_argument("--image-width", type=int, default=1280)
    parser.add_argument("--image-height", type=int, default=720)
    parser.add_argument(
        "--family",
        action="append",
        choices=tuple(family.value for family in SUPPORTED_FAMILIES),
        default=[],
        help="Family pool to sample from (default: all supported families).",
    )
    parser.add_argument("--train-ratio", type=float, default=0.8)
    parser.add_argument("--val-ratio", type=float, default=0.1, help="Test split takes the remainder.")
    parser.add_argument("--no-pptx", action="store_true", help="Skip writing .pptx sidecar files.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    config = GenerateDatasetConfig(
        output_dir=args.output_dir,
        count=args.count,
        seed=args.seed,
        image_width=args.image_width,
        image_height=args.image_height,
        families=tuple(DiagramFamily(item) for item in args.family) or SUPPORTED_FAMILIES,
        train_ratio=float(args.train_ratio),
        val_ratio=float(args.val_ratio),
        write_pptx=not args.no_pptx,
    )

    if config.count <= 0:
        parser.error("count must be positive")
    if config.image_width <= 0 or config.image_height <= 0:
        parser.error("image dimensions must be positive")
    if not 0.0 < config.train_ratio < 1.0 or config.val_ratio < 0.0 or config.train_ratio + config.val_ratio > 1.0:
        parser.error("ratios must satisfy 0 < train < 1, val >= 0, train + val <= 1")

    manifest = build_dataset(config)
    manifest_path = config.output_dir / MANIFEST_FILENAME
    print(f"wrote {config.count} samples and {manifest_path}")
    print(json.dumps({"split_counts": manifest["split_counts"], "family_counts": manifest["family_counts"]}, indent=2))
    return 0


def build_dataset(config: GenerateDatasetConfig) -> dict[str, object]:
    rng = random.Random(config.seed)
    image_size = AnnotationImageSize(width=config.image_width, height=config.image_height)
    splits = assign_splits(config.count, rng=rng, train_ratio=config.train_ratio, val_ratio=config.val_ratio)

    samples: list[dict[str, object]] = []
    family_counts: dict[str, int] = {}
    for index in range(config.count):
        family = config.families[rng.randrange(len(config.families))]
        sample_id = f"{family.value}_{config.seed:04d}_{index:05d}"
        split = splits[index]
        spec = generate_slide_spec(rng, sample_id=sample_id, family=family, image_size=image_size)
        validate_spec_contract(spec)

        sample_dir = config.output_dir / split
        sample_dir.mkdir(parents=True, exist_ok=True)
        image_path = sample_dir / f"{sample_id}.png"
        annotation_path = sample_dir / f"{sample_id}.json"
        pptx_path = sample_dir / f"{sample_id}.pptx"

        render_spec_image(spec).save(image_path)
        document = spec.to_annotation_document(
            split=split,
            metadata={"seed": config.seed, "sample_index": index},
        )
        annotation_path.write_text(json.dumps(document.to_dict(), indent=2), encoding="utf-8")
        if config.write_pptx:
            write_spec_pptx(spec, pptx_path)

        family_counts[family.value] = family_counts.get(family.value, 0) + 1
        samples.append(
            {
                "id": sample_id,
                "split": split,
                "family": family.value,
                "image": str(image_path.relative_to(config.output_dir)),
                "annotation": str(annotation_path.relative_to(config.output_dir)),
                "pptx": str(pptx_path.relative_to(config.output_dir)) if config.write_pptx else None,
            }
        )

    manifest: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "generator": {
            "name": GENERATOR_NAME,
            "renderer": RENDERER_NAME,
            "seed": config.seed,
            "count": config.count,
            "image_size": {"width": config.image_width, "height": config.image_height},
            "families": [family.value for family in config.families],
            "train_ratio": config.train_ratio,
            "val_ratio": config.val_ratio,
            "pptx_written": config.write_pptx,
        },
        "split_counts": {name: splits.count(name) for name in SPLIT_NAMES},
        "family_counts": family_counts,
        "samples": samples,
    }
    config.output_dir.mkdir(parents=True, exist_ok=True)
    (config.output_dir / MANIFEST_FILENAME).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def assign_splits(count: int, *, rng: random.Random, train_ratio: float, val_ratio: float) -> list[str]:
    indices = list(range(count))
    rng.shuffle(indices)
    train_cutoff = round(count * train_ratio)
    val_cutoff = train_cutoff + round(count * val_ratio)
    assignment = [""] * count
    for position, index in enumerate(indices):
        if position < train_cutoff:
            assignment[index] = "train"
        elif position < val_cutoff:
            assignment[index] = "val"
        else:
            assignment[index] = "test"
    return assignment


if __name__ == "__main__":
    raise SystemExit(main())
