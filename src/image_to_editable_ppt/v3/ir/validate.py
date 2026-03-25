from __future__ import annotations

import numpy as np

from image_to_editable_ppt.v3.core.contracts import ContractViolationError
from image_to_editable_ppt.v3.core.enums import BranchKind
from image_to_editable_ppt.v3.core.types import BBox
from image_to_editable_ppt.v3.ir.models import MultiViewBundle, RasterLayerResult, ResidualCanvasResult, SlideIR, TextLayerResult


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
    proposal_ids = {proposal.id for proposal in slide_ir.family_proposals}

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

    if slide_ir.residual_canvas is not None:
        text_ids = {region.id for region in slide_ir.text_regions}
        raster_ids = {region.id for region in slide_ir.raster_regions}
        unknown_text_ids = [item for item in slide_ir.residual_canvas.canvas.text_region_ids if item not in text_ids]
        unknown_raster_ids = [item for item in slide_ir.residual_canvas.canvas.raster_region_ids if item not in raster_ids]
        if unknown_text_ids:
            raise ContractViolationError(f"residual canvas references unknown text regions {unknown_text_ids}")
        if unknown_raster_ids:
            raise ContractViolationError(f"residual canvas references unknown raster regions {unknown_raster_ids}")


def _validate_confidence(confidence: float, *, label: str) -> None:
    if not 0.0 <= confidence <= 1.0:
        raise ContractViolationError(f"confidence out of range for {label}: {confidence}")


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
