"""ML-backed v3 SlideIRProvider.

Packages the trained detector (nodes/containers), family classifier, and
connector segmenter into a single object that produces a complete v3 ``SlideIR``
from an image. Implements the v3
:class:`~image_to_editable_ppt.v3.core.contracts.SlideIRProvider` protocol and is
injected via ``V3Config.slide_ir_provider`` so ``convert_image`` recovers
structure with the ML models instead of the heuristic family/connector stages.

Lives in the ml package (which may depend on v3) — v3 never imports ml. Heavy
deps (torch, the checkpoints) are loaded lazily on the first ``build`` call.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from image_to_editable_ppt.ml.adapter import AnnotationMLAdapter, DetectorModelOutput
from image_to_editable_ppt.ml.annotation_schema import (
    AnnotationBBox,
    AnnotationContainer,
    AnnotationFamilyProposal,
    AnnotationImageSize,
    AnnotationNode,
)
from image_to_editable_ppt.v3.core.enums import DiagramFamily, NodeKind

if TYPE_CHECKING:
    from PIL import Image

    from image_to_editable_ppt.v3.app.config import V3Config
    from image_to_editable_ppt.v3.ir.models import SlideIR

_DETECTOR_CACHE: dict[str, object] = {}


def _load_detector(checkpoint: str) -> object:
    from image_to_editable_ppt.ml.dataset import get_or_load
    from image_to_editable_ppt.ml.lightning_module import DetectorLightningModule

    def _load() -> object:
        module = DetectorLightningModule.load_from_checkpoint(checkpoint, map_location="cpu")
        module.eval()
        return module

    return get_or_load(_DETECTOR_CACHE, checkpoint, _load)


@dataclass(slots=True, frozen=True)
class MLSlideIRProvider:
    detector_checkpoint: str
    score_threshold: float = 0.5
    family_classifier_checkpoint: str | None = None
    connector_checkpoint: str | None = None
    image_id: str = "slide"

    def build(self, image: "Image.Image", *, config: "V3Config") -> "SlideIR":
        del config

        import numpy as np
        import torch

        from image_to_editable_ppt.ml.dataset import label_to_kind, to_rgb_chw_tensor

        rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
        height, width = rgb.shape[:2]

        module = _load_detector(self.detector_checkpoint)
        with torch.no_grad():
            prediction = module([to_rgb_chw_tensor(rgb)])[0]

        nodes: list[AnnotationNode] = []
        containers: list[AnnotationContainer] = []
        for index in range(len(prediction["scores"])):
            score = float(prediction["scores"][index])
            if score < self.score_threshold:
                continue
            x0, y0, x1, y1 = (float(value) for value in prediction["boxes"][index])
            if x1 <= x0 or y1 <= y0:
                continue
            kind = label_to_kind(int(prediction["labels"][index]))
            bbox = AnnotationBBox(x0=x0, y0=y0, x1=x1, y1=y1)
            if isinstance(kind, NodeKind):
                nodes.append(
                    AnnotationNode(
                        id=f"node:{self.image_id}:{index}", kind=kind, bbox=bbox, confidence=min(score, 1.0),
                        source="ml_detector", provenance=("ml_detector:checkpoint",),
                    )
                )
            else:
                containers.append(
                    AnnotationContainer(
                        id=f"container:{self.image_id}:{index}", kind=kind, bbox=bbox, confidence=min(score, 1.0),
                        source="ml_detector", provenance=("ml_detector:checkpoint",),
                    )
                )

        family, family_confidence = DiagramFamily.ORTHOGONAL_FLOW, self.score_threshold
        if self.family_classifier_checkpoint is not None:
            from image_to_editable_ppt.ml.family_classifier import classify_family

            family, family_confidence = classify_family(self.family_classifier_checkpoint, rgb)

        boxes = [node.bbox for node in nodes] + [container.bbox for container in containers]
        if boxes:
            focus = AnnotationBBox(
                x0=max(0.0, min(box.x0 for box in boxes)),
                y0=max(0.0, min(box.y0 for box in boxes)),
                x1=min(float(width), max(box.x1 for box in boxes)),
                y1=min(float(height), max(box.y1 for box in boxes)),
            )
        else:
            focus = AnnotationBBox(0.0, 0.0, float(width), float(height))
        family_proposal = AnnotationFamilyProposal(
            id=f"family:{family.value}:0", family=family, confidence=min(family_confidence, 1.0),
            focus_bbox=focus, evidence=("ml_detector:detection_union",),
            provenance=("ml_detector:slide_ir_provider",),
        )

        connectors: tuple = ()
        ports: tuple = ()
        if self.connector_checkpoint is not None:
            from image_to_editable_ppt.ml.connector_segmenter import extract_connectors, segment_connector_masks

            line_mask, arrow_mask = segment_connector_masks(self.connector_checkpoint, rgb)
            connectors, ports = extract_connectors(line_mask, arrow_mask, tuple(nodes), image_id=self.image_id)

        output = DetectorModelOutput(
            image_id=self.image_id,
            image_size=AnnotationImageSize(width=int(width), height=int(height)),
            family_predictions=(family_proposal,),
            node_predictions=tuple(nodes),
            container_predictions=tuple(containers),
            port_predictions=ports,
            connector_predictions=connectors,
            metadata={"stage": "ml_slide_ir_provider", "detector_checkpoint": self.detector_checkpoint},
        )
        adapter = AnnotationMLAdapter()
        return adapter.to_slide_ir(adapter.from_model_output(output))
