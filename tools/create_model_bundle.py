"""Create a checksum-bound model bundle manifest from trained artifacts."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from image_to_editable_ppt.ml.model_bundle import (
    BUNDLE_SCHEMA_VERSION,
    CHECKPOINT_ROLES,
    ModelBundleError,
    artifact_record,
)


def _checkpoint_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--detector", type=Path, required=True)
    for role in CHECKPOINT_ROLES[1:]:
        parser.add_argument(f"--{role}", type=Path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--status", choices=("candidate", "canonical"), default="candidate")
    parser.add_argument("--connector-strategy", choices=("morphological", "segmenter", "relation"), default="morphological")
    parser.add_argument("--detector-threshold", type=float, default=0.5)
    parser.add_argument("--detector-nms-iou", type=float, default=0.7)
    parser.add_argument("--node-containment-threshold", type=float, default=0.85)
    parser.add_argument("--gate-threshold", type=float, default=0.6)
    parser.add_argument("--training-manifest", type=Path, action="append", default=[])
    parser.add_argument("--evidence", type=Path, action="append", default=[])
    _checkpoint_arguments(parser)
    args = parser.parse_args(argv)

    output_path = args.output.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        checkpoints = {
            role: artifact_record(getattr(args, role), relative_to=output_path.parent)
            if getattr(args, role) is not None
            else None
            for role in CHECKPOINT_ROLES
        }
        training_manifests = [
            artifact_record(path, relative_to=output_path.parent) for path in args.training_manifest
        ]
        evidence = [artifact_record(path, relative_to=output_path.parent) for path in args.evidence]
    except ModelBundleError as error:
        parser.error(str(error))
    if args.status == "canonical":
        missing = [role for role in ("detector", "family", "gate") if checkpoints[role] is None]
        if missing:
            parser.error(f"canonical bundle requires checkpoints: {', '.join(missing)}")
        if not training_manifests or not evidence:
            parser.error("canonical bundle requires at least one training manifest and one evidence artifact")
    document = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "status": args.status,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "checkpoints": checkpoints,
        "settings": {
            "connector_strategy": args.connector_strategy,
            "detector_threshold": args.detector_threshold,
            "detector_nms_iou": args.detector_nms_iou,
            "node_containment_threshold": args.node_containment_threshold,
            "gate_threshold": args.gate_threshold,
        },
        "training_manifests": training_manifests,
        "evidence": evidence,
    }
    output_path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output_path), "status": args.status}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
