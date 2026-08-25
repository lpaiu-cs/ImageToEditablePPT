from __future__ import annotations

import pytest

from tools.evaluate_family_checkpoint import _summarize


def test_summary_builds_confusion_and_per_family_accuracy() -> None:
    report = _summarize([0, 1, 0], [0, 1, 1])
    assert report["accuracy"] == pytest.approx(2 / 3)
    assert report["confusion_matrix"][0][0] == 1
    assert report["confusion_matrix"][1][0] == 1
    assert report["per_family"][report["class_order"][1]]["accuracy"] == pytest.approx(0.5)
