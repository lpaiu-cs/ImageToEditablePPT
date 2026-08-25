from __future__ import annotations

import pytest

from tools.evaluate_detector_checkpoint import _iou, _match_count, _metrics


def test_iou_and_class_aware_matching() -> None:
    assert _iou([0, 0, 10, 10], [5, 0, 15, 10]) == pytest.approx(1 / 3)
    assert _match_count(
        [[0, 0, 10, 10], [20, 20, 30, 30]],
        [1, 2],
        [[0, 0, 10, 10], [20, 20, 30, 30]],
        [2, 2],
        iou_threshold=0.5,
    ) == 1


def test_metrics_reports_micro_counts() -> None:
    metrics = _metrics(true_positive=3, prediction_count=4, reference_count=5)
    assert metrics["precision"] == pytest.approx(0.75)
    assert metrics["recall"] == pytest.approx(0.6)
    assert metrics["f1"] == pytest.approx(2 / 3)
    assert metrics["false_positive"] == 1
    assert metrics["false_negative"] == 2
