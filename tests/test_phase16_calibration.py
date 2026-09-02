from __future__ import annotations

import csv
from pathlib import Path

import pytest

from tools.calibrate_edit_operation_time import summarize_measurements


def _protocol() -> dict[str, object]:
    return {
        "minimum_repetitions_per_operation": 3,
        "operations": [{"id": "create"}, {"id": "delete"}],
    }


def _write(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["operation_id", "repetition", "seconds", "valid", "note"]
        )
        writer.writeheader()
        writer.writerows(rows)


def test_calibration_uses_all_valid_trials_and_reports_median(tmp_path: Path) -> None:
    path = tmp_path / "measurements.csv"
    rows = []
    for operation in ("create", "delete"):
        for repetition, seconds in enumerate((3.0, 1.0, 2.0), start=1):
            rows.append(
                {
                    "operation_id": operation,
                    "repetition": repetition,
                    "seconds": seconds,
                    "valid": "true",
                    "note": "",
                }
            )
    _write(path, rows)

    result = summarize_measurements(_protocol(), path)

    assert result["create"]["valid_trials"] == 3
    assert result["create"]["median_seconds"] == 2.0
    assert result["delete"]["raw_seconds"] == [3.0, 1.0, 2.0]


def test_calibration_rejects_incomplete_or_duplicate_trials(tmp_path: Path) -> None:
    incomplete = tmp_path / "incomplete.csv"
    _write(
        incomplete,
        [
            {
                "operation_id": operation,
                "repetition": repetition,
                "seconds": 1.0,
                "valid": "true",
                "note": "",
            }
            for operation in ("create", "delete")
            for repetition in (1, 2)
        ],
    )
    with pytest.raises(ValueError, match="incomplete"):
        summarize_measurements(_protocol(), incomplete)

    duplicate = tmp_path / "duplicate.csv"
    _write(
        duplicate,
        [
            {
                "operation_id": operation,
                "repetition": repetition,
                "seconds": 1.0,
                "valid": "true",
                "note": "",
            }
            for operation in ("create", "delete")
            for repetition in (1, 1, 2)
        ],
    )
    with pytest.raises(ValueError, match="duplicate repetition"):
        summarize_measurements(_protocol(), duplicate)
