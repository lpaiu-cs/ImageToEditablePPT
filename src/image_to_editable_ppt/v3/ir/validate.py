from __future__ import annotations

from image_to_editable_ppt.v3.core.contracts import ContractViolationError
from image_to_editable_ppt.v3.core.enums import BranchKind
from image_to_editable_ppt.v3.ir.models import MultiViewBundle, SlideIR


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


def validate_slide_ir(slide_ir: SlideIR) -> None:
    instance_ids = {instance.id for instance in slide_ir.diagram_instances}
    node_ids = {node.id for instance in slide_ir.diagram_instances for node in instance.nodes}
    proposal_ids = {proposal.id for proposal in slide_ir.family_proposals}

    for region in (*slide_ir.text_regions, *slide_ir.raster_regions, *slide_ir.residual_regions):
        _validate_confidence(region.confidence, label=region.id)
        _validate_bbox(region.bbox, label=region.id)

    for proposal in slide_ir.family_proposals:
        _validate_confidence(proposal.confidence, label=proposal.id)
        if proposal.focus_bbox is not None:
            _validate_bbox(proposal.focus_bbox, label=proposal.id)

    for instance in slide_ir.diagram_instances:
        _validate_confidence(instance.confidence, label=instance.id)
        _validate_bbox(instance.bbox, label=instance.id)
        for node in instance.nodes:
            _validate_bbox(node.bbox, label=node.id)
            if node.id in proposal_ids:
                raise ContractViolationError(f"node id collides with proposal id: {node.id}")
        for proposal_id in instance.source_proposal_ids:
            if proposal_id not in proposal_ids:
                raise ContractViolationError(f"instance {instance.id} references unknown proposal {proposal_id}")

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
        unknown_targets = [target_id for target_id in token.target_ids if target_id not in instance_ids and target_id not in node_ids]
        if unknown_targets:
            raise ContractViolationError(f"style token {token.id} targets unknown ids {unknown_targets}")


def _validate_confidence(confidence: float, *, label: str) -> None:
    if not 0.0 <= confidence <= 1.0:
        raise ContractViolationError(f"confidence out of range for {label}: {confidence}")


def _validate_bbox(bbox, *, label: str) -> None:
    if bbox.width <= 0 or bbox.height <= 0:
        raise ContractViolationError(f"invalid bbox for {label}: non-positive extent")
