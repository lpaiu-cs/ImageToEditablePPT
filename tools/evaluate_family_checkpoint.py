"""Evaluate a family-classifier checkpoint on a manifest split."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
from torch.utils.data import DataLoader

from image_to_editable_ppt.ml.family_classifier import (
    FAMILY_CLASS_ORDER,
    FamilyClassifierModule,
    _build_torch_dataset,
)
from image_to_editable_ppt.ml.model_bundle import sha256_file


def _summarize(predictions: list[int], references: list[int]) -> dict[str, object]:
    if len(predictions) != len(references):
        raise ValueError("prediction and reference lengths differ")
    matrix = [[0 for _ in FAMILY_CLASS_ORDER] for _ in FAMILY_CLASS_ORDER]
    for prediction, reference in zip(predictions, references):
        matrix[reference][prediction] += 1
    correct = sum(int(prediction == reference) for prediction, reference in zip(predictions, references))
    per_family: dict[str, object] = {}
    for index, family in enumerate(FAMILY_CLASS_ORDER):
        count = sum(matrix[index])
        per_family[family.value] = {
            "correct": matrix[index][index],
            "count": count,
            "accuracy": matrix[index][index] / count if count else 1.0,
        }
    return {
        "accuracy": correct / len(references) if references else 1.0,
        "correct": correct,
        "count": len(references),
        "class_order": [family.value for family in FAMILY_CLASS_ORDER],
        "confusion_matrix": matrix,
        "per_family": per_family,
    }


def evaluate(args: argparse.Namespace) -> dict[str, object]:
    dataset_dir = Path(args.dataset_dir).resolve()
    checkpoint = Path(args.checkpoint).resolve()
    manifest_path = dataset_dir / "dataset_manifest.json"
    dataset = _build_torch_dataset(dataset_dir, split=args.split)
    loader = DataLoader(dataset, batch_size=args.batch_size, shuffle=False, num_workers=args.num_workers)
    module = FamilyClassifierModule.load_from_checkpoint(checkpoint, map_location="cpu")
    module.eval()
    predictions: list[int] = []
    references: list[int] = []
    with torch.no_grad():
        for images, labels in loader:
            predictions.extend(module(images).argmax(dim=1).cpu().tolist())
            references.extend(labels.cpu().tolist())
    report = {
        "schema_version": "family_checkpoint_evaluation_v1",
        "checkpoint": str(checkpoint),
        "checkpoint_sha256": sha256_file(checkpoint),
        "dataset_manifest": str(manifest_path),
        "dataset_manifest_sha256": sha256_file(manifest_path),
        "split": args.split,
        **_summarize(predictions, references),
    }
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--split", default="test")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--num-workers", type=int, default=0)
    return parser


def main(argv: list[str] | None = None) -> int:
    report = evaluate(build_parser().parse_args(argv))
    print(json.dumps({"accuracy": report["accuracy"], "correct": report["correct"], "count": report["count"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
