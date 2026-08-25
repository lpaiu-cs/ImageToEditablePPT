from __future__ import annotations

import torch

from image_to_editable_ppt.ml.dataset import NODE_KIND_LABELS
from image_to_editable_ppt.ml.detection_postprocess import select_detection_indices


def test_cross_kind_nms_suppresses_node_duplicates_but_preserves_container() -> None:
    container_label = max(NODE_KIND_LABELS.values()) + 1
    prediction = {
        "boxes": torch.tensor(
            [
                [0.0, 0.0, 20.0, 20.0],
                [1.0, 1.0, 21.0, 21.0],
                [0.0, 0.0, 20.0, 20.0],
                [40.0, 40.0, 60.0, 60.0],
            ]
        ),
        "scores": torch.tensor([0.95, 0.90, 0.85, 0.80]),
        "labels": torch.tensor([1, 2, container_label, 2]),
    }

    kept = select_detection_indices(prediction, score_threshold=0.5, cross_class_nms_iou=0.7)

    assert kept == [0, 2, 3]


def test_detection_selection_rejects_low_score_and_invalid_geometry() -> None:
    prediction = {
        "boxes": torch.tensor([[0.0, 0.0, 10.0, 10.0], [5.0, 5.0, 5.0, 8.0]]),
        "scores": torch.tensor([0.2, 0.9]),
        "labels": torch.tensor([1, 1]),
    }

    assert select_detection_indices(prediction, score_threshold=0.5) == []


def test_node_containment_suppresses_partial_cross_kind_duplicate() -> None:
    prediction = {
        "boxes": torch.tensor([[0.0, 0.0, 20.0, 20.0], [3.0, 3.0, 17.0, 17.0]]),
        "scores": torch.tensor([0.95, 0.90]),
        "labels": torch.tensor([1, 2]),
    }

    assert select_detection_indices(prediction, score_threshold=0.5) == [0]
