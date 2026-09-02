"""Apply the auditable visual review decisions for Phase 16 annotation v2."""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping

from PIL import Image, ImageDraw, ImageFont, ImageOps

from image_to_editable_ppt.ml.phase16.validation import sha256_file


REVIEW_SCHEMA = "phase16_annotation_review_v1"


def _load(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return raw


def _suffix(identifier: str, prefix: str) -> str:
    expected = f"{prefix}:auto:"
    if not identifier.startswith(expected):
        raise ValueError(f"expected {expected} id, got {identifier}")
    return identifier.removeprefix(expected)


def _auto_id(prefix: str, suffix: str) -> str:
    return f"{prefix}:auto:{suffix}"


def _label(text: str) -> dict[str, object]:
    return {"text": text, "legible": True, "editable_required": True}


def _review_objects(
    annotation: Mapping[str, object], decision: Mapping[str, object]
) -> list[dict[str, Any]]:
    object_decision = decision.get("objects", {})
    if not isinstance(object_decision, Mapping):
        raise ValueError("objects decision must be an object")
    keep = object_decision.get("keep", [])
    core = set(object_decision.get("core", []))
    overrides = object_decision.get("overrides", {})
    labels = object_decision.get("labels", {})
    if not isinstance(keep, list) or not isinstance(overrides, Mapping) or not isinstance(labels, Mapping):
        raise ValueError("invalid object review decision")

    source_by_suffix = {
        _suffix(str(item["id"]), "object"): item
        for item in annotation.get("objects", [])
        if str(item.get("id", "")).startswith("object:auto:")
    }
    reviewed: list[dict[str, Any]] = []
    for suffix_raw in keep:
        suffix = str(suffix_raw)
        if suffix not in source_by_suffix:
            raise ValueError(f"unknown object candidate {suffix}")
        item = deepcopy(source_by_suffix[suffix])
        override = overrides.get(suffix, {})
        if not isinstance(override, Mapping):
            raise ValueError(f"object override {suffix} must be an object")
        item.update(deepcopy(dict(override)))
        item["importance"] = "core" if suffix in core else "secondary"
        if suffix in labels:
            item["label"] = _label(str(labels[suffix]))
        item["ambiguity_note"] = "Accepted during the Phase 16 visual geometry review."
        reviewed.append(item)

    additions = object_decision.get("add", [])
    if not isinstance(additions, list):
        raise ValueError("objects.add must be a list")
    for addition_raw in additions:
        if not isinstance(addition_raw, Mapping):
            raise ValueError("manual object must be an object")
        addition = deepcopy(dict(addition_raw))
        if "label_text" in addition:
            addition["label"] = _label(str(addition.pop("label_text")))
        addition.setdefault("parent_id", None)
        addition.setdefault("importance", "secondary")
        addition.setdefault("label", None)
        addition.setdefault(
            "ambiguity_note", "Added after direct visual inspection of the source image."
        )
        reviewed.append(addition)

    identifiers = {str(item["id"]) for item in reviewed}
    for item in reviewed:
        parent_id = item.get("parent_id")
        if parent_id is not None and str(parent_id) not in identifiers:
            raise ValueError(f"{item['id']} references rejected parent {parent_id}")
    return reviewed


def _review_connectors(
    annotation: Mapping[str, object],
    decision: Mapping[str, object],
    object_ids: set[str],
) -> list[dict[str, Any]]:
    connector_decision = decision.get("connectors", {})
    if not isinstance(connector_decision, Mapping):
        raise ValueError("connectors decision must be an object")
    keep = connector_decision.get("keep", [])
    core = set(connector_decision.get("core", []))
    overrides = connector_decision.get("overrides", {})
    if not isinstance(keep, list) or not isinstance(overrides, Mapping):
        raise ValueError("invalid connector review decision")

    source_by_suffix = {
        _suffix(str(item["id"]), "connector"): item
        for item in annotation.get("connectors", [])
        if str(item.get("id", "")).startswith("connector:auto:")
    }
    reviewed: list[dict[str, Any]] = []
    for suffix_raw in keep:
        suffix = str(suffix_raw)
        if suffix not in source_by_suffix:
            raise ValueError(f"unknown connector candidate {suffix}")
        item = deepcopy(source_by_suffix[suffix])
        override = overrides.get(suffix, {})
        if not isinstance(override, Mapping):
            raise ValueError(f"connector override {suffix} must be an object")
        item.update(deepcopy(dict(override)))
        item["importance"] = "core" if suffix in core else "secondary"
        item["ambiguity_note"] = "Endpoint and direction accepted during visual topology review."
        reviewed.append(item)

    additions = connector_decision.get("add", [])
    if not isinstance(additions, list):
        raise ValueError("connectors.add must be a list")
    for addition_raw in additions:
        if not isinstance(addition_raw, Mapping):
            raise ValueError("manual connector must be an object")
        addition = deepcopy(dict(addition_raw))
        addition.setdefault("direction", "directed")
        addition.setdefault("path_class", "direct_orthogonal")
        addition.setdefault("importance", "core")
        addition.setdefault(
            "ambiguity_note", "Added after direct visual topology inspection."
        )
        reviewed.append(addition)

    for item in reviewed:
        if str(item["source_id"]) not in object_ids or str(item["target_id"]) not in object_ids:
            raise ValueError(f"{item['id']} references an omitted endpoint")
    return reviewed


def apply_decision(
    annotation: Mapping[str, object],
    decision: Mapping[str, object],
    *,
    review_sha256: str,
    finalized: bool,
) -> dict[str, Any]:
    output = deepcopy(dict(annotation))
    if output.get("kind") == "diagram":
        objects = _review_objects(output, decision)
        output["objects"] = objects
        output["connectors"] = _review_connectors(
            output, decision, {str(item["id"]) for item in objects}
        )
        excluded = decision.get("excluded_regions", [])
        if not isinstance(excluded, list):
            raise ValueError("excluded_regions decision must be a list")
        output["excluded_regions"] = deepcopy(excluded)
    else:
        if output.get("objects") or output.get("connectors"):
            raise ValueError(f"{output.get('sample_id')}: non-diagram draft emitted structure")

    omissions = decision.get("allowed_omissions", [])
    if not isinstance(omissions, list):
        raise ValueError("allowed_omissions must be a list")
    output["allowed_omissions"] = [
        "Icons, logos, photos, illustrations, decoration, unsupported polygons/free curves, and open outlines.",
        *[str(item) for item in omissions],
    ]
    output["ambiguity_notes"] = [
        f"Visual review decisions are bound to {REVIEW_SCHEMA} SHA-256 {review_sha256}.",
        *[str(item) for item in decision.get("ambiguity_notes", [])],
    ]
    review = output.setdefault("review", {})
    passes = [
        item
        for item in review.get("passes", [])
        if item.get("pass_id") not in {"phase16-visual-geometry", "phase16-topology-exclusion"}
    ]
    passes.append(
        {
            "pass_id": "phase16-visual-geometry",
            "reviewer": "gpt-5.6-sol",
            "completed_at": "2026-09-02T09:00:00+09:00",
            "focus": ["source_image", "object_geometry", "object_roles", "missing_structure"],
        }
    )
    if finalized:
        passes.append(
            {
                "pass_id": "phase16-topology-exclusion",
                "reviewer": "gpt-5.6-sol",
                "completed_at": "2026-09-02T10:00:00+09:00",
                "focus": ["object_roles", "connector_endpoints", "excluded_regions"],
            }
        )
    review["passes"] = passes
    review["status"] = "resolved" if finalized else "first_pass_complete"
    return output


def _overlay(image: Image.Image, annotation: Mapping[str, object]) -> Image.Image:
    output = image.convert("RGB")
    draw = ImageDraw.Draw(output)
    font = ImageFont.load_default()
    stroke = max(2, round(min(output.size) * 0.003))
    for item in annotation.get("excluded_regions", []):
        bbox = item["bbox"]
        draw.rectangle(
            (bbox["x0"], bbox["y0"], bbox["x1"], bbox["y1"]),
            outline=(235, 135, 20),
            width=stroke,
        )
    for item in annotation.get("objects", []):
        bbox = item["bbox"]
        bounds = (bbox["x0"], bbox["y0"], bbox["x1"], bbox["y1"])
        if item["role"] == "container":
            color = (215, 35, 35)
        elif item["importance"] == "core":
            color = (15, 80, 230)
        else:
            color = (120, 55, 190)
        draw.rectangle(bounds, outline=color, width=stroke)
        code = str(item["id"]).split(":")[-1]
        label = f"{code} {item['role'][0].upper()} {item['importance'][0].upper()}"
        draw.rectangle((bounds[0], bounds[1], bounds[0] + 118, bounds[1] + 15), fill="white")
        draw.text((bounds[0] + 2, bounds[1] + 1), label, fill=color, font=font)
    for item in annotation.get("connectors", []):
        points = [(point["x"], point["y"]) for point in item["path_points"]]
        if len(points) >= 2:
            draw.line(points, fill=(0, 155, 55), width=stroke + 1)
    return output


def _contact_sheets(paths: list[Path], output_dir: Path) -> list[str]:
    outputs: list[str] = []
    for page_start in range(0, len(paths), 12):
        sheet = Image.new("RGB", (1600, 1200), (235, 235, 235))
        draw = ImageDraw.Draw(sheet)
        for local_index, path in enumerate(paths[page_start : page_start + 12]):
            with Image.open(path) as source:
                preview = ImageOps.contain(source.convert("RGB"), (380, 330), Image.Resampling.LANCZOS)
            column, row = local_index % 4, local_index // 4
            x = column * 400 + (400 - preview.width) // 2
            y = row * 400 + 20
            sheet.paste(preview, (x, y))
            draw.text((column * 400 + 12, row * 400 + 360), path.stem, fill="black")
        page = page_start // 12 + 1
        target = output_dir / f"contact-sheet-{page:02d}.png"
        sheet.save(target)
        outputs.append(str(target))
    return outputs


def apply_review(
    review_path: Path,
    *,
    root: Path,
    output_dir: Path,
    write: bool,
    finalize: bool,
) -> dict[str, object]:
    review = _load(review_path)
    if review.get("schema_version") != REVIEW_SCHEMA:
        raise ValueError(f"unsupported review schema: {review.get('schema_version')}")
    decisions = review.get("samples")
    if not isinstance(decisions, Mapping):
        raise ValueError("review samples must be an object")
    review_sha = sha256_file(review_path)
    records: list[dict[str, object]] = []
    overlay_paths: dict[str, list[Path]] = {"dev": [], "holdout": []}
    manifests = [
        root / "benchmarks/phase16_dev_v1/manifest.json",
        root / "benchmarks/phase16_holdout_v1/manifest.json",
    ]
    seen: set[str] = set()
    for manifest_path in manifests:
        manifest = _load(manifest_path)
        split = str(manifest["split"])
        overlay_dir = output_dir / split / "overlays"
        overlay_dir.mkdir(parents=True, exist_ok=True)
        for sample in manifest["samples"]:
            sample_id = str(sample["id"])
            decision = decisions.get(sample_id, {})
            if not isinstance(decision, Mapping):
                raise ValueError(f"{sample_id} review decision must be an object")
            annotation_path = root / str(sample["annotation"])
            annotation = _load(annotation_path)
            try:
                reviewed = apply_decision(
                    annotation,
                    decision,
                    review_sha256=review_sha,
                    finalized=finalize,
                )
            except (ValueError, KeyError, TypeError) as error:
                raise ValueError(f"{sample_id}: {error}") from error
            if write:
                annotation_path.write_text(json.dumps(reviewed, indent=2) + "\n", encoding="utf-8")
            image_path = root / str(sample["path"])
            with Image.open(image_path) as image:
                overlay = _overlay(image, reviewed)
            overlay_path = overlay_dir / f"{sample_id}.png"
            overlay.save(overlay_path)
            overlay_paths[split].append(overlay_path)
            records.append(
                {
                    "id": sample_id,
                    "kind": sample["kind"],
                    "objects": len(reviewed["objects"]),
                    "connectors": len(reviewed["connectors"]),
                    "excluded_regions": len(reviewed["excluded_regions"]),
                    "status": reviewed["review"]["status"],
                }
            )
            seen.add(sample_id)
    unknown = set(decisions) - seen
    if unknown:
        raise ValueError(f"review contains unknown samples: {sorted(unknown)}")
    sheets = {
        split: _contact_sheets(paths, output_dir / split)
        for split, paths in overlay_paths.items()
    }
    report = {
        "schema_version": "phase16_annotation_review_report_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "review_sha256": review_sha,
        "write": write,
        "finalized": finalize,
        "records": records,
        "contact_sheets": sheets,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--review", type=Path, default=Path("benchmarks/phase16_annotation_review_v1.json")
    )
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument(
        "--output-dir", type=Path, default=Path("artifacts/phase16-annotation-review")
    )
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--finalize", action="store_true")
    args = parser.parse_args(argv)
    if args.finalize and not args.write:
        parser.error("--finalize requires --write")
    root = args.root.resolve()
    try:
        report = apply_review(
            (root / args.review).resolve(),
            root=root,
            output_dir=(root / args.output_dir).resolve(),
            write=args.write,
            finalize=args.finalize,
        )
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        parser.error(str(error))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
