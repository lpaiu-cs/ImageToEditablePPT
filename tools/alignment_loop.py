from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from image_to_editable_ppt.config import PipelineConfig
from image_to_editable_ppt.validation import run_validation_iteration


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run semantic-first input -> PPTX -> SVG validation iterations.")
    parser.add_argument(
        "input_image",
        nargs="?",
        default=Path("input.png"),
        type=Path,
        help="Input image to convert and validate",
    )
    parser.add_argument(
        "--workbench",
        type=Path,
        default=Path("workbench2.0") / "input-alignment",
        help="Directory where iteration artifacts are written",
    )
    parser.add_argument("--ocr", action="store_true", help="Enable optional OCR")
    parser.add_argument("--legacy", action="store_true", help="Force the legacy bottom-up CV pipeline")
    return parser


def next_iteration_dir(workbench: Path) -> Path:
    existing = sorted(path for path in workbench.glob("iter_*") if path.is_dir())
    next_index = 0
    if existing:
        next_index = max(int(path.name.split("_", 1)[1]) for path in existing) + 1
    return workbench / f"iter_{next_index:02d}"


def main() -> int:
    args = build_parser().parse_args()
    input_image = args.input_image.resolve()
    workbench = args.workbench.resolve()
    workbench.mkdir(parents=True, exist_ok=True)
    source_copy = workbench / input_image.name
    if not source_copy.exists() or source_copy.stat().st_mtime_ns != input_image.stat().st_mtime_ns:
        shutil.copy2(input_image, source_copy)
    iteration_dir = next_iteration_dir(workbench)
    result = run_validation_iteration(
        input_image,
        iteration_dir,
        config=PipelineConfig(semantic_mode=not args.legacy),
        enable_ocr=args.ocr,
    )
    print(f"iteration: {iteration_dir.name}")
    print(f"pptx: {result.artifacts.output_pptx}")
    print(f"svg: {result.artifacts.output_svg}")
    print(f"render: {result.artifacts.rendered_png}")
    print(f"overlay: {result.artifacts.overlay_png}")
    print(f"edge_diff: {result.artifacts.edge_diff_png}")
    print(f"metrics: {result.artifacts.metrics_json}")
    print(
        "precision={:.3f} recall={:.3f} f1={:.3f} coverage={:.3f} blank_penalty={:.3f} score={:.3f} shapes={}".format(
            result.metrics.precision,
            result.metrics.recall,
            result.metrics.f1,
            result.metrics.coverage_ratio,
            result.metrics.blank_output_penalty,
            result.metrics.structure_score,
            result.metrics.rendered_shape_count,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
