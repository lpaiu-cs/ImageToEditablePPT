from __future__ import annotations

import json

import pytest

from image_to_editable_ppt.ml.model_bundle import (
    BUNDLE_SCHEMA_VERSION,
    ModelBundleError,
    artifact_record,
    load_model_bundle,
)


def test_model_bundle_loads_and_verifies_checkpoint_hash(tmp_path):
    checkpoint = tmp_path / "detector.ckpt"
    checkpoint.write_bytes(b"trusted checkpoint")
    bundle_path = tmp_path / "model_bundle.json"
    bundle_path.write_text(
        json.dumps(
            {
                "schema_version": BUNDLE_SCHEMA_VERSION,
                "status": "candidate",
                "checkpoints": {
                    "detector": artifact_record(checkpoint, relative_to=tmp_path),
                    "family": None,
                    "segmenter": None,
                    "gate": None,
                    "relation": None,
                },
                "settings": {"connector_strategy": "morphological"},
            }
        ),
        encoding="utf-8",
    )

    loaded = load_model_bundle(bundle_path)

    assert loaded.checkpoints["detector"] == checkpoint
    assert loaded.status == "candidate"
    assert loaded.settings["connector_strategy"] == "morphological"


def test_model_bundle_fails_closed_when_checkpoint_changes(tmp_path):
    checkpoint = tmp_path / "detector.ckpt"
    checkpoint.write_bytes(b"original")
    bundle_path = tmp_path / "model_bundle.json"
    bundle_path.write_text(
        json.dumps(
            {
                "schema_version": BUNDLE_SCHEMA_VERSION,
                "status": "canonical",
                "checkpoints": {"detector": artifact_record(checkpoint, relative_to=tmp_path)},
            }
        ),
        encoding="utf-8",
    )
    checkpoint.write_bytes(b"tampered")

    with pytest.raises(ModelBundleError, match="checksum mismatch"):
        load_model_bundle(bundle_path)


def test_model_bundle_fails_closed_when_evidence_changes(tmp_path):
    checkpoint = tmp_path / "detector.ckpt"
    evidence = tmp_path / "evidence.json"
    checkpoint.write_bytes(b"trusted checkpoint")
    evidence.write_text("{}", encoding="utf-8")
    bundle_path = tmp_path / "model_bundle.json"
    bundle_path.write_text(
        json.dumps(
            {
                "schema_version": BUNDLE_SCHEMA_VERSION,
                "status": "candidate",
                "checkpoints": {"detector": artifact_record(checkpoint, relative_to=tmp_path)},
                "evidence": [artifact_record(evidence, relative_to=tmp_path)],
            }
        ),
        encoding="utf-8",
    )
    evidence.write_text('{"changed": true}', encoding="utf-8")

    with pytest.raises(ModelBundleError, match=r"evidence\[0\] checksum mismatch"):
        load_model_bundle(bundle_path)


def test_cli_rejects_candidate_bundle_without_explicit_opt_in(tmp_path):
    from image_to_editable_ppt.ml.convert_to_pptx import _build_provider, build_parser

    checkpoint = tmp_path / "detector.ckpt"
    checkpoint.write_bytes(b"checkpoint")
    bundle_path = tmp_path / "model_bundle.json"
    bundle_path.write_text(
        json.dumps(
            {
                "schema_version": BUNDLE_SCHEMA_VERSION,
                "status": "candidate",
                "checkpoints": {"detector": artifact_record(checkpoint, relative_to=tmp_path)},
            }
        ),
        encoding="utf-8",
    )
    args = build_parser().parse_args(["figure.png", "--bundle", str(bundle_path), "--no-gate"])

    with pytest.raises(SystemExit, match="not canonical"):
        _build_provider(args)
