"""Create review overlays and optional Phase 16 annotation drafts."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

from image_to_editable_ppt.ml.phase16.annotation_drafting import draft_structural_annotation


def _load(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return raw


def _overlay(image: Image.Image, draft: Mapping[str, object]) -> Image.Image:
    output = image.convert("RGB")
    draw = ImageDraw.Draw(output)
    font = ImageFont.load_default()
    stroke = max(2, round(min(output.size) * 0.003))
    for item in draft["objects"]:
        bbox = item["bbox"]
        bounds = (bbox["x0"], bbox["y0"], bbox["x1"], bbox["y1"])
        color = (220, 35, 35) if item["role"] == "container" else (20, 90, 230)
        draw.rectangle(bounds, outline=color, width=stroke)
        draw.rectangle(
            (bounds[0], bounds[1], bounds[0] + 116, bounds[1] + 15),
            fill=(255, 255, 255),
        )
        draw.text(
            (bounds[0] + 2, bounds[1] + 1),
            f"{item['id'].split(':')[-1]} {item['role'][0].upper()}",
            fill=color,
            font=font,
        )
    for item in draft["connectors"]:
        points = [(point["x"], point["y"]) for point in item["path_points"]]
        if len(points) >= 2:
            draw.line(points, fill=(0, 150, 60), width=stroke + 1)
    return output


def _contact_sheets(overlay_paths: list[Path], output_dir: Path) -> list[str]:
    outputs: list[str] = []
    for page_start in range(0, len(overlay_paths), 12):
        page_paths = overlay_paths[page_start : page_start + 12]
        sheet = Image.new("RGB", (1600, 1200), (235, 235, 235))
        draw = ImageDraw.Draw(sheet)
        for local_index, path in enumerate(page_paths):
            with Image.open(path) as source:
                preview = ImageOps.contain(source.convert("RGB"), (380, 330), Image.Resampling.LANCZOS)
            column = local_index % 4
            row = local_index // 4
            x = column * 400 + (400 - preview.width) // 2
            y = row * 400 + 20
            sheet.paste(preview, (x, y))
            draw.text((column * 400 + 12, row * 400 + 360), path.stem, fill=(0, 0, 0))
        page = page_start // 12 + 1
        target = output_dir / f"contact-sheet-{page:02d}.png"
        sheet.save(target)
        outputs.append(str(target))
    return outputs


def draft_manifest(
    manifest_path: Path,
    *,
    root: Path,
    output_dir: Path,
    write: bool,
) -> dict[str, object]:
    manifest = _load(manifest_path)
    split = str(manifest["split"])
    overlay_dir = output_dir / split / "overlays"
    overlay_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []
    overlay_paths: list[Path] = []
    for sample in manifest["samples"]:
        if sample["kind"] != "diagram":
            continue
        image_path = root / sample["path"]
        annotation_path = root / sample["annotation"]
        annotation = _load(annotation_path)
        if annotation["review"]["status"] != "draft":
            raise ValueError(f"refusing to replace reviewed annotation: {annotation_path}")
        with Image.open(image_path) as source:
            image = source.convert("RGB")
        draft = draft_structural_annotation(np.asarray(image), image_id=sample["id"])
        overlay_path = overlay_dir / f"{sample['id']}.png"
        _overlay(image, draft).save(overlay_path)
        overlay_paths.append(overlay_path)
        if write:
            annotation["objects"] = draft["objects"]
            annotation["connectors"] = draft["connectors"]
            annotation["ambiguity_notes"] = [
                "Frozen Phase 15 detections seeded this draft. Every object, endpoint, importance, label, and excluded region requires manual review."
            ]
            annotation["review"]["passes"].append(
                {
                    "pass_id": "phase15-annotation-assist",
                    "reviewer": "deterministic-tool",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "focus": ["draft_geometry", "draft_direct_connectors"],
                }
            )
            annotation_path.write_text(json.dumps(annotation, indent=2) + "\n", encoding="utf-8")
        records.append(
            {
                "id": sample["id"],
                "objects": len(draft["objects"]),
                "connectors": len(draft["connectors"]),
                "raw_candidates": draft["raw_candidate_count"],
                "overlay": str(overlay_path),
            }
        )
    contact_sheets = _contact_sheets(overlay_paths, output_dir / split)
    report = {"split": split, "write": write, "samples": records, "contact_sheets": contact_sheets}
    (output_dir / split / "draft_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        action="append",
        default=[],
        help="May be repeated; defaults to both Phase 16 manifests.",
    )
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument(
        "--output-dir", type=Path, default=Path("artifacts/phase16-annotation-drafts")
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    manifests = args.manifest or [
        Path("benchmarks/phase16_dev_v1/manifest.json"),
        Path("benchmarks/phase16_holdout_v1/manifest.json"),
    ]
    root = args.root.resolve()
    output_dir = args.output_dir.resolve()
    try:
        reports = [
            draft_manifest(
                (root / path).resolve(),
                root=root,
                output_dir=output_dir,
                write=args.write,
            )
            for path in manifests
        ]
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        parser.error(str(error))
    print(json.dumps(reports, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
