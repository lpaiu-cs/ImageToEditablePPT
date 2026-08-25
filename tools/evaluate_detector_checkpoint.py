"""Evaluate a detector checkpoint on a manifest split with hash-bound micro metrics."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import torch
from torch.utils.data import DataLoader

from image_to_editable_ppt.ml.dataset import (
    DetectorTorchDataset,
    NODE_KIND_LABELS,
    detection_collate,
)
from image_to_editable_ppt.ml.lightning_module import DetectorLightningModule
from image_to_editable_ppt.ml.detection_postprocess import select_detection_indices


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _iou(first: list[float], second: list[float]) -> float:
    ix0, iy0 = max(first[0], second[0]), max(first[1], second[1])
    ix1, iy1 = min(first[2], second[2]), min(first[3], second[3])
    intersection = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    first_area = max(0.0, first[2] - first[0]) * max(0.0, first[3] - first[1])
    second_area = max(0.0, second[2] - second[0]) * max(0.0, second[3] - second[1])
    union = first_area + second_area - intersection
    return intersection / union if union > 0.0 else 0.0


def _match_count(
    prediction_boxes: list[list[float]],
    prediction_labels: list[int],
    reference_boxes: list[list[float]],
    reference_labels: list[int],
    *,
    iou_threshold: float,
) -> int:
    candidates: list[tuple[float, int, int]] = []
    for prediction_index, prediction_box in enumerate(prediction_boxes):
        for reference_index, reference_box in enumerate(reference_boxes):
            if prediction_labels[prediction_index] != reference_labels[reference_index]:
                continue
            overlap = _iou(prediction_box, reference_box)
            if overlap >= iou_threshold:
                candidates.append((overlap, prediction_index, reference_index))
    candidates.sort(reverse=True)
    used_predictions: set[int] = set()
    used_references: set[int] = set()
    for _, prediction_index, reference_index in candidates:
        if prediction_index in used_predictions or reference_index in used_references:
            continue
        used_predictions.add(prediction_index)
        used_references.add(reference_index)
    return len(used_predictions)


def _metrics(*, true_positive: int, prediction_count: int, reference_count: int) -> dict[str, object]:
    precision = true_positive / prediction_count if prediction_count else float(reference_count == 0)
    recall = true_positive / reference_count if reference_count else float(prediction_count == 0)
    f1 = 2.0 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "true_positive": true_positive,
        "false_positive": prediction_count - true_positive,
        "false_negative": reference_count - true_positive,
        "prediction_count": prediction_count,
        "reference_count": reference_count,
    }


def _category_counts(
    prediction: dict[str, torch.Tensor],
    reference: dict[str, torch.Tensor],
    *,
    score_threshold: float,
    iou_threshold: float,
    cross_class_nms_iou: float,
    node_containment_threshold: float,
    node_category: bool,
) -> tuple[int, int, int]:
    maximum_node_label = max(NODE_KIND_LABELS.values())
    selected = select_detection_indices(
        prediction,
        score_threshold=score_threshold,
        cross_class_nms_iou=cross_class_nms_iou,
        node_containment_threshold=node_containment_threshold,
    )
    pred_labels_all = prediction["labels"][selected].detach().cpu().tolist()
    pred_boxes_all = prediction["boxes"][selected].detach().cpu().tolist()
    ref_labels_all = reference["labels"].detach().cpu().tolist()
    ref_boxes_all = reference["boxes"].detach().cpu().tolist()

    def belongs(label: int) -> bool:
        return label <= maximum_node_label if node_category else label > maximum_node_label

    pred_pairs = [(box, int(label)) for box, label in zip(pred_boxes_all, pred_labels_all) if belongs(int(label))]
    ref_pairs = [(box, int(label)) for box, label in zip(ref_boxes_all, ref_labels_all) if belongs(int(label))]
    pred_boxes = [box for box, _ in pred_pairs]
    pred_labels = [label for _, label in pred_pairs]
    ref_boxes = [box for box, _ in ref_pairs]
    ref_labels = [label for _, label in ref_pairs]
    matched = _match_count(
        pred_boxes,
        pred_labels,
        ref_boxes,
        ref_labels,
        iou_threshold=iou_threshold,
    )
    return matched, len(pred_boxes), len(ref_boxes)


def evaluate(args: argparse.Namespace) -> dict[str, object]:
    dataset_dir = Path(args.dataset_dir).resolve()
    checkpoint = Path(args.checkpoint).resolve()
    manifest_path = dataset_dir / "dataset_manifest.json"
    dataset = DetectorTorchDataset(dataset_dir, split=args.split)
    loader = DataLoader(
        dataset,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=args.num_workers,
        collate_fn=detection_collate,
    )
    module = DetectorLightningModule.load_from_checkpoint(checkpoint, map_location="cpu")
    module.eval()
    cached: list[tuple[dict[str, torch.Tensor], dict[str, torch.Tensor]]] = []
    with torch.no_grad():
        for images, targets in loader:
            predictions = module(images)
            cached.extend(zip(predictions, targets))

    threshold_reports: list[dict[str, object]] = []
    for score_threshold in args.score_thresholds:
        totals = {
            "nodes": [0, 0, 0],
            "containers": [0, 0, 0],
        }
        for prediction, reference in cached:
            for category, node_category in (("nodes", True), ("containers", False)):
                counts = _category_counts(
                    prediction,
                    reference,
                    score_threshold=score_threshold,
                    iou_threshold=args.iou_threshold,
                    cross_class_nms_iou=args.cross_class_nms_iou,
                    node_containment_threshold=args.node_containment_threshold,
                    node_category=node_category,
                )
                totals[category] = [left + right for left, right in zip(totals[category], counts)]
        threshold_reports.append(
            {
                "score_threshold": score_threshold,
                "nodes": _metrics(
                    true_positive=totals["nodes"][0],
                    prediction_count=totals["nodes"][1],
                    reference_count=totals["nodes"][2],
                ),
                "containers": _metrics(
                    true_positive=totals["containers"][0],
                    prediction_count=totals["containers"][1],
                    reference_count=totals["containers"][2],
                ),
            }
        )
    report = {
        "schema_version": "detector_checkpoint_evaluation_v1",
        "checkpoint": str(checkpoint),
        "checkpoint_sha256": _sha256_file(checkpoint),
        "dataset_manifest": str(manifest_path),
        "dataset_manifest_sha256": _sha256_file(manifest_path),
        "split": args.split,
        "sample_count": len(dataset),
        "iou_threshold": args.iou_threshold,
        "cross_class_nms_iou": args.cross_class_nms_iou,
        "node_containment_threshold": args.node_containment_threshold,
        "thresholds": threshold_reports,
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
    parser.add_argument("--score-thresholds", type=float, nargs="+", default=[0.3, 0.4, 0.5, 0.6, 0.7])
    parser.add_argument("--iou-threshold", type=float, default=0.5)
    parser.add_argument("--cross-class-nms-iou", type=float, default=0.7)
    parser.add_argument("--node-containment-threshold", type=float, default=0.85)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--num-workers", type=int, default=0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = evaluate(args)
    print(json.dumps({"sample_count": report["sample_count"], "thresholds": report["thresholds"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
