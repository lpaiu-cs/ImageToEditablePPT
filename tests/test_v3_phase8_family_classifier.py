from __future__ import annotations

import pytest

pytest.importorskip("torch")
pytest.importorskip("lightning")

import json
from pathlib import Path

import numpy as np
from PIL import Image

import image_to_editable_ppt.ml.generate_dataset as generate_dataset_cli
from image_to_editable_ppt.ml import family_classifier
from image_to_editable_ppt.ml.family_classifier import (
    FAMILY_CLASS_ORDER,
    FAMILY_TO_INDEX,
    classify_family,
)
from image_to_editable_ppt.ml.synthesize import SUPPORTED_FAMILIES
from image_to_editable_ppt.v3.core.enums import DiagramFamily


def test_family_class_order_matches_supported_families() -> None:
    assert set(FAMILY_CLASS_ORDER) == set(SUPPORTED_FAMILIES)
    assert FAMILY_TO_INDEX[FAMILY_CLASS_ORDER[0]] == 0
    assert len(FAMILY_TO_INDEX) == len(FAMILY_CLASS_ORDER)


def test_preprocess_produces_three_channel_square_tensor() -> None:
    gray = np.full((180, 320), 255, dtype=np.uint8)
    tensor = family_classifier._preprocess(gray)
    assert tuple(tensor.shape) == (3, family_classifier.INPUT_SIZE, family_classifier.INPUT_SIZE)
    assert 0.0 <= float(tensor.min()) and float(tensor.max()) <= 1.0


def test_train_and_classify_smoke(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "ds"
    exit_code = generate_dataset_cli.main(
        [
            "--output-dir", str(dataset_dir),
            "--count", "16",
            "--seed", "7",
            "--image-width", "160",
            "--image-height", "120",
            "--no-pptx",
        ]
    )
    assert exit_code == 0

    run_dir = tmp_path / "run"
    exit_code = family_classifier.main(
        [
            "--dataset-dir", str(dataset_dir),
            "--output-dir", str(run_dir),
            "--batch-size", "4",
            "--max-epochs", "1",
            "--accelerator", "cpu",
        ]
    )
    assert exit_code == 0

    manifest = json.loads((run_dir / "train_family_classifier_run.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "trained"
    checkpoint = manifest["checkpoint"]["last"]
    assert checkpoint is not None and Path(checkpoint).exists()

    family_classifier._MODULE_CACHE.clear()
    with Image.open(next((dataset_dir / "test").glob("*.png"))) as opened:
        image = np.asarray(opened.convert("L"), dtype=np.uint8)
    family, prob = classify_family(checkpoint, image)
    assert isinstance(family, DiagramFamily)
    assert family in FAMILY_CLASS_ORDER
    assert 0.0 <= prob <= 1.0
