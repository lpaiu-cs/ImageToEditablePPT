from __future__ import annotations

import json
from pathlib import Path

from image_to_editable_ppt.ml.phase16.validation import sha256_file
from tools.create_phase16_experiment_lock import validate_calibration


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def test_experiment_lock_rejects_missing_human_calibration(tmp_path: Path) -> None:
    protocol = tmp_path / "protocol.json"
    _write_json(
        protocol,
        {"minimum_repetitions_per_operation": 2, "operations": [{"id": "create"}]},
    )

    binding, blockers = validate_calibration(protocol, tmp_path / "missing.json")

    assert binding is None
    assert blockers and "human operation-time calibration is missing" in blockers[0]


def test_experiment_lock_accepts_bound_raw_human_timings(tmp_path: Path) -> None:
    protocol = tmp_path / "protocol.json"
    deck = tmp_path / "deck.pptx"
    measurements = tmp_path / "measurements.csv"
    calibration = tmp_path / "calibration.json"
    _write_json(
        protocol,
        {"minimum_repetitions_per_operation": 2, "operations": [{"id": "create"}]},
    )
    deck.write_bytes(b"deck")
    measurements.write_text("measurements", encoding="utf-8")
    _write_json(
        calibration,
        {
            "schema_version": "phase16_operation_time_calibration_v1",
            "status": "completed",
            "participant_id": "human-1",
            "powerpoint_version": "16.0",
            "protocol_sha256": sha256_file(protocol),
            "deck_path": str(deck),
            "deck_sha256": sha256_file(deck),
            "measurements_path": str(measurements),
            "measurements_sha256": sha256_file(measurements),
            "minimum_repetitions_per_operation": 2,
            "operation_times": {
                "create": {
                    "valid_trials": 2,
                    "median_seconds": 1.5,
                    "raw_seconds": [1.0, 2.0],
                }
            },
        },
    )

    binding, blockers = validate_calibration(protocol, calibration)

    assert blockers == []
    assert binding is not None
    assert binding["operation_median_seconds"] == {"create": 1.5}
