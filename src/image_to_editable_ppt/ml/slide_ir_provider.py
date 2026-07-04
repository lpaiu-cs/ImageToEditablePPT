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
    # Connector recovery strategy (real-figure measurement 2026-07-04):
    #   "morphological" (default) — classical ink-component tracing + classical
    #     arrowhead direction; recovers real routes with no domain gap, and is the
    #     live default because it out-recovers the learned paths on real figures.
    #   "segmenter" — the learned U-Net masks + component extraction
    #     (requires connector_checkpoint).
    #   "relation" — the pairwise relation model over segmenter/classical masks
    #     (requires relation_checkpoint); kept for experiments, weak on real transfer.
    connector_strategy: str = "morphological"
    relation_checkpoint: str | None = None
    relation_threshold: float = 0.5
    # Structural tree gate: parse/derivation trees are defined by text-only nodes,
    # and the detected text-node (LABEL_ANCHOR) fraction separates them cleanly on
    # real figures (~0.45 for trees vs ~0.05 for everything else) where the pixel
    # CNN collapses trees into flow/cycle. When the fraction clears this threshold
    # (with enough nodes), promote the family to TREE. Set None to disable.
    tree_text_fraction_gate: float | None = 0.25
    # OOD gate: when set, a binary diagram/not-a-diagram classifier runs first and,
    # if the figure does not look like a convertible diagram (chart, screenshot,
    # photo, …), the provider abstains — returning an empty scene flagged
    # ``ood_rejected`` rather than fabricating a diagram. Papers are majority
    # non-diagram figures, so this is what makes real-paper precision possible.
    # Default 0.6 suits the pretrained-backbone gate (run-gate4): recall ~0.95 /
    # reject ~0.90 on held-out figures; 0.6-0.75 all keep both sides ~0.94.
    diagram_gate_checkpoint: str | None = None
    diagram_gate_threshold: float = 0.6
    image_id: str = "slide"

    def build(self, image: "Image.Image", *, config: "V3Config") -> "SlideIR":
        del config

        import numpy as np
        import torch

        from image_to_editable_ppt.ml.dataset import label_to_kind, to_rgb_chw_tensor

        rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
        height, width = rgb.shape[:2]

        if self.diagram_gate_checkpoint is not None:
            from image_to_editable_ppt.ml.diagram_gate import is_diagram

            keep, p_diagram = is_diagram(self.diagram_gate_checkpoint, rgb, threshold=self.diagram_gate_threshold)
            if not keep:
                adapter = AnnotationMLAdapter()
                rejected = DetectorModelOutput(
                    image_id=self.image_id,
                    image_size=AnnotationImageSize(width=int(width), height=int(height)),
                    family_predictions=(),
                    node_predictions=(),
                    container_predictions=(),
                    metadata={"stage": "ml_slide_ir_provider", "ood_rejected": True, "diagram_probability": p_diagram},
                )
                return adapter.to_slide_ir(adapter.from_model_output(rejected))

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

        # Connectors first: the structure-based family classifier needs the
        # recovered topology, so connector recovery must run before family selection.
        connectors, ports = self._recover_connectors(rgb, nodes, containers)

        family, family_confidence = DiagramFamily.ORTHOGONAL_FLOW, self.score_threshold
        if self.family_classifier_checkpoint is not None:
            from image_to_editable_ppt.ml.family_classifier import classify_family

            family, family_confidence = classify_family(self.family_classifier_checkpoint, rgb)

        # Structural tree gate: the pixel CNN collapses text-label trees into
        # flow/cycle, but a high detected text-node fraction is a clean, robustly
        # transferring tree signal. Override toward TREE only when it clears the
        # threshold (and there are enough nodes) — false positives on flow/table
        # are negligible since their text fraction is ~0.05.
        if self.tree_text_fraction_gate is not None and len(nodes) >= 4:
            text_fraction = sum(1 for node in nodes if node.kind is NodeKind.LABEL_ANCHOR) / len(nodes)
            if text_fraction >= self.tree_text_fraction_gate:
                family, family_confidence = DiagramFamily.TREE, max(family_confidence, text_fraction)

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

    def _recover_connectors(self, rgb, nodes, containers):
        """Recover connectors with exactly the requested strategy.

        Honors ``connector_strategy`` literally: a missing checkpoint yields no
        connectors and a warning, never a silent fallback to a different strategy
        (which would corrupt strategy-comparison experiments).
        """
        import warnings

        if self.connector_strategy == "morphological":
            from image_to_editable_ppt.ml.morphological_connectors import morphological_connectors

            return morphological_connectors(rgb, tuple(nodes), tuple(containers), image_id=self.image_id)
        if self.connector_strategy == "relation":
            if self.relation_checkpoint is None:
                warnings.warn("connector_strategy='relation' but no relation_checkpoint; emitting no connectors")
                return (), ()
            return self._relation_connectors(rgb, nodes)
        if self.connector_strategy == "segmenter":
            if self.connector_checkpoint is None:
                warnings.warn("connector_strategy='segmenter' but no connector_checkpoint; emitting no connectors")
                return (), ()
            from image_to_editable_ppt.ml.connector_segmenter import extract_connectors, segment_connector_masks

            line_mask, arrow_mask = segment_connector_masks(self.connector_checkpoint, rgb)
            return extract_connectors(line_mask, arrow_mask, tuple(nodes), image_id=self.image_id)
        warnings.warn(f"unknown connector_strategy={self.connector_strategy!r}; emitting no connectors")
        return (), ()

    def _relation_connectors(self, rgb, nodes):
        """Opt-in: directed edges from the relation model over classical masks.

        Kept for experiments; weak on real-figure transfer (edges come from a
        geometry prior because real thin arrows barely segment), so it is not the
        default. Endpoints are placed at the node-edge midpoint facing the partner.
        """
        from image_to_editable_ppt.ml.annotation_schema import (
            AnnotationBBox,
            AnnotationConnectorCandidate,
            AnnotationConnectorEndpoint,
            AnnotationPoint,
        )
        from image_to_editable_ppt.ml.classical_connectors import classical_connector_masks
        from image_to_editable_ppt.ml.connector_segmenter import _port, _side_toward
        from image_to_editable_ppt.ml.relation_model import predict_relations
        from image_to_editable_ppt.v3.core.enums import ConnectorKind, PortOwnerKind

        node_list = list(nodes)
        if len(node_list) < 2:
            return (), ()
        line_mask, arrow_mask = classical_connector_masks(rgb, [n.bbox for n in node_list])
        height, width = rgb.shape[:2]
        edges = predict_relations(
            self.relation_checkpoint, line_mask, arrow_mask, [n.bbox for n in node_list],
            width=width, height=height, threshold=self.relation_threshold,
        )
        connectors, ports = [], []
        for index, edge in enumerate(edges):
            start_node, end_node = node_list[edge.source], node_list[edge.target]
            start_side = _side_toward(start_node, _center(end_node.bbox))
            end_side = _side_toward(end_node, _center(start_node.bbox))
            start_pt = AnnotationPoint(*_side_point(start_node.bbox, start_side))
            end_pt = AnnotationPoint(*_side_point(end_node.bbox, end_side))
            connector_id = f"connector:{self.image_id}:{index}"
            connectors.append(
                AnnotationConnectorCandidate(
                    id=connector_id, kind=ConnectorKind.ARROW,
                    bbox=AnnotationBBox(
                        x0=min(start_pt.x, end_pt.x) - 3, y0=min(start_pt.y, end_pt.y) - 3,
                        x1=max(start_pt.x, end_pt.x) + 3, y1=max(start_pt.y, end_pt.y) + 3,
                    ),
                    confidence=float(edge.probability), source_evidence_id=f"evidence:{connector_id}",
                    path_points=(start_pt, end_pt),
                    start_endpoint=AnnotationConnectorEndpoint(
                        point=start_pt, owner_id=start_node.id, owner_kind=PortOwnerKind.NODE, side=start_side,
                    ),
                    end_endpoint=AnnotationConnectorEndpoint(
                        point=end_pt, owner_id=end_node.id, owner_kind=PortOwnerKind.NODE, side=end_side,
                    ),
                    arrowhead_end=True, source="relation", provenance=("relation:predict",),
                )
            )
            ports.append(_port(start_node.id, self.image_id, index, "start", start_side, start_pt))
            ports.append(_port(end_node.id, self.image_id, index, "end", end_side, end_pt))
        return tuple(connectors), tuple(ports)


def _center(bbox) -> tuple[float, float]:
    return ((bbox.x0 + bbox.x1) / 2.0, (bbox.y0 + bbox.y1) / 2.0)


def _side_point(bbox, side) -> tuple[float, float]:
    from image_to_editable_ppt.v3.core.enums import PortSide

    cx, cy = _center(bbox)
    if side is PortSide.TOP:
        return (cx, bbox.y0)
    if side is PortSide.BOTTOM:
        return (cx, bbox.y1)
    if side is PortSide.LEFT:
        return (bbox.x0, cy)
    return (bbox.x1, cy)
