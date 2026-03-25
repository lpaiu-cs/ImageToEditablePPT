from __future__ import annotations

import argparse
from pathlib import Path

from image_to_editable_ppt.v3.diagnostics import run_v3_debug


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the v3 debug/inspection pipeline and dump JSON/overlay artifacts.")
    parser.add_argument("input_image", type=Path, help="Path to the input image")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for debug artifacts. Defaults to artifacts/v3_debug/<input-stem>",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    output_dir = args.output_dir or Path("artifacts") / "v3_debug" / args.input_image.stem
    run = run_v3_debug(args.input_image, output_dir=output_dir)
    print(run.artifacts.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
