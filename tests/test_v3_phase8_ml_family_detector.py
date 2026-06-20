from __future__ import annotations

import pytest

pytest.importorskip("torch")
pytest.importorskip("lightning")

import numpy as np
import torch

from image_to_editable_ppt.ml import family_detector as family_detector_module
from image_to_editable_ppt.ml.family_detector import MLFamilyDetector
from image_to_editable_ppt.v3.app.config import V3Config
from image_to_editable_ppt.v3.core.enums import DiagramFamily
from image_to_editable_ppt.v3.core.types import BBox
from image_to_editable_ppt.v3.families.registry import detect_family_proposals
from image_to_editable_ppt.v3.ir.models import ResidualStructuralCanvas


class _StubDetectorModel:
    """Stands in for a loaded DetectorLightningModule; ignores the input image."""

    def __init__(self, boxes: list[list[float]], scores: list[float], labels: list[int]) -> None:
        self._boxes = boxes
        self._scores = scores
        self._labels = labels

    def __call__(self, images: list[torch.Tensor]) -> list[dict[str, torch.Tensor]]:
        return [
            {
                "boxes": torch.tensor(self._boxes, dtype=torch.float32),
                "scores": torch.tensor(self._scores, dtype=torch.float32),
                "labels": torch.tensor(self._labels, dtype=torch.int64),
            }
        ]


def _canvas(width: int = 320, height: int = 180) -> ResidualStructuralCanvas:
    image = np.full((height, width), 255, dtype=np.uint8)
    return ResidualStructuralCanvas(id="canvas:test", bbox=BBox(0.0, 0.0, float(width), float(height)), image=image)


def _patch_model(monkeypatch, model: _StubDetectorModel) -> None:
    family_detector_module._MODEL_CACHE.clear()
    monkeypatch.setattr(family_detector_module, "_load_module", lambda checkpoint: model)


def test_ml_detector_unions_thresholded_detections(monkeypatch) -> None:
    _patch_model(
        monkeypatch,
        _StubDetectorModel(
            boxes=[[20, 30, 60, 70], [200, 40, 260, 90], [10, 10, 12, 12]],
            scores=[0.95, 0.80, 0.20],  # third is below threshold
            labels=[1, 5, 1],
        ),
    )
    detector = MLFamilyDetector(checkpoint="dummy.ckpt", score_threshold=0.5)
    proposals = detector.detect(_canvas(), text_layer=None, raster_layer=None, config=V3Config())

    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal.family is DiagramFamily.ORTHOGONAL_FLOW
    assert proposal.focus_bbox == BBox(20.0, 30.0, 260.0, 90.0)  # union of the two kept boxes
    assert "detector:ml_checkpoint" in proposal.provenance
    assert any("ml_detection_count=2" in item for item in proposal.evidence)
    assert 0.0 <= proposal.confidence <= 1.0


def test_ml_detector_returns_empty_when_all_below_threshold(monkeypatch) -> None:
    _patch_model(monkeypatch, _StubDetectorModel(boxes=[[20, 30, 60, 70]], scores=[0.10], labels=[1]))
    detector = MLFamilyDetector(checkpoint="dummy.ckpt", score_threshold=0.5)
    assert detector.detect(_canvas(), text_layer=None, raster_layer=None, config=V3Config()) == ()


def test_focus_bbox_is_clipped_to_canvas(monkeypatch) -> None:
    _patch_model(monkeypatch, _StubDetectorModel(boxes=[[-5, -5, 400, 250]], scores=[0.99], labels=[1]))
    detector = MLFamilyDetector(checkpoint="dummy.ckpt", score_threshold=0.5)
    proposal = detector.detect(_canvas(320, 180), text_layer=None, raster_layer=None, config=V3Config())[0]
    assert proposal.focus_bbox == BBox(0.0, 0.0, 320.0, 180.0)


def test_registry_routes_to_override_when_set(monkeypatch) -> None:
    _patch_model(monkeypatch, _StubDetectorModel(boxes=[[20, 30, 60, 70]], scores=[0.9], labels=[1]))
    detector = MLFamilyDetector(checkpoint="dummy.ckpt", score_threshold=0.5)
    config = V3Config(family_detector_override=detector)
    proposals = detect_family_proposals(_canvas(), text_layer=None, raster_layer=None, config=config)
    assert len(proposals) == 1
    assert "detector:ml_checkpoint" in proposals[0].provenance


def test_ml_detector_uses_family_classifier_when_set(monkeypatch) -> None:
    _patch_model(monkeypatch, _StubDetectorModel(boxes=[[20, 30, 60, 70]], scores=[0.9], labels=[1]))
    # Stub the classifier so no real checkpoint is needed; it forces CYCLE.
    from image_to_editable_ppt.ml import family_classifier

    monkeypatch.setattr(family_classifier, "classify_family", lambda checkpoint, image: (DiagramFamily.CYCLE, 0.88))
    detector = MLFamilyDetector(
        checkpoint="dummy.ckpt", score_threshold=0.5, family_classifier_checkpoint="fc.ckpt"
    )
    proposal = detector.detect(_canvas(), text_layer=None, raster_layer=None, config=V3Config())[0]
    assert proposal.family is DiagramFamily.CYCLE  # learned, not the default ORTHOGONAL_FLOW
    assert proposal.confidence == 0.88
    assert "family:ml_classifier" in proposal.provenance
    assert any("family_classifier_prob=0.8800" in item for item in proposal.evidence)


def test_registry_uses_heuristic_when_no_override(monkeypatch) -> None:
    # No override and no enabled families with a real canvas → heuristic path runs and yields nothing here.
    config = V3Config(enabled_families=frozenset())
    proposals = detect_family_proposals(_canvas(), text_layer=None, raster_layer=None, config=config)
    assert proposals == ()
