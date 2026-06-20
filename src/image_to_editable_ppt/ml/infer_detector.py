from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from image_to_editable_ppt.ml.adapter import AnnotationMLAdapter, DetectorModelOutput
from image_to_editable_ppt.ml.annotation_schema import (
    AnnotationBBox,
    AnnotationContainer,
    AnnotationFamilyProposal,
    AnnotationImageSize,
    AnnotationNode,
    DetectorAnnotationDocument,
)
from image_to_editable_ppt.v3.core.enums import ContainerKind, DiagramFamily, NodeKind
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
    checkpoint: Path | None
    image_path: Path | None
    score_threshold: float


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Detector inference and IR alignment.")
    parser.add_argument("--image-id", required=True, help="Logical image identifier.")
    parser.add_argument("--image-width", type=int, help="Image width in pixels (derived from --image-path when given).")
    parser.add_argument("--image-height", type=int, help="Image height in pixels (derived from --image-path when given).")
    parser.add_argument("--output-json", type=Path, required=True, help="Where to write prediction annotations.")
    parser.add_argument("--summary-json", type=Path, help="Optional IR summary output path.")
    parser.add_argument("--checkpoint", type=Path, help="Trained DetectorLightningModule checkpoint for real inference.")
    parser.add_argument("--image-path", type=Path, help="Input image to run the checkpoint on.")
    parser.add_argument("--score-threshold", type=float, default=0.5, help="Minimum detection score to keep.")
    parser.add_argument(
        "--family",
        action="append",
        choices=tuple(family.value for family in DiagramFamily),
        default=[],
        help="Seed family proposal(s); the detector does not predict families yet.",
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

    if args.image_path is not None:
        from PIL import Image

        with Image.open(args.image_path) as image:
            image_width, image_height = image.size
    else:
        if args.image_width is None or args.image_height is None:
            parser.error("--image-width/--image-height are required when --image-path is not given")
        image_width, image_height = args.image_width, args.image_height

    config = InferDetectorConfig(
        image_id=args.image_id,
        image_width=image_width,
        image_height=image_height,
        output_json=args.output_json,
        summary_json=args.summary_json,
        families=tuple(DiagramFamily(item) for item in args.family),
        family_confidence=float(args.family_confidence),
        validate_ir=bool(args.validate_ir),
        checkpoint=args.checkpoint,
        image_path=args.image_path,
        score_threshold=float(args.score_threshold),
    )

    if config.image_width <= 0 or config.image_height <= 0:
        parser.error("image width and height must be positive")
    if not 0.0 <= config.family_confidence <= 1.0:
        parser.error("family-confidence must be in [0, 1]")
    if config.checkpoint is not None and config.image_path is None:
        parser.error("--checkpoint requires --image-path")
    if config.checkpoint is not None and not config.checkpoint.exists():
        parser.error(f"checkpoint does not exist: {config.checkpoint}")

    adapter = AnnotationMLAdapter()
    if config.checkpoint is not None:
        node_predictions, container_predictions = _run_checkpoint_inference(config)
        # The detector predicts nodes/containers but not families, so seed the
        # family from the CLI flag while grounding its focus_bbox in the actual
        # detections (their union) instead of the whole-image placeholder.
        focus_bbox = _detection_focus_bbox(node_predictions, container_predictions, config)
        family_predictions = _seed_family_predictions(config, focus_bbox, from_detections=True)
        model_output = DetectorModelOutput(
            image_id=config.image_id,
            image_size=AnnotationImageSize(width=config.image_width, height=config.image_height),
            family_predictions=family_predictions,
            node_predictions=node_predictions,
            container_predictions=container_predictions,
            metadata={
                "stage": "phase7_ml_experiment_bootstrap",
                "inference_mode": "checkpoint",
                "checkpoint": str(config.checkpoint),
                "score_threshold": config.score_threshold,
            },
        )
    else:
        whole_image = AnnotationBBox(0.0, 0.0, float(config.image_width), float(config.image_height))
        family_predictions = _seed_family_predictions(config, whole_image, from_detections=False)
        model_output = DetectorModelOutput(
            image_id=config.image_id,
            image_size=AnnotationImageSize(width=config.image_width, height=config.image_height),
            family_predictions=family_predictions,
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


def _seed_family_predictions(
    config: InferDetectorConfig,
    focus_bbox: AnnotationBBox,
    *,
    from_detections: bool,
) -> tuple[AnnotationFamilyProposal, ...]:
    evidence = ("ml_detector:detection_union",) if from_detections else ("bootstrap:cli_seed",)
    provenance = ("ml_detector:focus_from_detections",) if from_detections else ("ml_detector:seed_family",)
    return tuple(
        AnnotationFamilyProposal(
            id=f"family:{family.value}:{index}",
            family=family,
            confidence=config.family_confidence,
            focus_bbox=focus_bbox,
            evidence=evidence,
            provenance=provenance,
        )
        for index, family in enumerate(config.families)
    )


def _detection_focus_bbox(
    nodes: tuple[AnnotationNode, ...],
    containers: tuple[AnnotationContainer, ...],
    config: InferDetectorConfig,
) -> AnnotationBBox:
    """Union of the detected node/container boxes, clipped to the image.

    Falls back to the whole image when there is nothing to ground the focus on.
    """
    boxes = [item.bbox for item in (*nodes, *containers)]
    whole_image = AnnotationBBox(0.0, 0.0, float(config.image_width), float(config.image_height))
    if not boxes:
        return whole_image
    x0 = max(0.0, min(box.x0 for box in boxes))
    y0 = max(0.0, min(box.y0 for box in boxes))
    x1 = min(float(config.image_width), max(box.x1 for box in boxes))
    y1 = min(float(config.image_height), max(box.y1 for box in boxes))
    if x1 <= x0 or y1 <= y0:
        return whole_image
    return AnnotationBBox(x0=x0, y0=y0, x1=x1, y1=y1)


def _run_checkpoint_inference(
    config: InferDetectorConfig,
) -> tuple[tuple[AnnotationNode, ...], tuple[AnnotationContainer, ...]]:
    import numpy as np
    import torch
    from PIL import Image

    from image_to_editable_ppt.ml.dataset import label_to_kind
    from image_to_editable_ppt.ml.lightning_module import DetectorLightningModule

    module = DetectorLightningModule.load_from_checkpoint(config.checkpoint, map_location="cpu")
    module.eval()

    assert config.image_path is not None
    with Image.open(config.image_path) as image:
        array = np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0
    image_tensor = torch.from_numpy(array).permute(2, 0, 1)
    with torch.no_grad():
        prediction = module([image_tensor])[0]

    nodes: list[AnnotationNode] = []
    containers: list[AnnotationContainer] = []
    for index in range(len(prediction["scores"])):
        score = float(prediction["scores"][index])
        if score < config.score_threshold:
            continue
        x0, y0, x1, y1 = (float(value) for value in prediction["boxes"][index])
        if x1 <= x0 or y1 <= y0:
            continue
        bbox = AnnotationBBox(x0=x0, y0=y0, x1=x1, y1=y1)
        kind = label_to_kind(int(prediction["labels"][index]))
        if isinstance(kind, NodeKind):
            nodes.append(
                AnnotationNode(
                    id=f"node:{config.image_id}:{index}",
                    kind=kind,
                    bbox=bbox,
                    confidence=min(score, 1.0),
                    source="ml_detector",
                    provenance=("ml_detector:checkpoint",),
                )
            )
        else:
            assert isinstance(kind, ContainerKind)
            containers.append(
                AnnotationContainer(
                    id=f"container:{config.image_id}:{index}",
                    kind=kind,
                    bbox=bbox,
                    confidence=min(score, 1.0),
                    source="ml_detector",
                    provenance=("ml_detector:checkpoint",),
                )
            )
    return tuple(nodes), tuple(containers)


def _write_document(path: Path, document: DetectorAnnotationDocument) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document.to_dict(), indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
