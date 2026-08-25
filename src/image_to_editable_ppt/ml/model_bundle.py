"""Versioned, checksum-bound model bundle contract for reproducible inference."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from typing import Mapping

BUNDLE_SCHEMA_VERSION = "image_to_editable_ppt_model_bundle_v1"
CHECKPOINT_ROLES = ("detector", "family", "segmenter", "gate", "relation")


class ModelBundleError(ValueError):
    """A bundle cannot be trusted or used for inference."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(slots=True, frozen=True)
class LoadedModelBundle:
    path: Path
    status: str
    checkpoints: Mapping[str, Path | None]
    settings: Mapping[str, object]
    document: Mapping[str, object]

    @property
    def sha256(self) -> str:
        return sha256_file(self.path)


def _resolve_artifact(bundle_path: Path, record: Mapping[str, object], *, label: str) -> Path:
    raw_path = record.get("path")
    expected_sha = record.get("sha256")
    if not isinstance(raw_path, str) or not raw_path:
        raise ModelBundleError(f"{label} path is missing")
    if not isinstance(expected_sha, str) or len(expected_sha) != 64:
        raise ModelBundleError(f"{label} sha256 is missing or malformed")
    path = (bundle_path.parent / raw_path).resolve()
    if not path.is_file():
        raise ModelBundleError(f"{label} file not found: {path}")
    actual_sha = sha256_file(path)
    if actual_sha != expected_sha.lower():
        raise ModelBundleError(
            f"{label} checksum mismatch: expected {expected_sha.lower()}, got {actual_sha}"
        )
    return path


def load_model_bundle(path: str | Path) -> LoadedModelBundle:
    bundle_path = Path(path).resolve()
    try:
        document = json.loads(bundle_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ModelBundleError(f"model bundle not found: {bundle_path}") from error
    except json.JSONDecodeError as error:
        raise ModelBundleError(f"invalid model bundle JSON: {error}") from error
    if document.get("schema_version") != BUNDLE_SCHEMA_VERSION:
        raise ModelBundleError(f"unsupported model bundle schema: {document.get('schema_version')!r}")
    status = document.get("status")
    if status not in {"candidate", "canonical"}:
        raise ModelBundleError(f"invalid model bundle status: {status!r}")
    raw_checkpoints = document.get("checkpoints")
    if not isinstance(raw_checkpoints, dict):
        raise ModelBundleError("bundle checkpoints must be an object")
    checkpoints: dict[str, Path | None] = {}
    for role in CHECKPOINT_ROLES:
        record = raw_checkpoints.get(role)
        if record is None:
            checkpoints[role] = None
            continue
        if not isinstance(record, dict):
            raise ModelBundleError(f"checkpoint record for {role} must be an object or null")
        checkpoints[role] = _resolve_artifact(bundle_path, record, label=f"checkpoint:{role}")
    if checkpoints["detector"] is None:
        raise ModelBundleError("detector checkpoint is required")
    verified_supporting_artifacts: dict[str, tuple[Path, ...]] = {}
    for field in ("training_manifests", "evidence"):
        records = document.get(field, [])
        if not isinstance(records, list):
            raise ModelBundleError(f"bundle {field} must be an array")
        verified: list[Path] = []
        for index, record in enumerate(records):
            if not isinstance(record, dict):
                raise ModelBundleError(f"{field}[{index}] must be an object")
            verified.append(_resolve_artifact(bundle_path, record, label=f"{field}[{index}]"))
        verified_supporting_artifacts[field] = tuple(verified)
    if status == "canonical":
        missing = [role for role in ("detector", "family", "gate") if checkpoints[role] is None]
        if missing:
            raise ModelBundleError(f"canonical bundle requires checkpoints: {', '.join(missing)}")
        if not verified_supporting_artifacts["training_manifests"]:
            raise ModelBundleError("canonical bundle requires at least one training manifest")
        if not verified_supporting_artifacts["evidence"]:
            raise ModelBundleError("canonical bundle requires at least one evidence artifact")
    settings = document.get("settings", {})
    if not isinstance(settings, dict):
        raise ModelBundleError("bundle settings must be an object")
    strategy = settings.get("connector_strategy", "morphological")
    if strategy not in {"morphological", "segmenter", "relation"}:
        raise ModelBundleError(f"invalid connector strategy: {strategy!r}")
    for key in ("detector_threshold", "gate_threshold"):
        if key in settings and not 0.0 <= float(settings[key]) <= 1.0:
            raise ModelBundleError(f"{key} must be between 0 and 1")
    if "detector_nms_iou" in settings and not 0.0 < float(settings["detector_nms_iou"]) <= 1.0:
        raise ModelBundleError("detector_nms_iou must be in (0, 1]")
    if "node_containment_threshold" in settings and not 0.0 < float(settings["node_containment_threshold"]) <= 1.0:
        raise ModelBundleError("node_containment_threshold must be in (0, 1]")
    return LoadedModelBundle(
        path=bundle_path,
        status=status,
        checkpoints=checkpoints,
        settings=settings,
        document=document,
    )


def artifact_record(path: Path, *, relative_to: Path) -> dict[str, object]:
    resolved = path.resolve()
    if not resolved.is_file():
        raise ModelBundleError(f"artifact file not found: {resolved}")
    return {
        "path": Path(os.path.relpath(resolved, relative_to.resolve())).as_posix(),
        "sha256": sha256_file(resolved),
        "bytes": resolved.stat().st_size,
    }
