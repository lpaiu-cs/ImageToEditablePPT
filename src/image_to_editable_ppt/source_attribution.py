from __future__ import annotations

from collections import Counter
from enum import StrEnum
from typing import Iterable


class SourceBucket(StrEnum):
    GEOMETRY_ONLY = "geometry_only"
    FALLBACK_ONLY = "fallback_only"
    MIXED_GEOMETRY_FALLBACK = "mixed_geometry_fallback"
    OTHER = "other"


GEOMETRY_PREFIXES = (
    "rect-candidate:",
    "connector-candidate:",
    "line-primitive:",
    "region-primitive:",
)

FALLBACK_PREFIXES = (
    "grow_fallback",
    "fallback-region:",
)


def is_geometry_source_id(source_id: str) -> bool:
    if any(source_id.startswith(prefix) for prefix in GEOMETRY_PREFIXES):
        return True
    return ":snapped" in source_id and source_id.startswith("rect-candidate:")


def is_fallback_source_id(source_id: str) -> bool:
    return source_id == "grow_fallback" or any(source_id.startswith(prefix) for prefix in FALLBACK_PREFIXES)


def classify_source_bucket(source_ids: Iterable[str] | None) -> SourceBucket:
    ids = tuple(str(source_id) for source_id in (source_ids or ()))
    has_geometry = any(is_geometry_source_id(source_id) for source_id in ids)
    has_fallback = any(is_fallback_source_id(source_id) for source_id in ids)
    if has_geometry and has_fallback:
        return SourceBucket.MIXED_GEOMETRY_FALLBACK
    if has_geometry:
        return SourceBucket.GEOMETRY_ONLY
    if has_fallback:
        return SourceBucket.FALLBACK_ONLY
    return SourceBucket.OTHER


def count_source_buckets(rows: Iterable[object]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for row in rows:
        source_ids = getattr(row, "source_ids", [])
        counts[classify_source_bucket(source_ids).value] += 1
    return {bucket.value: int(counts.get(bucket.value, 0)) for bucket in SourceBucket}


def normalize_kind(kind: str) -> str:
    normalized = str(kind).strip().lower()
    if normalized in {"rect", "rounded_rect", "box", "container", "panel"}:
        return "container"
    if normalized in {"line", "orthogonal_connector", "arrow", "connector", "solid_arrow"}:
        return "connector"
    if normalized in {"text", "textbox", "text_only"}:
        return "textbox"
    return normalized or "unknown"


def row_kind(row: object) -> str:
    return normalize_kind(getattr(row, "object_type", "") or getattr(row, "kind", ""))


def count_source_buckets_by_kind(rows: Iterable[object]) -> dict[str, dict[str, int]]:
    counts: dict[str, Counter[str]] = {}
    for row in rows:
        kind = row_kind(row)
        source_ids = getattr(row, "source_ids", [])
        counts.setdefault(kind, Counter())[classify_source_bucket(source_ids).value] += 1
    return {
        kind: {bucket.value: int(counter.get(bucket.value, 0)) for bucket in SourceBucket}
        for kind, counter in sorted(counts.items())
    }
