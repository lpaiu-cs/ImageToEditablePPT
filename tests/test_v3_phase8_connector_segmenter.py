from __future__ import annotations

import pytest

pytest.importorskip("torch")
pytest.importorskip("lightning")

import json
from pathlib import Path

import numpy as np

import image_to_editable_ppt.ml.generate_dataset as generate_dataset_cli
from image_to_editable_ppt.ml import connector_segmenter
from image_to_editable_ppt.ml.annotation_schema import AnnotationBBox, AnnotationNode
from image_to_editable_ppt.ml.connector_segmenter import (
    extract_connectors,
    rasterize_connector_mask,
    rasterize_connector_masks,
    segment_connector_mask,
)
from image_to_editable_ppt.ml.dataset import load_annotation_document
from image_to_editable_ppt.v3.core.enums import NodeKind, PortSide


def _node(node_id: str, x0: float, y0: float, x1: float, y1: float) -> AnnotationNode:
    return AnnotationNode(
        id=node_id, kind=NodeKind.BOX, bbox=AnnotationBBox(x0=x0, y0=y0, x1=x1, y1=y1), confidence=0.9,
        source="ml_detector", provenance=("ml_detector:checkpoint",),
    )


def test_rasterize_connector_mask_paints_strokes(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "ds"
    assert generate_dataset_cli.main(
        ["--output-dir", str(dataset_dir), "--count", "8", "--seed", "7",
         "--image-width", "320", "--image-height", "180", "--no-pptx", "--family", "orthogonal_flow"]
    ) == 0
    manifest = json.loads((dataset_dir / "dataset_manifest.json").read_text(encoding="utf-8"))
    sample = manifest["samples"][0]
    document = load_annotation_document(dataset_dir / sample["annotation"])
    masks = rasterize_connector_masks(document, width=320, height=180)
    assert masks.shape == (2, 180, 320)
    assert masks[0].sum() > 0  # line channel painted
    assert masks[1].sum() > 0  # arrowhead channel painted
    assert masks[0].mean() < 0.1
    # line-only helper returns channel 0
    assert np.array_equal(rasterize_connector_mask(document, width=320, height=180), masks[0])


def _line_mask() -> np.ndarray:
    mask = np.zeros((180, 320), dtype=np.uint8)
    mask[54:57, 60:120] = 1  # horizontal stroke spanning the gap
    return mask


def _arrow_at(cx: int) -> np.ndarray:
    arrow = np.zeros((180, 320), dtype=np.uint8)
    arrow[49:62, cx - 6 : cx + 6] = 1
    return arrow


def test_extract_connectors_orients_by_arrowhead() -> None:
    left = _node("node:t:0", 20, 40, 60, 70)
    right = _node("node:t:1", 120, 40, 160, 70)
    # arrowhead at the RIGHT end -> directed left->right
    connectors, ports = extract_connectors(_line_mask(), _arrow_at(118), (left, right), image_id="t")
    assert len(connectors) == 1 and len(ports) == 2
    connector = connectors[0]
    assert connector.start_endpoint.owner_id == "node:t:0"
    assert connector.end_endpoint.owner_id == "node:t:1"
    assert connector.start_endpoint.side is PortSide.RIGHT
    assert connector.end_endpoint.side is PortSide.LEFT
    assert connector.bbox.y0 < 54 and connector.bbox.y1 > 56


def test_extract_connectors_arrowhead_flips_orientation() -> None:
    left = _node("node:t:0", 20, 40, 60, 70)
    right = _node("node:t:1", 120, 40, 160, 70)
    # arrowhead at the LEFT end -> directed right->left (opposite of reading order)
    connectors, _ = extract_connectors(_line_mask(), _arrow_at(62), (left, right), image_id="t")
    assert connectors[0].start_endpoint.owner_id == "node:t:1"  # right is the source
    assert connectors[0].end_endpoint.owner_id == "node:t:0"  # arrowhead end = left


def test_extract_connectors_dedupes_fragments_on_same_node_pair() -> None:
    left = _node("node:t:0", 20, 40, 60, 70)
    right = _node("node:t:1", 120, 40, 160, 70)
    mask = np.zeros((180, 320), dtype=np.uint8)
    mask[50:53, 60:120] = 1  # fragment A between the same pair
    mask[58:61, 60:120] = 1  # fragment B between the same pair
    no_arrow = np.zeros((180, 320), dtype=np.uint8)
    connectors, _ = extract_connectors(mask, no_arrow, (left, right), image_id="t")
    assert len(connectors) == 1  # collapsed to one edge per node-pair


def test_train_and_segment_smoke(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "ds"
    assert generate_dataset_cli.main(
        ["--output-dir", str(dataset_dir), "--count", "8", "--seed", "7",
         "--image-width", "160", "--image-height", "120", "--no-pptx", "--family", "orthogonal_flow"]
    ) == 0
    run_dir = tmp_path / "run"
    assert connector_segmenter.main(
        ["--dataset-dir", str(dataset_dir), "--output-dir", str(run_dir),
         "--batch-size", "4", "--max-epochs", "1", "--accelerator", "cpu"]
    ) == 0
    checkpoint = json.loads(
        (run_dir / "train_connector_segmenter_run.json").read_text(encoding="utf-8")
    )["checkpoint"]["last"]
    assert checkpoint is not None and Path(checkpoint).exists()

    connector_segmenter._MODULE_CACHE.clear()
    image = np.full((120, 160), 255, dtype=np.uint8)
    mask = segment_connector_mask(checkpoint, image)
    assert mask.shape == (120, 160)
    assert mask.dtype == np.uint8
