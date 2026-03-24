from __future__ import annotations

import argparse

from image_to_editable_ppt.benchmark_report import format_benchmark_summary, write_benchmark_summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Aggregate benchmark diagnostics across slide directories.")
    parser.add_argument("benchmark_root", help="Benchmark root directory, e.g. workbench2.0")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    summary_path, rollup_path, summary, _ = write_benchmark_summary(args.benchmark_root)
    print(f"benchmark_summary: {summary_path}")
    print(f"benchmark_rollup: {rollup_path}")
    print(format_benchmark_summary(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
