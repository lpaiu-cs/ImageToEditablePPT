"""Build a deterministic, source-bound visual candidate pool for Phase 16.

The pool is development infrastructure, not an acceptance split.  It downloads
previously unused one-row parquet shards, extracts their image and caption, and
creates numbered contact sheets for manual stratum selection.  Final dev and
holdout manifests are created only after that visual classification step.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import random
import re
from typing import Iterable, Mapping
import urllib.parse
import urllib.request

from PIL import Image, ImageDraw, ImageFont, ImageOps


DEFAULT_DATASET = "yousefg-codes/research-paper-figures"
DEFAULT_REVISION = "3e8a1a190f814b48a358e5be60e69de28e886110"
DEFAULT_SEED = 160016

_DIAGRAM_TERMS = (
    "architecture",
    "block diagram",
    "flow diagram",
    "flowchart",
    "framework",
    "pipeline",
    "schematic",
    "system overview",
    "workflow",
    "encoder-decoder",
    "encoder decoder",
    "network structure",
    "proposed model",
    "model structure",
)
_NON_DIAGRAM_TERMS = (
    "box plot",
    "boxplot",
    "confusion matrix",
    "distribution",
    "heatmap",
    "histogram",
    "micrograph",
    "microscopy",
    "photograph",
    "scatter",
    "spectrum",
    "spectra",
    "table ",
    "x-ray",
    "xrd",
)
_SOURCE_GROUP_PATTERNS = (
    re.compile(r"(?<!\d)(\d{4}\.\d{4,5})(?!\d)"),
    re.compile(r"(?<!\d)(\d{7})(?!\d)"),
)
_SHARD_PATTERN = re.compile(r'"shard"\s*:\s*"([^"]+\.parquet)"')


@dataclass(slots=True, frozen=True)
class HubShard:
    path: str
    size: int
    sha256: str


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def caption_suggestion(caption: str, file_name: str = "") -> str:
    text = f"{caption} {file_name}".lower()
    diagram_score = sum(term in text for term in _DIAGRAM_TERMS)
    non_diagram_score = sum(term in text for term in _NON_DIAGRAM_TERMS)
    if diagram_score > non_diagram_score and diagram_score:
        return "diagram_candidate"
    if non_diagram_score > diagram_score and non_diagram_score:
        return "non_diagram_candidate"
    return "ambiguous"


def source_group_from_file_name(file_name: str, shard: str) -> str:
    for pattern in _SOURCE_GROUP_PATTERNS:
        match = pattern.search(file_name)
        if match:
            return f"arxiv:{match.group(1)}"
    return f"shard:{Path(shard).stem}"


def difference_hash(image: Image.Image) -> str:
    grayscale = ImageOps.grayscale(image).resize((9, 8), Image.Resampling.LANCZOS)
    pixels = list(grayscale.get_flattened_data())
    value = 0
    for y in range(8):
        row = pixels[y * 9 : (y + 1) * 9]
        for x in range(8):
            value = (value << 1) | int(row[x] > row[x + 1])
    return f"{value:016x}"


def discover_consumed_shards(root: Path) -> set[str]:
    consumed: set[str] = set()
    for directory_name in ("benchmarks", "artifacts"):
        directory = root / directory_name
        if not directory.is_dir():
            continue
        for path in directory.rglob("*.json"):
            try:
                if path.stat().st_size > 8 * 1024 * 1024:
                    continue
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            consumed.update(match.group(1) for match in _SHARD_PATTERN.finditer(text))
    return consumed


def _read_json_url(url: str) -> Mapping[str, object]:
    request = urllib.request.Request(url, headers={"User-Agent": "ImageToEditablePPT-phase16"})
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, Mapping):
        raise RuntimeError(f"expected JSON object from {url}")
    return payload


def list_hub_shards(
    dataset: str,
    *,
    revision: str,
    minimum_bytes: int,
    maximum_bytes: int,
) -> list[HubShard]:
    encoded_dataset = "/".join(urllib.parse.quote(part) for part in dataset.split("/"))
    info = _read_json_url(f"https://huggingface.co/api/datasets/{encoded_dataset}?blobs=true")
    if info.get("sha") != revision:
        raise RuntimeError(
            f"dataset revision drift: requested {revision}, Hub reports {info.get('sha')}"
        )
    shards: list[HubShard] = []
    siblings = info.get("siblings")
    if not isinstance(siblings, list):
        raise RuntimeError("Hub dataset response has no sibling list")
    for sibling in siblings:
        if not isinstance(sibling, Mapping):
            continue
        path = sibling.get("rfilename")
        lfs = sibling.get("lfs")
        if not isinstance(path, str) or not path.endswith(".parquet"):
            continue
        if not isinstance(lfs, Mapping):
            continue
        sha256 = lfs.get("sha256")
        size = lfs.get("size", sibling.get("size"))
        if not isinstance(sha256, str) or len(sha256) != 64:
            continue
        if not isinstance(size, int) or not minimum_bytes <= size <= maximum_bytes:
            continue
        shards.append(HubShard(path=path, size=size, sha256=sha256))
    return shards


def _download_shard(dataset: str, revision: str, shard: HubShard) -> bytes:
    encoded_dataset = "/".join(urllib.parse.quote(part) for part in dataset.split("/"))
    encoded_shard = urllib.parse.quote(shard.path, safe="/")
    url = (
        f"https://huggingface.co/datasets/{encoded_dataset}/resolve/"
        f"{revision}/{encoded_shard}?download=true"
    )
    request = urllib.request.Request(url, headers={"User-Agent": "ImageToEditablePPT-phase16"})
    with urllib.request.urlopen(request, timeout=120) as response:
        payload = response.read()
    actual_sha = sha256_bytes(payload)
    if actual_sha != shard.sha256:
        raise RuntimeError(f"parquet hash mismatch for {shard.path}: {actual_sha}")
    return payload


def _extract_record(parquet_payload: bytes) -> tuple[str, str, bytes]:
    try:
        import pyarrow.parquet as pq
    except ImportError as error:
        raise RuntimeError("pyarrow is required to build the Phase 16 pool") from error
    table = pq.read_table(io.BytesIO(parquet_payload))
    if table.num_rows != 1 or "image" not in table.column_names:
        raise RuntimeError("expected a one-row parquet shard with an image column")
    caption = table["caption"][0].as_py() if "caption" in table.column_names else ""
    file_name = table["file_name"][0].as_py() if "file_name" in table.column_names else ""
    image_payload = table["image"][0].as_py()
    if not isinstance(image_payload, bytes):
        raise RuntimeError("parquet image cell is not bytes")
    return str(caption or ""), str(file_name or ""), image_payload


def _materialize_one(
    index: int,
    shard: HubShard,
    *,
    dataset: str,
    revision: str,
) -> tuple[int, dict[str, object], bytes] | None:
    parquet_payload = _download_shard(dataset, revision, shard)
    caption, file_name, image_payload = _extract_record(parquet_payload)
    try:
        with Image.open(io.BytesIO(image_payload)) as source:
            image = source.convert("RGB")
    except OSError:
        return None
    width, height = image.size
    if min(width, height) < 160 or width * height < 80_000:
        return None
    normalized = io.BytesIO()
    image.save(normalized, format="PNG", optimize=True)
    png_payload = normalized.getvalue()
    suggestion = caption_suggestion(caption, file_name)
    record: dict[str, object] = {
        "selection_index": index,
        "caption": caption,
        "file_name": file_name,
        "suggestion": suggestion,
        "width": width,
        "height": height,
        "sha256": sha256_bytes(png_payload),
        "perceptual_hash": difference_hash(image),
        "source_group": source_group_from_file_name(file_name, shard.path),
        "source": {
            "type": "huggingface_parquet",
            "dataset": dataset,
            "revision": revision,
            "shard": shard.path,
            "row": 0,
            "sha256": shard.sha256,
            "size": shard.size,
        },
    }
    return index, record, png_payload


def _wrapped_text(draw: ImageDraw.ImageDraw, text: str, width: int) -> list[str]:
    words = text.replace("\n", " ").split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if draw.textlength(candidate) <= width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _contact_sheets(records: list[dict[str, object]], output_dir: Path) -> list[str]:
    sheet_dir = output_dir / "contact-sheets"
    sheet_dir.mkdir(parents=True, exist_ok=True)
    columns, rows = 4, 4
    cell_width, cell_height = 420, 310
    margin = 16
    page_size = columns * rows
    font = ImageFont.load_default()
    outputs: list[str] = []
    for page_index in range(0, len(records), page_size):
        page_records = records[page_index : page_index + page_size]
        sheet = Image.new(
            "RGB",
            (columns * cell_width, rows * cell_height),
            (235, 235, 235),
        )
        draw = ImageDraw.Draw(sheet)
        for local_index, record in enumerate(page_records):
            column = local_index % columns
            row = local_index // columns
            x = column * cell_width
            y = row * cell_height
            image_path = output_dir / str(record["path"])
            with Image.open(image_path) as source:
                preview = ImageOps.contain(
                    source.convert("RGB"),
                    (cell_width - 2 * margin, 210),
                    Image.Resampling.LANCZOS,
                )
            px = x + (cell_width - preview.width) // 2
            py = y + margin
            sheet.paste(preview, (px, py))
            title = f"{record['pool_id']}  {record['suggestion']}"
            draw.text((x + margin, y + 230), title, fill=(0, 0, 0), font=font)
            caption_lines = _wrapped_text(draw, str(record.get("caption", "")), cell_width - 2 * margin)
            for line_index, line in enumerate(caption_lines[:4]):
                draw.text(
                    (x + margin, y + 246 + line_index * 13),
                    line,
                    fill=(40, 40, 40),
                    font=font,
                )
        page_number = page_index // page_size + 1
        output = sheet_dir / f"pool-{page_number:02d}.png"
        sheet.save(output)
        outputs.append(str(output.relative_to(output_dir)).replace("\\", "/"))
    return outputs


def build_pool(
    *,
    output_dir: Path,
    root: Path,
    dataset: str,
    revision: str,
    count: int,
    seed: int,
    workers: int,
    minimum_source_bytes: int,
    maximum_source_bytes: int,
) -> dict[str, object]:
    output_dir = output_dir.resolve()
    root = root.resolve()
    manifest_path = output_dir / "pool_manifest.json"
    if manifest_path.exists():
        raise RuntimeError(f"refusing to overwrite existing pool manifest: {manifest_path}")
    output_dir.mkdir(parents=True, exist_ok=True)
    image_dir = output_dir / "images"
    image_dir.mkdir(parents=True, exist_ok=True)

    consumed = discover_consumed_shards(root)
    shards = [
        shard
        for shard in list_hub_shards(
            dataset,
            revision=revision,
            minimum_bytes=minimum_source_bytes,
            maximum_bytes=maximum_source_bytes,
        )
        if shard.path not in consumed
    ]
    random.Random(seed).shuffle(shards)
    if len(shards) < count:
        raise RuntimeError(f"only {len(shards)} eligible unused shards for requested count {count}")

    records: list[dict[str, object]] = []
    attempted = 0
    cursor = 0
    batch_size = max(workers * 3, 24)
    while len(records) < count and cursor < len(shards):
        batch = shards[cursor : cursor + batch_size]
        cursor += len(batch)
        attempted += len(batch)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    _materialize_one,
                    cursor - len(batch) + local_index,
                    shard,
                    dataset=dataset,
                    revision=revision,
                ): shard
                for local_index, shard in enumerate(batch)
            }
            completed: list[tuple[int, dict[str, object], bytes]] = []
            for future in as_completed(futures):
                try:
                    result = future.result()
                except (OSError, RuntimeError):
                    continue
                if result is not None:
                    completed.append(result)
        for _, record, png_payload in sorted(completed, key=lambda item: item[0]):
            if len(records) >= count:
                break
            pool_id = f"P{len(records) + 1:03d}"
            shard_stem = Path(str(record["source"]["shard"])).stem
            relative_path = f"images/{pool_id}-{shard_stem}.png"
            (output_dir / relative_path).write_bytes(png_payload)
            record["pool_id"] = pool_id
            record["path"] = relative_path
            records.append(record)

    if len(records) < count:
        raise RuntimeError(f"only materialized {len(records)} valid images after {attempted} attempts")
    contact_sheets = _contact_sheets(records, output_dir)
    manifest: dict[str, object] = {
        "schema_version": "phase16_sample_pool_v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "Manual visual selection pool; not an acceptance split.",
        "dataset": dataset,
        "revision": revision,
        "selection_seed": seed,
        "requested_count": count,
        "attempted_shards": attempted,
        "excluded_consumed_shards": len(consumed),
        "source_size_range": [minimum_source_bytes, maximum_source_bytes],
        "contact_sheets": contact_sheets,
        "records": records,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--revision", default=DEFAULT_REVISION)
    parser.add_argument("--count", type=int, default=160)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--minimum-source-bytes", type=int, default=15_000)
    parser.add_argument("--maximum-source-bytes", type=int, default=2_500_000)
    args = parser.parse_args(argv)
    if args.count <= 0 or args.workers <= 0:
        parser.error("count and workers must be positive")
    try:
        manifest = build_pool(
            output_dir=args.output_dir,
            root=args.root,
            dataset=args.dataset,
            revision=args.revision,
            count=args.count,
            seed=args.seed,
            workers=args.workers,
            minimum_source_bytes=args.minimum_source_bytes,
            maximum_source_bytes=args.maximum_source_bytes,
        )
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))
    print(
        json.dumps(
            {
                "records": len(manifest["records"]),
                "attempted_shards": manifest["attempted_shards"],
                "contact_sheets": manifest["contact_sheets"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
