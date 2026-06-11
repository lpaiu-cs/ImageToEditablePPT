from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from image_to_editable_ppt.ml.adapter import AnnotationMLAdapter, DetectorModelOutput
from image_to_editable_ppt.ml.annotation_schema import (
    AnnotationBBox,
    AnnotationFamilyProposal,
    AnnotationImageSize,
    DetectorAnnotationDocument,
)
from image_to_editable_ppt.v3.core.enums import DiagramFamily
from image_to_editable_ppt.v3.ir.validate import validate_slide_ir


@dataclass(slots=True, frozen=True)
class InferDetectorConfig:
    image_id: str
    image_width: int
    image_height: int
    output_json: Path
    summary_json: Path | None
    families: tuple[DiagramFamily, ...]
    family_confidence: float
    validate_ir: bool


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bootstrap detector inference and IR alignment.")
    parser.add_argument("--image-id", required=True, help="Logical image identifier.")
    parser.add_argument("--image-width", type=int, required=True, help="Image width in pixels.")
    parser.add_argument("--image-height", type=int, required=True, help="Image height in pixels.")
    parser.add_argument("--output-json", type=Path, required=True, help="Where to write prediction annotations.")
    parser.add_argument("--summary-json", type=Path, help="Optional IR summary output path.")
    parser.add_argument(
        "--family",
        action="append",
        choices=tuple(family.value for family in DiagramFamily),
        default=[],
        help="Seed family proposal(s) for the placeholder detector.",
    )
    parser.add_argument("--family-confidence", type=float, default=0.5, help="Confidence for seeded family proposals.")
    parser.add_argument(
        "--validate-ir",
        action="store_true",
        help="Validate the adapted SlideIR payload after inference.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    config = InferDetectorConfig(
        image_id=args.image_id,
        image_width=args.image_width,
        image_height=args.image_height,
        output_json=args.output_json,
        summary_json=args.summary_json,
        families=tuple(DiagramFamily(item) for item in args.family),
        family_confidence=float(args.family_confidence),
        validate_ir=bool(args.validate_ir),
    )

    if config.image_width <= 0 or config.image_height <= 0:
        parser.error("image width and height must be positive")
    if not 0.0 <= config.family_confidence <= 1.0:
        parser.error("family-confidence must be in [0, 1]")

    adapter = AnnotationMLAdapter()
    model_output = DetectorModelOutput(
        image_id=config.image_id,
        image_size=AnnotationImageSize(width=config.image_width, height=config.image_height),
        family_predictions=tuple(
            AnnotationFamilyProposal(
                id=f"family:{family.value}:{index}",
                family=family,
                confidence=config.family_confidence,
                focus_bbox=AnnotationBBox(0.0, 0.0, float(config.image_width), float(config.image_height)),
                evidence=("bootstrap:cli_seed",),
                provenance=("ml_detector:seed_family",),
            )
            for index, family in enumerate(config.families)
        ),
        metadata={
            "stage": "phase7_ml_experiment_bootstrap",
            "inference_mode": "placeholder",
        },
    )
    document = adapter.from_model_output(model_output)
    _write_document(config.output_json, document)

    slide_ir = adapter.to_slide_ir(document)
    if config.validate_ir:
        validate_slide_ir(slide_ir)

    if config.summary_json is not None:
        summary = {
            "image_id": config.image_id,
            "family_proposal_count": len(slide_ir.family_proposals),
            "diagram_instance_count": len(slide_ir.diagram_instances),
            "primitive_node_count": len(slide_ir.primitive_scene.nodes) if slide_ir.primitive_scene is not None else 0,
            "primitive_container_count": len(slide_ir.primitive_scene.containers)
            if slide_ir.primitive_scene is not None
            else 0,
            "primitive_text_count": len(slide_ir.primitive_scene.texts) if slide_ir.primitive_scene is not None else 0,
            "connector_candidate_count": len(slide_ir.connector_candidates),
        }
        config.summary_json.parent.mkdir(parents=True, exist_ok=True)
        config.summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"wrote detector bootstrap predictions to {config.output_json}")
    return 0


def _write_document(path: Path, document: DetectorAnnotationDocument) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document.to_dict(), indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
