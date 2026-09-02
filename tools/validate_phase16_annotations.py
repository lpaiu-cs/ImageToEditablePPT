"""Validate Phase 16 manifests, annotations, hashes, and split isolation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from image_to_editable_ppt.ml.phase16.validation import (
    ValidationError,
    validate_phase16_manifests,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dev",
        type=Path,
        default=Path("benchmarks/phase16_dev_v1/manifest.json"),
    )
    parser.add_argument(
        "--holdout",
        type=Path,
        default=Path("benchmarks/phase16_holdout_v1/manifest.json"),
    )
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--require-frozen", action="store_true")
    parser.add_argument("--near-duplicate-distance", type=int, default=6)
    args = parser.parse_args(argv)
    try:
        report = validate_phase16_manifests(
            args.dev,
            args.holdout,
            root=args.root,
            require_frozen=args.require_frozen,
            near_duplicate_distance=args.near_duplicate_distance,
        )
    except (OSError, ValidationError) as error:
        parser.error(str(error))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
