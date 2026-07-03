"""User-facing loop closer (Phase 10): image in, editable .pptx out.

Wires the canonical ML checkpoints (detector / family classifier / connector
segmenter / OOD gate) into ``convert_image`` via ``MLSlideIRProvider``, merges
the OCR-annotated text branch, and writes native PowerPoint primitives with
``write_pptx``. Falls back to the heuristic v3 path with ``--no-ml``.

Usage:
    image-to-editable-ppt-convert figure.png
    image-to-editable-ppt-convert figs/*.png -o out/ --models-dir workbench-ml
"""
from __future__ import annotations

import argparse
import glob
import os
import sys
from pathlib import Path

# Canonical runs (docs/phase9_real_transfer_measurement.md). Override with the
# corresponding CLI flags or by pointing --models-dir elsewhere.
CANONICAL_RUNS = {
    "detector": "run-v8",
    "family": "run-fc5",
    "segmenter": "run-seg8",
    "gate": "run-gate4",
}
DEFAULT_TARGET_WIDTH = 768  # inference scale the canonical models were measured at


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convert a diagram image to an editable .pptx")
    parser.add_argument("inputs", nargs="+", help="input image path(s) or glob(s)")
    parser.add_argument("-o", "--output", default=None, help="output .pptx file (single input) or directory")
    parser.add_argument(
        "--models-dir",
        default=os.environ.get("IEP_MODELS_DIR", "workbench-ml"),
        help="directory containing the run-*/checkpoints/last.ckpt trees (default: workbench-ml)",
    )
    parser.add_argument("--detector-run", default=CANONICAL_RUNS["detector"])
    parser.add_argument("--family-run", default=CANONICAL_RUNS["family"])
    parser.add_argument("--segmenter-run", default=CANONICAL_RUNS["segmenter"])
    parser.add_argument("--gate-run", default=CANONICAL_RUNS["gate"])
    parser.add_argument("--threshold", type=float, default=0.5, help="detector score threshold")
    parser.add_argument("--gate-threshold", type=float, default=0.6, help="OOD diagram-gate threshold")
    parser.add_argument("--width", type=int, default=DEFAULT_TARGET_WIDTH, help="resize input to this width (0 = keep)")
    parser.add_argument("--no-ml", action="store_true", help="use the heuristic v3 path instead of the ML provider")
    parser.add_argument("--no-gate", action="store_true", help="skip the OOD not-a-diagram gate")
    parser.add_argument("--no-ocr", action="store_true", help="skip text recovery (OCR)")
    parser.add_argument("--no-style", action="store_true", help="skip per-shape colour sampling")
    return parser


def _checkpoint(models_dir: Path, run: str) -> Path:
    return models_dir / run / "checkpoints" / "last.ckpt"


def _build_provider(args: argparse.Namespace):
    from image_to_editable_ppt.ml.slide_ir_provider import MLSlideIRProvider

    models_dir = Path(args.models_dir)
    detector = _checkpoint(models_dir, args.detector_run)
    if not detector.exists():
        raise SystemExit(
            f"detector checkpoint not found: {detector}\n"
            "pass --models-dir (or set IEP_MODELS_DIR) to the directory holding the canonical runs, "
            "or use --no-ml for the heuristic path"
        )
    family = _checkpoint(models_dir, args.family_run)
    segmenter = _checkpoint(models_dir, args.segmenter_run)
    gate = _checkpoint(models_dir, args.gate_run)
    return MLSlideIRProvider(
        detector_checkpoint=str(detector),
        score_threshold=args.threshold,
        family_classifier_checkpoint=str(family) if family.exists() else None,
        connector_checkpoint=str(segmenter) if segmenter.exists() else None,
        diagram_gate_checkpoint=str(gate) if gate.exists() and not args.no_gate else None,
        diagram_gate_threshold=args.gate_threshold,
    )


def _resize(image, target_width: int):
    if target_width <= 0 or image.width == target_width:
        return image.convert("RGB")
    scale = target_width / float(image.width)
    return image.convert("RGB").resize((target_width, max(1, int(round(image.height * scale)))))


def _expand_inputs(patterns: list[str]) -> list[Path]:
    paths: list[Path] = []
    for pattern in patterns:
        if os.path.isdir(pattern):
            paths.extend(sorted(Path(pattern).iterdir()))
        else:
            paths.extend(Path(p) for p in sorted(glob.glob(pattern)) or [Path(pattern)])
    return [p for p in paths if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}]


def _output_path(input_path: Path, output: str | None, *, multiple: bool) -> Path:
    if output is None:
        return input_path.with_suffix(".pptx")
    output_path = Path(output)
    if multiple or output_path.suffix.lower() != ".pptx":
        return output_path / f"{input_path.stem}.pptx"
    return output_path


def convert_one(input_path: Path, output_path: Path, *, args: argparse.Namespace, provider) -> dict[str, object]:
    import numpy as np
    from PIL import Image

    from image_to_editable_ppt.v3.app.config import V3Config
    from image_to_editable_ppt.v3.app.convert import convert_image
    from image_to_editable_ppt.v3.emit import build_emit_scene, sample_shape_styles, write_pptx

    image = _resize(Image.open(input_path), args.width)
    config = V3Config(slide_ir_provider=provider, recover_text=not args.no_ocr)
    result = convert_image(image, config=config)
    slide_ir = result.slide_ir
    scene = slide_ir.primitive_scene
    emit_scene = build_emit_scene(primitive_scene=scene, connectors=slide_ir.connectors)
    styles = None
    if not args.no_style:
        styles = sample_shape_styles(np.asarray(image, dtype=np.uint8), emit_scene)
    write_pptx(emit_scene, output_path, styles=styles)

    recognized = sum(1 for text in emit_scene.texts if text.text)
    return {
        "family": slide_ir.family_proposals[0].family.value if slide_ir.family_proposals else None,
        "nodes": len(scene.nodes),
        "containers": len(scene.containers),
        "connectors": len(slide_ir.connectors),
        "texts": len(emit_scene.texts),
        "recognized_texts": recognized,
        "output": str(output_path),
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    inputs = _expand_inputs(args.inputs)
    if not inputs:
        print(f"no images found for {args.inputs}", file=sys.stderr)
        return 2

    provider = None if args.no_ml else _build_provider(args)
    if not args.no_ocr:
        from image_to_editable_ppt.v3.text.ocr import ocr_available

        if not ocr_available():
            print("note: no OCR backend (pip install rapidocr-onnxruntime); text will be left blank", file=sys.stderr)

    exit_code = 0
    for input_path in inputs:
        output_path = _output_path(input_path, args.output, multiple=len(inputs) > 1)
        try:
            summary = convert_one(input_path, output_path, args=args, provider=provider)
        except Exception as error:  # keep batch conversions alive
            print(f"[FAIL] {input_path}: {error}", file=sys.stderr)
            exit_code = 1
            continue
        if summary["family"] is None and summary["nodes"] == 0:
            print(
                f"[EMPTY] {input_path} -> {summary['output']} "
                "(OOD gate rejected it as not-a-diagram, or no structure was detected; use --no-gate to force)"
            )
        else:
            print(
                f"[OK] {input_path} -> {summary['output']} "
                f"family={summary['family']} nodes={summary['nodes']} containers={summary['containers']} "
                f"connectors={summary['connectors']} texts={summary['recognized_texts']}/{summary['texts']}"
            )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
