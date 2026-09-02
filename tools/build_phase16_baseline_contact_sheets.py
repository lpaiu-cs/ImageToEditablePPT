"""Build source-versus-Phase-15 contact sheets for direct visual baseline audit."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _fit(path: Path, size: tuple[int, int]) -> Image.Image:
    with Image.open(path) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
    image.thumbnail(size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", size, "white")
    canvas.paste(image, ((size[0] - image.width) // 2, (size[1] - image.height) // 2))
    return canvas


def _tile(record: dict[str, Any], *, root: Path, width: int, height: int) -> Image.Image:
    header_height = 54
    gutter = 12
    panel_width = (width - gutter) // 2
    panel_height = height - header_height - 24
    canvas = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default(size=18)
    small = ImageFont.load_default(size=15)
    counts = record["shape_counts"]
    status = "BLANK" if counts["blank"] else (
        f"objects={counts['total']} nodes={counts['nodes']} containers={counts['containers']} "
        f"connectors={counts['semantic_connectors']}"
    )
    draw.text((8, 6), f"{record['id']} | {record['stratum']} | {status}", fill="black", font=font)
    draw.text((8, 32), "SOURCE", fill="#333333", font=small)
    draw.text((panel_width + gutter + 8, 32), "PHASE 15 POWERPOINT", fill="#333333", font=small)
    source = _fit(root / record["source"]["path"], (panel_width, panel_height))
    baseline = _fit(root / record["powerpoint_render"]["path"], (panel_width, panel_height))
    canvas.paste(source, (0, header_height))
    canvas.paste(baseline, (panel_width + gutter, header_height))
    draw.rectangle((0, header_height, panel_width - 1, height - 1), outline="#888888", width=1)
    draw.rectangle(
        (panel_width + gutter, header_height, width - 1, height - 1),
        outline="#888888",
        width=1,
    )
    return canvas


def build_contact_sheets(
    manifest_path: Path,
    output_dir: Path,
    *,
    root: Path,
    per_sheet: int = 4,
) -> list[dict[str, object]]:
    manifest = _load(manifest_path)
    records = manifest.get("records")
    if not isinstance(records, list):
        raise ValueError("baseline manifest records must be a list")
    output_dir.mkdir(parents=True, exist_ok=True)
    index: list[dict[str, object]] = []
    for split in ("dev", "holdout"):
        for kind in ("diagram", "non_diagram"):
            selected = [
                record
                for record in records
                if record["split"] == split and record["kind"] == kind
            ]
            for page_index in range(0, len(selected), per_sheet):
                page_records = selected[page_index : page_index + per_sheet]
                tiles = [
                    _tile(record, root=root, width=1200, height=440) for record in page_records
                ]
                sheet = Image.new("RGB", (1200, 440 * len(tiles)), "white")
                for row, tile in enumerate(tiles):
                    sheet.paste(tile, (0, row * 440))
                output = output_dir / f"{split}-{kind}-{page_index // per_sheet + 1:02d}.png"
                sheet.save(output, optimize=True)
                index.append(
                    {
                        "path": output.resolve().relative_to(root.resolve()).as_posix(),
                        "sample_ids": [record["id"] for record in page_records],
                    }
                )
    index_path = output_dir / "index.json"
    index_path.write_text(
        json.dumps(
            {
                "schema_version": "phase16_baseline_contact_sheet_index_v1",
                "source_manifest": manifest_path.resolve().relative_to(root.resolve()).as_posix(),
                "sheets": index,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return index


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--manifest", type=Path, default=Path("benchmarks/phase16_baseline_v1.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/phase16-baseline-v1/contact-sheets"))
    parser.add_argument("--per-sheet", type=int, default=4)
    args = parser.parse_args()
    if args.per_sheet < 1:
        raise ValueError("--per-sheet must be positive")
    root = args.root.resolve()
    manifest = args.manifest if args.manifest.is_absolute() else root / args.manifest
    output_dir = args.output_dir if args.output_dir.is_absolute() else root / args.output_dir
    index = build_contact_sheets(
        manifest, output_dir, root=root, per_sheet=args.per_sheet
    )
    print(json.dumps({"output_dir": str(output_dir), "sheets": len(index)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
