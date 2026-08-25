"""Evaluate a diagram-gate checkpoint on the fixed real-figure benchmark."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

from image_to_editable_ppt.ml.diagram_gate import is_diagram
from image_to_editable_ppt.ml.model_bundle import sha256_file


def _threshold_summary(samples: list[dict[str, object]], threshold: float) -> dict[str, object]:
    diagram = [sample for sample in samples if sample["kind"] == "diagram"]
    nondiagram = [sample for sample in samples if sample["kind"] == "non_diagram"]
    diagram_kept = sum(float(sample["p_diagram"]) >= threshold for sample in diagram)
    nondiagram_rejected = sum(float(sample["p_diagram"]) < threshold for sample in nondiagram)
    return {
        "threshold": threshold,
        "diagram_recall": diagram_kept / len(diagram) if diagram else 1.0,
        "nondiagram_reject_rate": nondiagram_rejected / len(nondiagram) if nondiagram else 1.0,
        "accuracy": (diagram_kept + nondiagram_rejected) / len(samples) if samples else 1.0,
        "diagram_kept": diagram_kept,
        "diagram_count": len(diagram),
        "nondiagram_rejected": nondiagram_rejected,
        "nondiagram_count": len(nondiagram),
    }


def evaluate(args: argparse.Namespace) -> dict[str, object]:
    root = Path(args.root).resolve()
    manifest_path = Path(args.manifest).resolve()
    checkpoint = Path(args.checkpoint).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    samples: list[dict[str, object]] = []
    for item in manifest["samples"]:
        image_path = root / item["path"]
        actual_hash = sha256_file(image_path)
        if actual_hash != item["sha256"]:
            raise RuntimeError(f"input hash mismatch for {item['id']}: {actual_hash}")
        with Image.open(image_path) as image:
            rgb = np.asarray(image.convert("RGB"))
        _, probability = is_diagram(str(checkpoint), rgb, threshold=0.5)
        samples.append(
            {
                "id": item["id"],
                "kind": item["kind"],
                "input_sha256": actual_hash,
                "p_diagram": probability,
            }
        )
    report = {
        "schema_version": "diagram_gate_evaluation_v1",
        "checkpoint": str(checkpoint),
        "checkpoint_sha256": sha256_file(checkpoint),
        "benchmark_manifest": str(manifest_path),
        "benchmark_manifest_sha256": sha256_file(manifest_path),
        "samples": samples,
        "thresholds": [_threshold_summary(samples, threshold) for threshold in args.thresholds],
    }
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=Path("benchmarks/real_v1/manifest.json"))
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--thresholds", type=float, nargs="+", default=[0.3, 0.4, 0.5, 0.6, 0.7, 0.8])
    return parser


def main(argv: list[str] | None = None) -> int:
    report = evaluate(build_parser().parse_args(argv))
    print(json.dumps({"thresholds": report["thresholds"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
