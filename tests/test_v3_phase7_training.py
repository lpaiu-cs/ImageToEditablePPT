from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("torch")
pytest.importorskip("lightning")

import torch

import image_to_editable_ppt.ml.generate_dataset as generate_dataset_cli
from image_to_editable_ppt.ml import eval_detector, infer_detector, train_detector
from image_to_editable_ppt.ml.adapter import AnnotationMLAdapter
from image_to_editable_ppt.ml.annotation_schema import DetectorAnnotationDocument
from image_to_editable_ppt.ml.dataset import (
    CONTAINER_KIND_LABELS,
    NODE_KIND_LABELS,
    NUM_DETECTION_CLASSES,
    DetectorTorchDataset,
    detection_collate,
    label_to_kind,
)
from image_to_editable_ppt.v3.core.enums import ContainerKind, NodeKind
from image_to_editable_ppt.v3.ir.validate import validate_slide_ir


@pytest.fixture(scope="module")
def tiny_dataset_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    output_dir = tmp_path_factory.mktemp("phase7_training") / "dataset"
    exit_code = generate_dataset_cli.main(
        [
            "--output-dir",
            str(output_dir),
            "--count",
            "4",
            "--seed",
            "13",
            "--image-width",
            "320",
            "--image-height",
            "180",
            "--train-ratio",
            "0.5",
            "--val-ratio",
            "0.25",
            "--no-pptx",
        ]
    )
    assert exit_code == 0
    return output_dir


def test_label_space_is_disjoint_and_reversible() -> None:
    labels = [*NODE_KIND_LABELS.values(), *CONTAINER_KIND_LABELS.values()]
    assert 0 not in labels
    assert len(set(labels)) == len(labels)
    assert NUM_DETECTION_CLASSES == len(labels) + 1
    for kind, label in NODE_KIND_LABELS.items():
        assert label_to_kind(label) is kind
    for kind, label in CONTAINER_KIND_LABELS.items():
        assert label_to_kind(label) is kind
    with pytest.raises(ValueError, match="unknown detection label"):
        label_to_kind(NUM_DETECTION_CLASSES)


def test_torch_dataset_yields_detection_targets(tiny_dataset_dir: Path) -> None:
    dataset = DetectorTorchDataset(tiny_dataset_dir, split="train")
    assert len(dataset) == 2

    image, target = dataset[0]
    assert image.shape == (3, 180, 320)
    assert image.dtype == torch.float32
    assert 0.0 <= float(image.min()) and float(image.max()) <= 1.0
    assert target["boxes"].shape[1] == 4
    assert target["boxes"].shape[0] == target["labels"].shape[0] >= 3
    assert bool(((target["boxes"][:, 2] > target["boxes"][:, 0]) & (target["boxes"][:, 3] > target["boxes"][:, 1])).all())
    assert bool((target["labels"] >= 1).all()) and bool((target["labels"] < NUM_DETECTION_CLASSES).all())

    images, targets = detection_collate([dataset[0], dataset[1]])
    assert len(images) == 2 and len(targets) == 2


def test_train_infer_eval_loop_produces_valid_artifacts(tiny_dataset_dir: Path, tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    exit_code = train_detector.main(
        [
            "--dataset-dir",
            str(tiny_dataset_dir),
            "--output-dir",
            str(run_dir),
            "--batch-size",
            "2",
            "--max-epochs",
            "1",
            "--accelerator",
            "cpu",
            "--limit-train-batches",
            "1",
            "--limit-val-batches",
            "1",
            "--tracking-backend",
            "csv",
        ]
    )
    assert exit_code == 0

    run_manifest = json.loads((run_dir / "train_detector_run.json").read_text(encoding="utf-8"))
    assert run_manifest["status"] == "trained"
    assert "train_loss" in run_manifest["final_metrics"]
    assert run_manifest["dataset"]["generator"]["seed"] == 13
    checkpoint = run_manifest["checkpoint"]["last"]
    assert checkpoint is not None and Path(checkpoint).exists()
    metrics_csv = list(run_dir.rglob("metrics.csv"))
    assert metrics_csv, "csv tracking backend should write metrics.csv"

    dataset_manifest = json.loads((tiny_dataset_dir / "dataset_manifest.json").read_text(encoding="utf-8"))
    sample = next(item for item in dataset_manifest["samples"] if item["split"] == "train")
    prediction_json = tmp_path / "prediction.json"
    exit_code = infer_detector.main(
        [
            "--image-id",
            sample["id"],
            "--image-path",
            str(tiny_dataset_dir / sample["image"]),
            "--checkpoint",
            checkpoint,
            "--score-threshold",
            "0.1",
            "--output-json",
            str(prediction_json),
            "--family",
            "orthogonal_flow",
            "--validate-ir",
        ]
    )
    assert exit_code == 0

    document = DetectorAnnotationDocument.from_dict(json.loads(prediction_json.read_text(encoding="utf-8")))
    assert document.metadata["inference_mode"] == "checkpoint"
    assert document.image_size.width == 320 and document.image_size.height == 180
    validate_slide_ir(AnnotationMLAdapter().to_slide_ir(document))
    scene = document.primitive_scene
    assert scene is not None
    for node in scene.nodes:
        assert isinstance(node.kind, NodeKind)
        assert 0.0 <= node.confidence <= 1.0
    for container in scene.containers:
        assert isinstance(container.kind, ContainerKind)

    report_json = tmp_path / "report.json"
    exit_code = eval_detector.main(
        [
            "--predictions-json",
            str(prediction_json),
            "--ground-truth-json",
            str(tiny_dataset_dir / sample["annotation"]),
            "--report-json",
            str(report_json),
        ]
    )
    assert exit_code == 0
    report = json.loads(report_json.read_text(encoding="utf-8"))
    assert {"family_proposals", "nodes", "containers", "connectors", "structural"} <= set(report)
