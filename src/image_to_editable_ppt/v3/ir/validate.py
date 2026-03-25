from __future__ import annotations

import numpy as np

from image_to_editable_ppt.v3.core.contracts import ContractViolationError
from image_to_editable_ppt.v3.core.enums import BranchKind
from image_to_editable_ppt.v3.core.types import BBox
from image_to_editable_ppt.v3.ir.models import (
    ConnectorAttachment,
    ConnectorEvidence,
    MultiViewBundle,
    PortSpec,
    PrimitiveConnectorCandidate,
    PrimitiveScene,
    RasterLayerResult,
    ResidualCanvasResult,
    SlideIR,
    TextLayerResult,
    UnattachedConnectorEvidence,
)


REQUIRED_BRANCHES = {
    BranchKind.RGB,
    BranchKind.STYLE,
    BranchKind.TEXT,
    BranchKind.STRUCTURE,
    BranchKind.STRUCTURAL_CANVAS,
}


def validate_multiview_bundle(bundle: MultiViewBundle) -> None:
    if set(bundle.branches) != REQUIRED_BRANCHES:
        missing = sorted(branch.value for branch in REQUIRED_BRANCHES - set(bundle.branches))
        extra = sorted(branch.value for branch in set(bundle.branches) - REQUIRED_BRANCHES)
        raise ContractViolationError(f"multiview branches mismatch: missing={missing}, extra={extra}")
    for kind, branch in bundle.branches.items():
        if kind != branch.kind:
            raise ContractViolationError(f"branch key mismatch for {kind.value}")
        if branch.width != bundle.image_size.width or branch.height != bundle.image_size.height:
            raise ContractViolationError(f"branch size mismatch for {kind.value}")
        if branch.soft_mask is not None and branch.soft_mask.shape != (bundle.image_size.height, bundle.image_size.width):
            raise ContractViolationError(f"soft mask shape mismatch for {kind.value}")


def validate_text_layer_result(result: TextLayerResult) -> None:
    _validate_view_shape(result.soft_mask, image_size=result.image_size, label="text_layer.soft_mask", allow_channels=False)
    _validate_view_shape(
        result.masked_structure_view,
        image_size=result.image_size,
        label="text_layer.masked_structure_view",
        allow_channels=False,
    )
    if not result.provenance:
        raise ContractViolationError("text layer provenance must not be empty")
    for region in result.regions:
        _validate_confidence(region.confidence, label=region.id)
        _validate_bbox(region.bbox, label=region.id)
        if not region.source:
            raise ContractViolationError(f"text region {region.id} must declare a source")


def validate_raster_layer_result(result: RasterLayerResult) -> None:
    _validate_view_shape(
        result.subtraction_mask,
        image_size=result.image_size,
        label="raster_layer.subtraction_mask",
        allow_channels=False,
    )
    _validate_view_shape(
        result.subtracted_structure_view,
        image_size=result.image_size,
        label="raster_layer.subtracted_structure_view",
        allow_channels=False,
    )
    if not result.provenance:
        raise ContractViolationError("raster layer provenance must not be empty")
    for region in result.regions:
        _validate_confidence(region.confidence, label=region.id)
        _validate_bbox(region.bbox, label=region.id)
        if not region.source:
            raise ContractViolationError(f"raster region {region.id} must declare a source")


def validate_residual_canvas_result(result: ResidualCanvasResult) -> None:
    _validate_view_shape(result.text_mask, image_size=result.image_size, label="residual.text_mask", allow_channels=False)
    _validate_view_shape(result.raster_mask, image_size=result.image_size, label="residual.raster_mask", allow_channels=False)
    _validate_view_shape(result.combined_mask, image_size=result.image_size, label="residual.combined_mask", allow_channels=False)
    _validate_view_shape(
        result.text_suppressed_view,
        image_size=result.image_size,
        label="residual.text_suppressed_view",
        allow_channels=False,
    )
    _validate_view_shape(
        result.raster_suppressed_view,
        image_size=result.image_size,
        label="residual.raster_suppressed_view",
        allow_channels=False,
    )
    if result.canvas is None:
        raise ContractViolationError("residual canvas result must include a canvas payload")
    _validate_bbox(result.canvas.bbox, label=result.canvas.id)
    _validate_view_shape(result.canvas.image, image_size=result.image_size, label=result.canvas.id, allow_channels=False)
    if result.canvas.bbox != BBox.from_image_size(result.image_size):
        raise ContractViolationError("residual canvas must span the full image extent")
    if not result.provenance:
        raise ContractViolationError("residual canvas provenance must not be empty")


def validate_slide_ir(slide_ir: SlideIR) -> None:
    instance_ids = {instance.id for instance in slide_ir.diagram_instances}
    node_ids = {node.id for instance in slide_ir.diagram_instances for node in instance.nodes}
    container_ids = {container.id for instance in slide_ir.diagram_instances for container in instance.containers}
    proposal_ids = {proposal.id for proposal in slide_ir.family_proposals}
    evidence_ids = {evidence.id for evidence in slide_ir.connector_evidence}

    if slide_ir.text_layer is not None:
        validate_text_layer_result(slide_ir.text_layer)
        if tuple(region.id for region in slide_ir.text_regions) != tuple(region.id for region in slide_ir.text_layer.regions):
            raise ContractViolationError("slide_ir.text_regions must mirror text_layer.regions")
    if slide_ir.raster_layer is not None:
        validate_raster_layer_result(slide_ir.raster_layer)
        if tuple(region.id for region in slide_ir.raster_regions) != tuple(region.id for region in slide_ir.raster_layer.regions):
            raise ContractViolationError("slide_ir.raster_regions must mirror raster_layer.regions")
    if slide_ir.residual_canvas is not None:
        validate_residual_canvas_result(slide_ir.residual_canvas)
        if slide_ir.residual_canvas.image_size != slide_ir.image_size:
            raise ContractViolationError("residual canvas image size must match slide_ir.image_size")

    for region in (*slide_ir.text_regions, *slide_ir.raster_regions, *slide_ir.residual_regions):
        _validate_confidence(region.confidence, label=region.id)
        _validate_bbox(region.bbox, label=region.id)

    for proposal in slide_ir.family_proposals:
        _validate_confidence(proposal.confidence, label=proposal.id)
        if proposal.focus_bbox is None:
            raise ContractViolationError(f"family proposal {proposal.id} must include a focus_bbox")
        _validate_bbox(proposal.focus_bbox, label=proposal.id)
        if not proposal.provenance:
            raise ContractViolationError(f"family proposal {proposal.id} must declare provenance")

    for instance in slide_ir.diagram_instances:
        _validate_confidence(instance.confidence, label=instance.id)
        _validate_bbox(instance.bbox, label=instance.id)
        for container in instance.containers:
            _validate_confidence(container.confidence, label=container.id)
            _validate_bbox(container.bbox, label=container.id)
            if not container.source:
                raise ContractViolationError(f"container {container.id} must declare a source")
            if not container.provenance:
                raise ContractViolationError(f"container {container.id} must declare provenance")
            unknown_member_ids = [node_id for node_id in container.member_node_ids if node_id not in node_ids]
            if unknown_member_ids:
                raise ContractViolationError(f"container {container.id} references unknown node ids {unknown_member_ids}")
            if container.id in proposal_ids or container.id in node_ids:
                raise ContractViolationError(f"container id collides with proposal or node id: {container.id}")
        for node in instance.nodes:
            _validate_confidence(node.confidence, label=node.id)
            _validate_bbox(node.bbox, label=node.id)
            if not node.source:
                raise ContractViolationError(f"node {node.id} must declare a source")
            if not node.provenance:
                raise ContractViolationError(f"node {node.id} must declare provenance")
            if node.id in proposal_ids:
                raise ContractViolationError(f"node id collides with proposal id: {node.id}")
        for proposal_id in instance.source_proposal_ids:
            if proposal_id not in proposal_ids:
                raise ContractViolationError(f"instance {instance.id} references unknown proposal {proposal_id}")
        if not instance.provenance:
            raise ContractViolationError(f"instance {instance.id} must declare provenance")

    for evidence in slide_ir.connector_evidence:
        _validate_connector_evidence(evidence, node_ids=node_ids, container_ids=container_ids)

    if slide_ir.connector_candidates or slide_ir.unattached_connector_evidence:
        if slide_ir.primitive_scene is None:
            raise ContractViolationError("connector attachment outputs require a primitive_scene payload")

    for connector in slide_ir.connectors:
        _validate_confidence(connector.confidence, label=connector.id)
        if connector.source_instance_id is not None and connector.source_instance_id not in instance_ids:
            raise ContractViolationError(
                f"connector {connector.id} references unknown source instance {connector.source_instance_id}"
            )
        if connector.target_instance_id is not None and connector.target_instance_id not in instance_ids:
            raise ContractViolationError(
                f"connector {connector.id} references unknown target instance {connector.target_instance_id}"
            )
        if connector.source_node_id is not None and connector.source_node_id not in node_ids:
            raise ContractViolationError(f"connector {connector.id} references unknown source node {connector.source_node_id}")
        if connector.target_node_id is not None and connector.target_node_id not in node_ids:
            raise ContractViolationError(f"connector {connector.id} references unknown target node {connector.target_node_id}")

    for token in slide_ir.style_tokens:
        unknown_targets = [
            target_id
            for target_id in token.target_ids
            if target_id not in instance_ids and target_id not in node_ids and target_id not in container_ids
        ]
        if unknown_targets:
            raise ContractViolationError(f"style token {token.id} targets unknown ids {unknown_targets}")

    if slide_ir.residual_canvas is not None:
        text_ids = {region.id for region in slide_ir.text_regions}
        raster_ids = {region.id for region in slide_ir.raster_regions}
        unknown_text_ids = [item for item in slide_ir.residual_canvas.canvas.text_region_ids if item not in text_ids]
        unknown_raster_ids = [item for item in slide_ir.residual_canvas.canvas.raster_region_ids if item not in raster_ids]
        if unknown_text_ids:
            raise ContractViolationError(f"residual canvas references unknown text regions {unknown_text_ids}")
        if unknown_raster_ids:
            raise ContractViolationError(f"residual canvas references unknown raster regions {unknown_raster_ids}")

    if slide_ir.primitive_scene is not None:
        validate_primitive_scene(slide_ir.primitive_scene)
        if slide_ir.primitive_scene.image_size != slide_ir.image_size:
            raise ContractViolationError("primitive scene image size must match slide_ir.image_size")
        if slide_ir.connector_candidates != slide_ir.primitive_scene.connector_candidates:
            raise ContractViolationError("slide_ir.connector_candidates must mirror primitive_scene.connector_candidates")
        if slide_ir.unattached_connector_evidence != slide_ir.primitive_scene.unattached_connector_evidence:
            raise ContractViolationError(
                "slide_ir.unattached_connector_evidence must mirror primitive_scene.unattached_connector_evidence"
            )
        primitive_node_ids = {item.id for item in slide_ir.primitive_scene.nodes}
        primitive_container_ids = {item.id for item in slide_ir.primitive_scene.containers}
        port_ids = {item.id for item in slide_ir.primitive_scene.ports}
        for candidate in slide_ir.connector_candidates:
            _validate_connector_candidate(
                candidate,
                evidence_ids=evidence_ids,
                port_ids=port_ids,
                node_ids=primitive_node_ids,
                container_ids=primitive_container_ids,
            )
        for item in slide_ir.unattached_connector_evidence:
            _validate_unattached_connector_evidence(item, evidence_ids=evidence_ids, port_ids=port_ids)


def validate_primitive_scene(scene: PrimitiveScene) -> None:
    if not scene.provenance:
        raise ContractViolationError("primitive scene provenance must not be empty")

    node_ids = {item.id for item in scene.nodes}
    container_ids = {item.id for item in scene.containers}
    port_ids = {item.id for item in scene.ports}
    text_ids = {item.id for item in scene.texts}

    for node in scene.nodes:
        _validate_confidence(node.confidence, label=node.id)
        _validate_bbox(node.bbox, label=node.id)
        if not node.source:
            raise ContractViolationError(f"primitive node {node.id} must declare a source")
        if not node.provenance:
            raise ContractViolationError(f"primitive node {node.id} must declare provenance")
        unknown_port_ids = [port_id for port_id in node.port_ids if port_id not in port_ids]
        if unknown_port_ids:
            raise ContractViolationError(f"primitive node {node.id} references unknown ports {unknown_port_ids}")

    for container in scene.containers:
        _validate_confidence(container.confidence, label=container.id)
        _validate_bbox(container.bbox, label=container.id)
        if not container.source:
            raise ContractViolationError(f"primitive container {container.id} must declare a source")
        if not container.provenance:
            raise ContractViolationError(f"primitive container {container.id} must declare provenance")
        unknown_member_ids = [node_id for node_id in container.member_node_ids if node_id not in node_ids]
        if unknown_member_ids:
            raise ContractViolationError(
                f"primitive container {container.id} references unknown member nodes {unknown_member_ids}"
            )
        unknown_port_ids = [port_id for port_id in container.port_ids if port_id not in port_ids]
        if unknown_port_ids:
            raise ContractViolationError(f"primitive container {container.id} references unknown ports {unknown_port_ids}")

    for text in scene.texts:
        _validate_confidence(text.confidence, label=text.id)
        _validate_bbox(text.bbox, label=text.id)
        if not text.source:
            raise ContractViolationError(f"primitive text {text.id} must declare a source")
        if not text.provenance:
            raise ContractViolationError(f"primitive text {text.id} must declare provenance")
        unknown_owner_ids = [
            owner_id for owner_id in text.owner_ids if owner_id not in node_ids and owner_id not in container_ids
        ]
        if unknown_owner_ids:
            raise ContractViolationError(f"primitive text {text.id} references unknown owners {unknown_owner_ids}")

    for port in scene.ports:
        _validate_port(port, node_ids=node_ids, container_ids=container_ids)

    for item in scene.connector_candidates:
        _validate_connector_candidate(
            item,
            evidence_ids=set(),
            port_ids=port_ids,
            node_ids=node_ids,
            container_ids=container_ids,
            allow_unknown_evidence=True,
        )

    for item in scene.unattached_connector_evidence:
        _validate_unattached_connector_evidence(item, evidence_ids=set(), port_ids=port_ids, allow_unknown_evidence=True)

    for residual in scene.residuals:
        _validate_confidence(residual.confidence, label=residual.id)
        _validate_bbox(residual.bbox, label=residual.id)
        if not residual.source:
            raise ContractViolationError(f"primitive residual {residual.id} must declare a source")
        if not residual.provenance:
            raise ContractViolationError(f"primitive residual {residual.id} must declare provenance")

    if len(text_ids) != len(scene.texts):
        raise ContractViolationError("primitive text ids must be unique")


def _validate_confidence(confidence: float, *, label: str) -> None:
    if not 0.0 <= confidence <= 1.0:
        raise ContractViolationError(f"confidence out of range for {label}: {confidence}")


def _validate_connector_evidence(
    evidence: ConnectorEvidence,
    *,
    node_ids: set[str],
    container_ids: set[str],
) -> None:
    _validate_confidence(evidence.confidence, label=evidence.id)
    _validate_bbox(evidence.bbox, label=evidence.id)
    if len(evidence.path_points) < 2:
        raise ContractViolationError(f"connector evidence {evidence.id} must have at least two path points")
    if not evidence.source:
        raise ContractViolationError(f"connector evidence {evidence.id} must declare a source")
    if not evidence.provenance:
        raise ContractViolationError(f"connector evidence {evidence.id} must declare provenance")
    for node_id in (*evidence.start_nearby_node_ids, *evidence.end_nearby_node_ids):
        if node_id not in node_ids:
            raise ContractViolationError(f"connector evidence {evidence.id} references unknown node id {node_id}")
    for container_id in evidence.nearby_container_ids:
        if container_id not in container_ids:
            raise ContractViolationError(f"connector evidence {evidence.id} references unknown container id {container_id}")


def _validate_port(port: PortSpec, *, node_ids: set[str], container_ids: set[str]) -> None:
    _validate_confidence(port.confidence, label=port.id)
    if not port.source:
        raise ContractViolationError(f"port {port.id} must declare a source")
    if not port.provenance:
        raise ContractViolationError(f"port {port.id} must declare provenance")
    if port.owner_kind.value == "node" and port.owner_id not in node_ids:
        raise ContractViolationError(f"port {port.id} references unknown node owner {port.owner_id}")
    if port.owner_kind.value == "container" and port.owner_id not in container_ids:
        raise ContractViolationError(f"port {port.id} references unknown container owner {port.owner_id}")


def _validate_attachment(
    attachment: ConnectorAttachment,
    *,
    port_ids: set[str],
    node_ids: set[str],
    container_ids: set[str],
) -> None:
    _validate_confidence(attachment.confidence, label=attachment.port_id)
    if attachment.port_id not in port_ids:
        raise ContractViolationError(f"attachment references unknown port id {attachment.port_id}")
    if attachment.owner_kind.value == "node" and attachment.owner_id not in node_ids:
        raise ContractViolationError(f"attachment references unknown node owner {attachment.owner_id}")
    if attachment.owner_kind.value == "container" and attachment.owner_id not in container_ids:
        raise ContractViolationError(f"attachment references unknown container owner {attachment.owner_id}")
    if attachment.distance < 0.0:
        raise ContractViolationError(f"attachment distance must be non-negative for {attachment.port_id}")
    if not attachment.source:
        raise ContractViolationError(f"attachment {attachment.port_id} must declare a source")
    if not attachment.provenance:
        raise ContractViolationError(f"attachment {attachment.port_id} must declare provenance")


def _validate_connector_candidate(
    candidate: PrimitiveConnectorCandidate,
    *,
    evidence_ids: set[str],
    port_ids: set[str],
    node_ids: set[str],
    container_ids: set[str],
    allow_unknown_evidence: bool = False,
) -> None:
    _validate_confidence(candidate.confidence, label=candidate.id)
    _validate_bbox(candidate.bbox, label=candidate.id)
    if len(candidate.path_points) < 2:
        raise ContractViolationError(f"connector candidate {candidate.id} must have at least two path points")
    if not candidate.source:
        raise ContractViolationError(f"connector candidate {candidate.id} must declare a source")
    if not candidate.provenance:
        raise ContractViolationError(f"connector candidate {candidate.id} must declare provenance")
    if not allow_unknown_evidence and candidate.source_evidence_id not in evidence_ids:
        raise ContractViolationError(
            f"connector candidate {candidate.id} references unknown evidence {candidate.source_evidence_id}"
        )
    if candidate.start_attachment is None or candidate.end_attachment is None:
        raise ContractViolationError(f"connector candidate {candidate.id} must include both endpoint attachments")
    _validate_attachment(candidate.start_attachment, port_ids=port_ids, node_ids=node_ids, container_ids=container_ids)
    _validate_attachment(candidate.end_attachment, port_ids=port_ids, node_ids=node_ids, container_ids=container_ids)
    if candidate.start_attachment.owner_id == candidate.end_attachment.owner_id:
        raise ContractViolationError(f"connector candidate {candidate.id} cannot attach both ends to the same owner")


def _validate_unattached_connector_evidence(
    item: UnattachedConnectorEvidence,
    *,
    evidence_ids: set[str],
    port_ids: set[str],
    allow_unknown_evidence: bool = False,
) -> None:
    _validate_confidence(item.confidence, label=item.id)
    if not item.reason:
        raise ContractViolationError(f"unattached connector evidence {item.id} must include a reason")
    if not item.source:
        raise ContractViolationError(f"unattached connector evidence {item.id} must declare a source")
    if not item.provenance:
        raise ContractViolationError(f"unattached connector evidence {item.id} must declare provenance")
    if not allow_unknown_evidence and item.evidence_id not in evidence_ids:
        raise ContractViolationError(
            f"unattached connector evidence {item.id} references unknown evidence {item.evidence_id}"
        )
    unknown_port_ids = [port_id for port_id in item.candidate_port_ids if port_id not in port_ids]
    if unknown_port_ids:
        raise ContractViolationError(
            f"unattached connector evidence {item.id} references unknown candidate ports {unknown_port_ids}"
        )


def _validate_bbox(bbox, *, label: str) -> None:
    if bbox.width <= 0 or bbox.height <= 0:
        raise ContractViolationError(f"invalid bbox for {label}: non-positive extent")


def _validate_view_shape(array: np.ndarray, *, image_size, label: str, allow_channels: bool) -> None:
    if array.ndim not in {2, 3}:
        raise ContractViolationError(f"{label} must be 2D or 3D")
    expected_hw = (image_size.height, image_size.width)
    if tuple(array.shape[:2]) != expected_hw:
        raise ContractViolationError(f"{label} shape mismatch: expected {expected_hw}, got {array.shape[:2]}")
    if not allow_channels and array.ndim != 2:
        raise ContractViolationError(f"{label} must be 2D")
