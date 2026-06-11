from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from image_to_editable_ppt.ml.annotation_schema import (
    AnnotationConnectorCandidate,
    AnnotationConnectorEndpoint,
    AnnotationContainer,
    AnnotationDiagramInstance,
    AnnotationFamilyProposal,
    AnnotationImageSize,
    AnnotationNode,
    AnnotationPort,
    AnnotationPrimitiveScene,
    AnnotationPrimitiveText,
    AnnotationResidual,
    AnnotationSchemaError,
    AnnotationTextRegion,
    DetectorAnnotationDocument,
)
from image_to_editable_ppt.v3.ir.models import (
    ConnectorAttachment,
    ConnectorEvidence,
    DiagramContainer,
    DiagramInstance,
    DiagramNode,
    FamilyProposal,
    PortSpec,
    PrimitiveConnectorCandidate,
    PrimitiveContainer,
    PrimitiveNode,
    PrimitiveResidual,
    PrimitiveScene,
    PrimitiveText,
    SlideIR,
    TextRegion,
    UnattachedConnectorEvidence,
)
from image_to_editable_ppt.v3.core.enums import ConnectorOrientation, PortSide


@dataclass(slots=True, frozen=True)
class DetectorModelOutput:
    image_id: str
    image_size: AnnotationImageSize
    family_predictions: tuple[AnnotationFamilyProposal, ...] = ()
    node_predictions: tuple[AnnotationNode, ...] = ()
    container_predictions: tuple[AnnotationContainer, ...] = ()
    text_predictions: tuple[AnnotationTextRegion, ...] = ()
    port_predictions: tuple[AnnotationPort, ...] = ()
    connector_predictions: tuple[AnnotationConnectorCandidate, ...] = ()
    residual_predictions: tuple[AnnotationResidual, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict)


class MLAdapter(Protocol):
    def from_model_output(self, output: DetectorModelOutput) -> DetectorAnnotationDocument: ...

    def to_family_proposals(self, document: DetectorAnnotationDocument) -> tuple[FamilyProposal, ...]: ...

    def to_text_regions(self, document: DetectorAnnotationDocument) -> tuple[TextRegion, ...]: ...

    def to_diagram_instances(self, document: DetectorAnnotationDocument) -> tuple[DiagramInstance, ...]: ...

    def to_primitive_scene(self, document: DetectorAnnotationDocument) -> PrimitiveScene: ...

    def to_slide_ir(
        self,
        document: DetectorAnnotationDocument,
        *,
        diagram_instances: tuple[DiagramInstance, ...] | None = None,
    ) -> SlideIR: ...


@dataclass(slots=True)
class AnnotationMLAdapter:
    default_source: str = "ml_detector"
    default_provenance_prefix: str = "ml_adapter"

    def from_model_output(self, output: DetectorModelOutput) -> DetectorAnnotationDocument:
        primitive_texts = tuple(
            AnnotationPrimitiveText(
                id=item.id,
                role=item.role,
                bbox=item.bbox,
                confidence=item.confidence,
                text=item.text,
                owner_ids=(),
                source=item.source,
                provenance=(*item.provenance, "ml_adapter:primitive_text"),
            )
            for item in output.text_predictions
        )
        primitive_scene = AnnotationPrimitiveScene(
            nodes=tuple(output.node_predictions),
            containers=tuple(output.container_predictions),
            texts=primitive_texts,
            ports=tuple(output.port_predictions),
            connector_candidates=tuple(output.connector_predictions),
            residuals=tuple(output.residual_predictions),
        )
        metadata = dict(output.metadata)
        metadata.setdefault("bootstrap_stage", "phase7_ml_experiment_bootstrap")
        metadata.setdefault("adapter", self.__class__.__name__)
        return DetectorAnnotationDocument(
            image_id=output.image_id,
            image_size=output.image_size,
            family_proposals=tuple(output.family_predictions),
            text_regions=tuple(output.text_predictions),
            primitive_scene=primitive_scene,
            metadata=metadata,
        )

    def to_family_proposals(self, document: DetectorAnnotationDocument) -> tuple[FamilyProposal, ...]:
        return tuple(
            FamilyProposal(
                id=item.id,
                family=item.family,
                confidence=item.confidence,
                evidence=item.evidence,
                provenance=item.provenance,
                focus_bbox=item.focus_bbox.to_bbox(),
            )
            for item in document.family_proposals
        )

    def to_text_regions(self, document: DetectorAnnotationDocument) -> tuple[TextRegion, ...]:
        return tuple(
            TextRegion(
                id=item.id,
                bbox=item.bbox.to_bbox(),
                confidence=item.confidence,
                role=item.role,
                text=item.text,
                source=item.source,
                provenance=item.provenance,
            )
            for item in document.text_regions
        )

    def to_diagram_instances(self, document: DetectorAnnotationDocument) -> tuple[DiagramInstance, ...]:
        return tuple(self._to_diagram_instance(item) for item in document.diagram_instances)

    def to_primitive_scene(self, document: DetectorAnnotationDocument) -> PrimitiveScene:
        scene = document.primitive_scene or AnnotationPrimitiveScene()
        port_lookup = {(port.owner_id, port.side): port.id for port in scene.ports}
        return PrimitiveScene(
            image_size=document.image_size.to_image_size(),
            nodes=tuple(self._to_primitive_node(item) for item in scene.nodes),
            containers=tuple(self._to_primitive_container(item) for item in scene.containers),
            texts=tuple(self._to_primitive_text(item) for item in scene.texts),
            ports=tuple(self._to_port(item) for item in scene.ports),
            connector_candidates=tuple(
                self._to_connector_candidate(item, port_lookup=port_lookup) for item in scene.connector_candidates
            ),
            unattached_connector_evidence=tuple(
                UnattachedConnectorEvidence(
                    id=item.id,
                    evidence_id=item.evidence_id,
                    reason=item.reason,
                    confidence=item.confidence,
                    candidate_port_ids=item.candidate_port_ids,
                    source=item.source,
                    provenance=item.provenance,
                )
                for item in scene.unattached_connector_evidence
            ),
            residuals=tuple(self._to_primitive_residual(item) for item in scene.residuals),
            provenance=(
                f"{self.default_provenance_prefix}:primitive_scene",
                f"source:{self.default_source}",
                f"document:{document.image_id}",
            ),
        )

    def to_slide_ir(
        self,
        document: DetectorAnnotationDocument,
        *,
        diagram_instances: tuple[DiagramInstance, ...] | None = None,
    ) -> SlideIR:
        primitive_scene = self.to_primitive_scene(document)
        resolved_diagram_instances = self.to_diagram_instances(document) if diagram_instances is None else diagram_instances
        text_regions = self.to_text_regions(document)
        connector_evidence = tuple(
            self._to_connector_evidence(item)
            for item in (document.primitive_scene or AnnotationPrimitiveScene()).connector_candidates
        )
        return SlideIR(
            image_size=document.image_size.to_image_size(),
            family_proposals=self.to_family_proposals(document),
            diagram_instances=resolved_diagram_instances,
            connector_evidence=connector_evidence,
            connector_candidates=primitive_scene.connector_candidates,
            unattached_connector_evidence=primitive_scene.unattached_connector_evidence,
            primitive_scene=primitive_scene,
            text_regions=text_regions,
            residual_regions=(),
            connectors=(),
            style_tokens=(),
            raster_regions=(),
        )

    def _to_diagram_instance(self, item: AnnotationDiagramInstance) -> DiagramInstance:
        return DiagramInstance(
            id=item.id,
            family=item.family,
            confidence=item.confidence,
            bbox=item.bbox.to_bbox(),
            containers=tuple(self._to_diagram_container(container) for container in item.containers),
            nodes=tuple(self._to_diagram_node(node) for node in item.nodes),
            text_region_ids=item.text_region_ids,
            source_proposal_ids=item.source_proposal_ids,
            provenance=item.provenance,
        )

    def _to_diagram_node(self, item: AnnotationNode) -> DiagramNode:
        return DiagramNode(
            id=item.id,
            kind=item.kind,
            bbox=item.bbox.to_bbox(),
            confidence=item.confidence,
            label=item.label,
            text_region_ids=item.text_region_ids,
            source=item.source,
            provenance=item.provenance,
        )

    def _to_diagram_container(self, item: AnnotationContainer) -> DiagramContainer:
        return DiagramContainer(
            id=item.id,
            kind=item.kind,
            bbox=item.bbox.to_bbox(),
            confidence=item.confidence,
            member_node_ids=item.member_node_ids,
            label=item.label,
            source=item.source,
            provenance=item.provenance,
        )

    def _to_primitive_node(self, item: AnnotationNode) -> PrimitiveNode:
        return PrimitiveNode(
            id=item.id,
            kind=item.kind,
            bbox=item.bbox.to_bbox(),
            confidence=item.confidence,
            label=item.label,
            text_region_ids=item.text_region_ids,
            source=item.source,
            provenance=item.provenance,
        )

    def _to_primitive_container(self, item: AnnotationContainer) -> PrimitiveContainer:
        return PrimitiveContainer(
            id=item.id,
            kind=item.kind,
            bbox=item.bbox.to_bbox(),
            confidence=item.confidence,
            member_node_ids=item.member_node_ids,
            label=item.label,
            source=item.source,
            provenance=item.provenance,
        )

    def _to_primitive_text(self, item: AnnotationPrimitiveText) -> PrimitiveText:
        return PrimitiveText(
            id=item.id,
            role=item.role,
            bbox=item.bbox.to_bbox(),
            confidence=item.confidence,
            text=item.text,
            owner_ids=item.owner_ids,
            source=item.source,
            provenance=item.provenance,
        )

    def _to_port(self, item: AnnotationPort) -> PortSpec:
        return PortSpec(
            id=item.id,
            owner_id=item.owner_id,
            owner_kind=item.owner_kind,
            side=item.side,
            point=item.point.to_point(),
            confidence=item.confidence,
            source=item.source,
            provenance=item.provenance,
        )

    def _to_connector_candidate(
        self,
        item: AnnotationConnectorCandidate,
        *,
        port_lookup: dict[tuple[str, PortSide], str],
    ) -> PrimitiveConnectorCandidate:
        return PrimitiveConnectorCandidate(
            id=item.id,
            kind=item.kind,
            bbox=item.bbox.to_bbox(),
            confidence=item.confidence,
            source_evidence_id=item.source_evidence_id,
            path_points=tuple(point.to_point() for point in item.effective_path_points()),
            start_attachment=self._to_attachment(item.start_endpoint, port_lookup=port_lookup),
            end_attachment=self._to_attachment(item.end_endpoint, port_lookup=port_lookup),
            arrowhead_start=item.arrowhead_start,
            arrowhead_end=item.arrowhead_end,
            source=item.source,
            provenance=item.provenance,
        )

    def _to_attachment(
        self,
        endpoint: AnnotationConnectorEndpoint | None,
        *,
        port_lookup: dict[tuple[str, PortSide], str],
    ) -> ConnectorAttachment | None:
        if endpoint is None:
            return None
        if endpoint.owner_id is None or endpoint.owner_kind is None or endpoint.side is None:
            raise AnnotationSchemaError("connector endpoints must include owner_id, owner_kind, and side")
        port_id = port_lookup.get((endpoint.owner_id, endpoint.side))
        if port_id is None:
            raise AnnotationSchemaError(
                f"missing AnnotationPort for connector endpoint owner={endpoint.owner_id} side={endpoint.side.value}"
            )
        return ConnectorAttachment(
            port_id=port_id,
            owner_id=endpoint.owner_id,
            owner_kind=endpoint.owner_kind,
            side=endpoint.side,
            point=endpoint.point.to_point(),
            distance=endpoint.distance,
            confidence=endpoint.confidence,
            source=self.default_source,
            provenance=(f"{self.default_provenance_prefix}:connector_attachment",),
        )

    def _to_primitive_residual(self, item: AnnotationResidual) -> PrimitiveResidual:
        return PrimitiveResidual(
            id=item.id,
            kind=item.kind,
            bbox=item.bbox.to_bbox(),
            confidence=item.confidence,
            reason=item.reason,
            source=item.source,
            provenance=item.provenance,
        )

    def _to_connector_evidence(self, item: AnnotationConnectorCandidate) -> ConnectorEvidence:
        path_points = tuple(point.to_point() for point in item.effective_path_points())
        return ConnectorEvidence(
            id=item.source_evidence_id,
            kind=item.kind,
            orientation=_infer_orientation(path_points),
            bbox=item.bbox.to_bbox(),
            confidence=item.confidence,
            path_points=path_points,
            arrowhead_start=item.arrowhead_start,
            arrowhead_end=item.arrowhead_end,
            start_nearby_node_ids=(),
            end_nearby_node_ids=(),
            nearby_container_ids=(),
            source=self.default_source,
            provenance=(f"{self.default_provenance_prefix}:connector_evidence", f"source:{item.id}"),
        )


def _infer_orientation(path_points) -> ConnectorOrientation:
    if len(path_points) < 2:
        return ConnectorOrientation.UNKNOWN
    horizontal = all(abs(first.y - second.y) < 1e-6 for first, second in zip(path_points, path_points[1:]))
    vertical = all(abs(first.x - second.x) < 1e-6 for first, second in zip(path_points, path_points[1:]))
    if horizontal and not vertical:
        return ConnectorOrientation.HORIZONTAL
    if vertical and not horizontal:
        return ConnectorOrientation.VERTICAL
    if len(path_points) > 2:
        return ConnectorOrientation.MIXED
    return ConnectorOrientation.DIAGONAL
