from __future__ import annotations

import pytest

from tools.evaluate_diagram_gate import _threshold_summary


def test_threshold_summary_separates_recall_and_rejection() -> None:
    samples = [
        {"kind": "diagram", "p_diagram": 0.9},
        {"kind": "diagram", "p_diagram": 0.4},
        {"kind": "non_diagram", "p_diagram": 0.2},
        {"kind": "non_diagram", "p_diagram": 0.7},
    ]
    summary = _threshold_summary(samples, 0.5)
    assert summary["diagram_recall"] == pytest.approx(0.5)
    assert summary["nondiagram_reject_rate"] == pytest.approx(0.5)
    assert summary["accuracy"] == pytest.approx(0.5)
