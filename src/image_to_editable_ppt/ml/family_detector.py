"""ML-backed family detector that plugs into the v3 FAMILY_DETECT stage.

This lives in the ``ml`` package (which may depend on ``v3``) rather than under
``v3`` (which may not depend on ``ml``). It implements the v3
:class:`~image_to_editable_ppt.v3.core.contracts.FamilyDetector` protocol, so a
caller constructs it and injects it via ``V3Config.family_detector_override``;
the v3 pipeline then calls ``detect`` without importing anything from ``ml``.

It runs the trained Phase 7 Faster R-CNN checkpoint on the structural canvas and
turns the node/container detections into a single :class:`FamilyProposal`. The
detector predicts node/container boxes, not families, so the proposal is tagged
with ``family`` and uses the union of the detected boxes as the focus region.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from image_to_editable_ppt.v3.core.enums import DiagramFamily
from image_to_editable_ppt.v3.core.types import BBox
from image_to_editable_ppt.v3.ir.models import (
    FamilyProposal,
    RasterLayerResult,
    ResidualStructuralCanvas,
    TextLayerResult,
)

if TYPE_CHECKING:
    import numpy as np

    from image_to_editable_ppt.v3.app.config import V3Config

# Cache loaded checkpoints by path so repeated detect() calls (and repeated
# slides in a batch) do not re-deserialize the model.
_MODEL_CACHE: dict[str, object] = {}


def _load_module(checkpoint: str) -> object:
    cached = _MODEL_CACHE.get(checkpoint)
    if cached is not None:
        return cached
    from image_to_editable_ppt.ml.lightning_module import DetectorLightningModule

    module = DetectorLightningModule.load_from_checkpoint(checkpoint, map_location="cpu")
    module.eval()
    _MODEL_CACHE[checkpoint] = module
    return module


@dataclass(slots=True, frozen=True)
class MLFamilyDetector:
    checkpoint: str
    score_threshold: float = 0.5
    family: DiagramFamily = field(default=DiagramFamily.ORTHOGONAL_FLOW)
    # Opt-in: when set, the slide's family is predicted by the learned family
    # classifier instead of using the fixed ``family`` above (detector is
    # family-blind on its own).
    family_classifier_checkpoint: str | None = None

    def detect(
        self,
        canvas: ResidualStructuralCanvas,
        *,
        text_layer: TextLayerResult,
        raster_layer: RasterLayerResult,
        config: "V3Config",
    ) -> tuple[FamilyProposal, ...]:
        del text_layer, raster_layer, config

        import torch

        module = _load_module(self.checkpoint)
        image_tensor = _to_rgb_tensor(canvas.image)
        with torch.no_grad():
            prediction = module([image_tensor])[0]

        kept_boxes: list[tuple[float, float, float, float]] = []
        kept_scores: list[float] = []
        for index in range(len(prediction["scores"])):
            score = float(prediction["scores"][index])
            if score < self.score_threshold:
                continue
            x0, y0, x1, y1 = (float(value) for value in prediction["boxes"][index])
            if x1 <= x0 or y1 <= y0:
                continue
            kept_boxes.append((x0, y0, x1, y1))
            kept_scores.append(score)

        if not kept_boxes:
            return ()

        family = self.family
        family_confidence: float | None = None
        evidence = [
            f"ml_detection_count={len(kept_boxes)}",
            f"max_score={max(kept_scores):.4f}",
            f"score_threshold={self.score_threshold:.3f}",
        ]
        provenance = ["branch:structural_canvas", "detector:ml_checkpoint"]
        if self.family_classifier_checkpoint is not None:
            from image_to_editable_ppt.ml.family_classifier import classify_family

            family, family_confidence = classify_family(self.family_classifier_checkpoint, canvas.image)
            evidence.append(f"family_classifier_prob={family_confidence:.4f}")
            provenance.append("family:ml_classifier")

        height, width = canvas.image.shape[:2]
        focus_bbox = _clip(_union(kept_boxes), width=int(width), height=int(height))
        confidence = family_confidence if family_confidence is not None else min(0.99, max(kept_scores))
        return (
            FamilyProposal(
                id=f"family:{family.value}:ml:1",
                family=family,
                confidence=confidence,
                evidence=tuple(evidence),
                provenance=tuple(provenance),
                focus_bbox=focus_bbox,
            ),
        )


def _to_rgb_tensor(image: "np.ndarray"):
    import numpy as np
    import torch

    array = np.asarray(image)
    if array.ndim == 2:
        array = np.stack([array, array, array], axis=-1)
    elif array.ndim == 3 and array.shape[2] == 1:
        array = np.repeat(array, 3, axis=2)
    array = array.astype(np.float32)
    if array.max() > 1.0:
        array = array / 255.0
    return torch.from_numpy(array).permute(2, 0, 1)


def _union(boxes: list[tuple[float, float, float, float]]) -> BBox:
    return BBox(
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    )


def _clip(bbox: BBox, *, width: int, height: int) -> BBox:
    return BBox(
        max(0.0, min(float(width), bbox.x0)),
        max(0.0, min(float(height), bbox.y0)),
        max(0.0, min(float(width), bbox.x1)),
        max(0.0, min(float(height), bbox.y1)),
    )
