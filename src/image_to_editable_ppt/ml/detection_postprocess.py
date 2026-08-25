"""Precision-first post-processing shared by detector inference entry points."""
from __future__ import annotations

from collections.abc import Mapping

import torch
from torchvision.ops import batched_nms

from image_to_editable_ppt.ml.dataset import NODE_KIND_LABELS


def select_detection_indices(
    prediction: Mapping[str, torch.Tensor],
    *,
    score_threshold: float,
    cross_class_nms_iou: float = 0.7,
    node_containment_threshold: float = 0.85,
) -> list[int]:
    """Keep valid detections and suppress same-entity cross-kind duplicates.

    Torchvision Faster R-CNN applies NMS per class. During kind confusion, one
    physical box can therefore survive several times as different node kinds.
    We run a second NMS across node kinds and, separately, across container
    kinds so duplicates disappear without collapsing a node into its enclosing
    container.
    """
    if not 0.0 <= score_threshold <= 1.0:
        raise ValueError("score_threshold must be between 0 and 1")
    if not 0.0 < cross_class_nms_iou <= 1.0:
        raise ValueError("cross_class_nms_iou must be in (0, 1]")
    if not 0.0 < node_containment_threshold <= 1.0:
        raise ValueError("node_containment_threshold must be in (0, 1]")
    boxes = prediction["boxes"]
    scores = prediction["scores"]
    labels = prediction["labels"]
    valid_geometry = (boxes[:, 2] > boxes[:, 0]) & (boxes[:, 3] > boxes[:, 1])
    candidates = torch.nonzero((scores >= score_threshold) & valid_geometry, as_tuple=False).flatten()
    if candidates.numel() == 0:
        return []
    maximum_node_label = max(NODE_KIND_LABELS.values())
    entity_categories = (labels[candidates] > maximum_node_label).to(dtype=torch.int64)
    kept_relative = batched_nms(
        boxes[candidates],
        scores[candidates],
        entity_categories,
        cross_class_nms_iou,
    )
    nms_kept = candidates[kept_relative].detach().cpu().tolist()
    boxes_cpu = boxes.detach().cpu()
    labels_cpu = labels.detach().cpu()
    kept: list[int] = []
    kept_nodes: list[int] = []
    for index in nms_kept:
        is_node = int(labels_cpu[index]) <= maximum_node_label
        if is_node and any(
            _intersection_over_smaller(boxes_cpu[index], boxes_cpu[other]) >= node_containment_threshold
            for other in kept_nodes
        ):
            continue
        kept.append(index)
        if is_node:
            kept_nodes.append(index)
    return kept


def _intersection_over_smaller(first: torch.Tensor, second: torch.Tensor) -> float:
    ix0 = max(float(first[0]), float(second[0]))
    iy0 = max(float(first[1]), float(second[1]))
    ix1 = min(float(first[2]), float(second[2]))
    iy1 = min(float(first[3]), float(second[3]))
    intersection = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    first_area = max(0.0, float(first[2] - first[0])) * max(0.0, float(first[3] - first[1]))
    second_area = max(0.0, float(second[2] - second[0])) * max(0.0, float(second[3] - second[1]))
    smaller = min(first_area, second_area)
    return intersection / smaller if smaller > 0.0 else 0.0
