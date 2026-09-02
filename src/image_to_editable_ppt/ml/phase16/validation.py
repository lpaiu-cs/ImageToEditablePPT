"""Validation for Phase 16 manifests and manual annotation v2 files."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from PIL import Image

from .models import (
    ANNOTATION_SCHEMA_VERSION,
    MANIFEST_SCHEMA_VERSION,
    AnnotationDocument,
    Importance,
    ObjectRole,
    Phase16ModelError,
    SampleKind,
)


class ValidationError(ValueError):
    """Raised when frozen Phase 16 evidence is incomplete or inconsistent."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def perceptual_hash_distance(first: str, second: str) -> int:
    if len(first) != 16 or len(second) != 16:
        raise ValidationError("perceptual hashes must be 16 hexadecimal characters")
    try:
        return (int(first, 16) ^ int(second, 16)).bit_count()
    except ValueError as error:
        raise ValidationError("perceptual hashes must be hexadecimal") from error


def _load_json(path: Path, label: str) -> Mapping[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValidationError(f"cannot read {label} {path}: {error}") from error
    if not isinstance(raw, Mapping):
        raise ValidationError(f"{label} {path} must contain a JSON object")
    return raw


def _resolve_inside(root: Path, relative: object, label: str) -> Path:
    if not isinstance(relative, str) or not relative:
        raise ValidationError(f"{label} must be a non-empty path")
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise ValidationError(f"{label} escapes repository root: {relative}") from error
    return candidate


def _validate_hex_digest(value: object, label: str, *, length: int) -> str:
    if not isinstance(value, str) or len(value) != length:
        raise ValidationError(f"{label} must contain {length} hexadecimal characters")
    try:
        int(value, 16)
    except ValueError as error:
        raise ValidationError(f"{label} must be hexadecimal") from error
    return value.lower()


def _validate_annotation(
    document: AnnotationDocument,
    *,
    sample: Mapping[str, object],
    root: Path,
    require_frozen: bool,
) -> dict[str, int]:
    if document.schema_version != ANNOTATION_SCHEMA_VERSION:
        raise ValidationError(
            f"{document.sample_id}: unsupported annotation schema {document.schema_version}"
        )
    if document.sample_id != sample.get("id"):
        raise ValidationError(
            f"annotation sample id {document.sample_id} does not match manifest {sample.get('id')}"
        )
    try:
        sample_kind = SampleKind(sample.get("kind"))
    except (TypeError, ValueError) as error:
        raise ValidationError(f"{document.sample_id}: invalid manifest sample kind") from error
    if document.kind is not sample_kind:
        raise ValidationError(f"{document.sample_id}: annotation kind does not match manifest")

    image_path = _resolve_inside(root, sample.get("path"), f"{document.sample_id}.path")
    if document.image_path != sample.get("path"):
        raise ValidationError(f"{document.sample_id}: annotation image path does not match manifest")
    if not image_path.is_file():
        raise ValidationError(f"{document.sample_id}: image is missing: {image_path}")
    expected_sha = _validate_hex_digest(
        sample.get("sha256"), f"{document.sample_id}.sha256", length=64
    )
    actual_sha = sha256_file(image_path)
    if actual_sha != expected_sha or document.image_sha256 != expected_sha:
        raise ValidationError(f"{document.sample_id}: image SHA-256 mismatch")
    with Image.open(image_path) as image:
        if image.size != (document.image_width, document.image_height):
            raise ValidationError(f"{document.sample_id}: annotation image size mismatch")

    if document.image_width <= 0 or document.image_height <= 0:
        raise ValidationError(f"{document.sample_id}: image dimensions must be positive")
    image_bbox = document.image_bbox
    identifiers = [item.id for item in document.objects]
    identifiers.extend(item.id for item in document.connectors)
    identifiers.extend(item.id for item in document.excluded_regions)
    duplicates = [item_id for item_id, count in Counter(identifiers).items() if count > 1]
    if duplicates:
        raise ValidationError(f"{document.sample_id}: duplicate annotation ids: {duplicates}")

    object_by_id = {item.id: item for item in document.objects}
    for item in document.objects:
        if not image_bbox.contains_bbox(item.bbox):
            raise ValidationError(f"{document.sample_id}: object {item.id} bbox is outside image")
        if item.label is not None:
            if item.label.legible and not item.label.text:
                raise ValidationError(f"{document.sample_id}: legible label {item.id} is empty")
            if not item.label.legible and item.label.text:
                raise ValidationError(
                    f"{document.sample_id}: illegible label {item.id} must not guess text"
                )
        if item.parent_id is None:
            continue
        parent = object_by_id.get(item.parent_id)
        if parent is None:
            raise ValidationError(
                f"{document.sample_id}: object {item.id} has dangling parent {item.parent_id}"
            )
        if parent.role is not ObjectRole.CONTAINER:
            raise ValidationError(
                f"{document.sample_id}: parent {parent.id} is not a container"
            )
        if not parent.bbox.contains_bbox(item.bbox, tolerance=1.0):
            raise ValidationError(
                f"{document.sample_id}: parent {parent.id} does not contain {item.id}"
            )

    for item in document.objects:
        seen: set[str] = set()
        cursor = item
        while cursor.parent_id is not None:
            if cursor.parent_id in seen or cursor.parent_id == item.id:
                raise ValidationError(f"{document.sample_id}: containment cycle at {item.id}")
            seen.add(cursor.parent_id)
            cursor = object_by_id[cursor.parent_id]

    for connector in document.connectors:
        if connector.source_id not in object_by_id or connector.target_id not in object_by_id:
            raise ValidationError(
                f"{document.sample_id}: connector {connector.id} has dangling endpoint"
            )
        if connector.source_id == connector.target_id:
            raise ValidationError(f"{document.sample_id}: connector {connector.id} is a self-loop")
        if len(connector.path_points) < 2:
            raise ValidationError(
                f"{document.sample_id}: connector {connector.id} needs at least two path points"
            )
        if any(not image_bbox.contains_point(point, tolerance=1.0) for point in connector.path_points):
            raise ValidationError(
                f"{document.sample_id}: connector {connector.id} path leaves image bounds"
            )

    for region in document.excluded_regions:
        if not image_bbox.contains_bbox(region.bbox):
            raise ValidationError(
                f"{document.sample_id}: excluded region {region.id} bbox is outside image"
            )

    if document.kind is SampleKind.NON_DIAGRAM and (document.objects or document.connectors):
        raise ValidationError(
            f"{document.sample_id}: non-diagram annotation must not contain structural output"
        )
    if require_frozen:
        pass_ids = [item.pass_id for item in document.review_passes]
        if document.review_status != "resolved":
            raise ValidationError(f"{document.sample_id}: review status must be resolved")
        if len(set(pass_ids)) < 2:
            raise ValidationError(f"{document.sample_id}: two distinct review passes are required")
        required_focus = {"object_roles", "connector_endpoints", "excluded_regions"}
        actual_focus = {focus for item in document.review_passes for focus in item.focus}
        if not required_focus.issubset(actual_focus):
            raise ValidationError(
                f"{document.sample_id}: second-pass focus is incomplete: "
                f"{sorted(required_focus - actual_focus)}"
            )

    return {
        "objects": len(document.objects),
        "core_objects": sum(item.importance is Importance.CORE for item in document.objects),
        "connectors": len(document.connectors),
        "core_connectors": sum(
            item.importance is Importance.CORE for item in document.connectors
        ),
        "excluded_regions": len(document.excluded_regions),
    }


def validate_phase16_manifest(
    manifest_path: Path,
    *,
    root: Path,
    require_frozen: bool = False,
) -> dict[str, Any]:
    root = root.resolve()
    manifest_path = manifest_path.resolve()
    raw = _load_json(manifest_path, "manifest")
    if raw.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise ValidationError(f"unsupported manifest schema in {manifest_path}")
    split = raw.get("split")
    if split not in {"dev", "holdout"}:
        raise ValidationError(f"manifest split must be dev or holdout in {manifest_path}")
    samples = raw.get("samples")
    if not isinstance(samples, list) or not samples:
        raise ValidationError(f"manifest samples must be a non-empty list in {manifest_path}")

    counts: Counter[str] = Counter()
    strata: Counter[str] = Counter()
    source_keys: set[tuple[str, str, int]] = set()
    source_groups: set[str] = set()
    content_hashes: set[str] = set()
    perceptual_hashes: dict[str, str] = {}
    sample_ids: set[str] = set()
    totals: Counter[str] = Counter()
    low_connectivity = 0

    for index, sample_raw in enumerate(samples):
        if not isinstance(sample_raw, Mapping):
            raise ValidationError(f"sample {index} in {manifest_path} must be an object")
        sample_id = sample_raw.get("id")
        if not isinstance(sample_id, str) or not sample_id:
            raise ValidationError(f"sample {index} in {manifest_path} has invalid id")
        if sample_id in sample_ids:
            raise ValidationError(f"duplicate sample id {sample_id} in {manifest_path}")
        sample_ids.add(sample_id)
        try:
            kind = SampleKind(sample_raw.get("kind"))
        except (TypeError, ValueError) as error:
            raise ValidationError(f"{sample_id}: invalid sample kind") from error
        stratum = sample_raw.get("stratum")
        if not isinstance(stratum, str) or not stratum:
            raise ValidationError(f"{sample_id}: stratum must be a non-empty string")
        counts[kind.value] += 1
        strata[stratum] += 1
        low_connectivity += int(bool(sample_raw.get("low_connectivity", False)))

        content_hash = _validate_hex_digest(
            sample_raw.get("sha256"), f"{sample_id}.sha256", length=64
        )
        perceptual_hash = _validate_hex_digest(
            sample_raw.get("perceptual_hash"), f"{sample_id}.perceptual_hash", length=16
        )
        if content_hash in content_hashes:
            raise ValidationError(f"duplicate content hash in {manifest_path}: {sample_id}")
        if perceptual_hash in perceptual_hashes:
            raise ValidationError(
                f"duplicate perceptual hash: {sample_id} and {perceptual_hashes[perceptual_hash]}"
            )
        content_hashes.add(content_hash)
        perceptual_hashes[perceptual_hash] = sample_id

        source_group = sample_raw.get("source_group")
        if not isinstance(source_group, str) or not source_group:
            raise ValidationError(f"{sample_id}: source_group must be recorded")
        source_groups.add(source_group)
        source = sample_raw.get("source")
        if not isinstance(source, Mapping) or source.get("type") != "huggingface_parquet":
            raise ValidationError(f"{sample_id}: Phase 16 source must bind a parquet row")
        revision = source.get("revision")
        shard = source.get("shard")
        row = source.get("row")
        if not isinstance(revision, str) or len(revision) < 7:
            raise ValidationError(f"{sample_id}: source revision is missing")
        if not isinstance(shard, str) or not shard.endswith(".parquet"):
            raise ValidationError(f"{sample_id}: source shard is invalid")
        if not isinstance(row, int) or row < 0:
            raise ValidationError(f"{sample_id}: source row is invalid")
        source_sha = _validate_hex_digest(
            source.get("sha256"), f"{sample_id}.source.sha256", length=64
        )
        del source_sha
        key = (revision, shard, row)
        if key in source_keys:
            raise ValidationError(f"duplicate source row in {manifest_path}: {sample_id}")
        source_keys.add(key)

        annotation_path = _resolve_inside(
            root, sample_raw.get("annotation"), f"{sample_id}.annotation"
        )
        annotation_raw = _load_json(annotation_path, "annotation")
        try:
            document = AnnotationDocument.from_dict(annotation_raw)
        except Phase16ModelError as error:
            raise ValidationError(f"{sample_id}: {error}") from error
        record = _validate_annotation(
            document,
            sample=sample_raw,
            root=root,
            require_frozen=require_frozen,
        )
        totals.update(record)

    minimum = 20 if split == "dev" else 12
    if require_frozen:
        for kind in SampleKind:
            if counts[kind.value] < minimum:
                raise ValidationError(
                    f"{split} requires at least {minimum} {kind.value} samples"
                )
        required_diagram_strata = {
            "simple_direct_orthogonal",
            "nested_gradient_shadow",
            "connector_dense_orthogonal_elbow",
        }
        missing_strata = required_diagram_strata - set(strata)
        if missing_strata:
            raise ValidationError(f"{split} is missing diagram strata: {sorted(missing_strata)}")
        if split == "holdout" and low_connectivity < 2:
            raise ValidationError("holdout requires at least two low-connectivity diagrams")

    return {
        "manifest": str(manifest_path),
        "manifest_sha256": sha256_file(manifest_path),
        "split": split,
        "samples": len(samples),
        "counts": dict(sorted(counts.items())),
        "strata": dict(sorted(strata.items())),
        "source_keys": source_keys,
        "source_groups": source_groups,
        "content_hashes": content_hashes,
        "perceptual_hashes": perceptual_hashes,
        "annotation_totals": dict(sorted(totals.items())),
    }


def validate_phase16_manifests(
    dev_manifest: Path,
    holdout_manifest: Path,
    *,
    root: Path,
    require_frozen: bool = False,
    near_duplicate_distance: int = 6,
) -> dict[str, Any]:
    dev = validate_phase16_manifest(dev_manifest, root=root, require_frozen=require_frozen)
    holdout = validate_phase16_manifest(
        holdout_manifest, root=root, require_frozen=require_frozen
    )
    if dev["split"] != "dev" or holdout["split"] != "holdout":
        raise ValidationError("dev and holdout manifests were passed in the wrong order")

    overlap = dev["source_keys"] & holdout["source_keys"]
    if overlap:
        raise ValidationError(f"dev/holdout source-row overlap: {sorted(overlap)}")
    group_overlap = dev["source_groups"] & holdout["source_groups"]
    if group_overlap:
        raise ValidationError(f"dev/holdout source-group overlap: {sorted(group_overlap)}")
    content_overlap = dev["content_hashes"] & holdout["content_hashes"]
    if content_overlap:
        raise ValidationError("dev/holdout content SHA-256 overlap")
    for dev_hash, dev_id in dev["perceptual_hashes"].items():
        for holdout_hash, holdout_id in holdout["perceptual_hashes"].items():
            distance = perceptual_hash_distance(dev_hash, holdout_hash)
            if distance <= near_duplicate_distance:
                raise ValidationError(
                    "dev/holdout perceptual near-duplicate: "
                    f"{dev_id} vs {holdout_id} (distance={distance})"
                )

    def _public(summary: Mapping[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in summary.items()
            if key
            not in {
                "source_keys",
                "source_groups",
                "content_hashes",
                "perceptual_hashes",
            }
        }

    return {
        "schema_version": "phase16_validation_report_v1",
        "frozen_contract_enforced": require_frozen,
        "near_duplicate_distance": near_duplicate_distance,
        "dev": _public(dev),
        "holdout": _public(holdout),
    }
