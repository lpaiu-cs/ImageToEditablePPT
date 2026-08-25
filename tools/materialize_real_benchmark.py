"""Materialize externally hosted real-figure benchmark samples with hash checks."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import urllib.parse
import urllib.request
from pathlib import Path


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _extract_image(parquet_payload: bytes, *, row_index: int) -> bytes:
    try:
        import pyarrow.parquet as pq
    except ImportError as error:
        raise RuntimeError("pyarrow is required to materialize parquet-backed figures") from error
    table = pq.read_table(io.BytesIO(parquet_payload), columns=["image"])
    if row_index < 0 or row_index >= table.num_rows:
        raise RuntimeError(f"row {row_index} is outside shard with {table.num_rows} rows")
    image_payload = table.column("image")[row_index].as_py()
    if not isinstance(image_payload, bytes):
        raise RuntimeError("parquet image column did not contain bytes")
    return image_payload


def _normalize_png(image_payload: bytes) -> bytes:
    from PIL import Image

    output = io.BytesIO()
    Image.open(io.BytesIO(image_payload)).convert("RGB").save(output, format="PNG")
    return output.getvalue()


def materialize(manifest_path: Path, *, root: Path) -> dict[str, object]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    records: list[dict[str, object]] = []
    for sample in manifest["samples"]:
        target = root / sample["path"]
        source = sample["source"]
        if source["type"] == "repository":
            if not target.exists():
                raise FileNotFoundError(target)
        elif source["type"] == "huggingface_parquet":
            shard = urllib.parse.quote(source["shard"])
            url = (
                f"https://huggingface.co/datasets/{source['dataset']}/resolve/"
                f"{source['revision']}/{shard}?download=true"
            )
            with urllib.request.urlopen(url) as response:
                parquet_payload = response.read()
            if _sha256_bytes(parquet_payload) != source["sha256"]:
                raise RuntimeError(f"source hash mismatch for {sample['id']}")
            image_payload = _normalize_png(
                _extract_image(parquet_payload, row_index=int(source["row"]))
            )
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(image_payload)
        else:
            raise ValueError(f"unsupported source type: {source['type']}")
        actual = _sha256_file(target)
        if actual != sample["sha256"]:
            raise RuntimeError(f"image hash mismatch for {sample['id']}: {actual}")
        records.append({"id": sample["id"], "path": str(target), "sha256": actual})
    return {"manifest": str(manifest_path), "materialized": records}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, nargs="?", default=Path("benchmarks/real_v1/manifest.json"))
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args(argv)
    try:
        result = materialize(args.manifest, root=args.root.resolve())
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError, RuntimeError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
