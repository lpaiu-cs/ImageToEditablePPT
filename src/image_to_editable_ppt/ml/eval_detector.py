from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from image_to_editable_ppt.ml.annotation_schema import DetectorAnnotationDocument
from image_to_editable_ppt.ml.metrics import evaluate_detector_predictions


@dataclass(slots=True, frozen=True)
class EvalDetectorConfig:
    predictions_json: Path
    ground_truth_json: Path
    iou_threshold: float
    report_json: Path | None


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate detector predictions against annotation JSON.")
    parser.add_argument("--predictions-json", type=Path, required=True, help="Predicted annotation JSON.")
    parser.add_argument("--ground-truth-json", type=Path, required=True, help="Reference annotation JSON.")
    parser.add_argument("--iou-threshold", type=float, default=0.5, help="IoU threshold for greedy matching.")
    parser.add_argument("--report-json", type=Path, help="Optional detailed report output path.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    config = EvalDetectorConfig(
        predictions_json=args.predictions_json,
        ground_truth_json=args.ground_truth_json,
        iou_threshold=float(args.iou_threshold),
        report_json=args.report_json,
    )

    if not config.predictions_json.exists():
        parser.error(f"prediction json does not exist: {config.predictions_json}")
    if not config.ground_truth_json.exists():
        parser.error(f"ground truth json does not exist: {config.ground_truth_json}")
    if not 0.0 < config.iou_threshold <= 1.0:
        parser.error("iou-threshold must be in (0, 1]")

    prediction = _load_document(config.predictions_json)
    reference = _load_document(config.ground_truth_json)
    report = evaluate_detector_predictions(
        prediction,
        reference,
        iou_threshold=config.iou_threshold,
    )

    if config.report_json is not None:
        config.report_json.parent.mkdir(parents=True, exist_ok=True)
        config.report_json.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")

    summary = {
        "image_id": report.image_id,
        "reference_image_id": report.reference_image_id,
        "iou_threshold": report.iou_threshold,
        "family_proposal_accuracy": report.family_proposals.accuracy,
        "node_f1": report.nodes.f1,
        "container_f1": report.containers.f1,
    }
    print(json.dumps(summary, indent=2))
    return 0


def _load_document(path: Path) -> DetectorAnnotationDocument:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return DetectorAnnotationDocument.from_dict(payload)


if __name__ == "__main__":
    raise SystemExit(main())
