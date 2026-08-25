from __future__ import annotations

from tools.run_real_benchmark import _sample_acceptance


THRESHOLDS = {
    "diagram_min_primitive_fraction": 0.5,
    "diagram_min_connector_fraction": 0.5,
}


def test_diagram_acceptance_uses_verified_minimum_coverage():
    sample = {
        "kind": "diagram",
        "ground_truth": {
            "verified_min_primitives": 8,
            "verified_max_primitives": 12,
            "verified_min_connectors": 6,
            "verified_max_connectors": 10,
        },
    }

    passing = _sample_acceptance(sample, {"nodes": 4, "containers": 0, "connectors": 3}, THRESHOLDS)
    failing = _sample_acceptance(sample, {"nodes": 8, "containers": 0, "connectors": 2}, THRESHOLDS)

    assert passing["passed"] is True
    assert failing["passed"] is False


def test_diagram_acceptance_rejects_over_detection():
    sample = {
        "kind": "diagram",
        "ground_truth": {
            "verified_min_primitives": 3,
            "verified_max_primitives": 5,
            "verified_min_connectors": 2,
            "verified_max_connectors": 5,
        },
    }

    result = _sample_acceptance(sample, {"nodes": 12, "containers": 1, "connectors": 3}, THRESHOLDS)

    assert result["passed"] is False
    assert result["within_upper_bounds"] is False


def test_non_diagram_acceptance_requires_no_structure():
    sample = {"kind": "non_diagram"}

    assert _sample_acceptance(sample, {"nodes": 0, "containers": 0, "connectors": 0}, THRESHOLDS)["passed"]
    assert not _sample_acceptance(sample, {"nodes": 1, "containers": 0, "connectors": 0}, THRESHOLDS)["passed"]
