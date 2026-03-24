from __future__ import annotations

import argparse
from pathlib import Path

from .config import PipelineConfig
from .pipeline import convert_image


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convert structural diagram images into editable PPTX.")
    parser.add_argument("input_image", type=Path, help="Input image path")
    parser.add_argument("output_pptx", type=Path, help="Output PPTX path")
    parser.add_argument("--ocr", action="store_true", help="Enable optional OCR if pytesseract is available")
    parser.add_argument("--debug-elements", type=Path, help="Write detected element JSON for inspection")
    parser.add_argument("--legacy", action="store_true", help="Disable semantic-first VLM parsing and use legacy CV only")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    config = PipelineConfig(semantic_mode=not args.legacy)
    result = convert_image(
        args.input_image,
        args.output_pptx,
        config=config,
        enable_ocr=args.ocr,
        debug_elements_path=args.debug_elements,
    )
    print(f"exported {len(result.elements)} elements to {args.output_pptx} via {result.pipeline_mode}")
    return 0
