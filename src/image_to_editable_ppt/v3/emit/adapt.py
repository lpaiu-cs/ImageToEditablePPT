from __future__ import annotations

from image_to_editable_ppt.v3.core.enums import PortOwnerKind
from image_to_editable_ppt.v3.emit.models import (
    EmitConnectorPrimitive,
    EmitResidualPrimitive,
    EmitScene,
    EmitShapePrimitive,
    EmitTextPrimitive,
)
from image_to_editable_ppt.v3.ir.models import ConnectorSpec, PrimitiveScene


def build_emit_scene(
    *,
    primitive_scene: PrimitiveScene,
    connectors: tuple[ConnectorSpec, ...],
) -> EmitScene:
    shapes = (
        *tuple(_container_to_emit_shape(item) for item in primitive_scene.containers),
        *tuple(_node_to_emit_shape(item) for item in primitive_scene.nodes),
    )
    texts = tuple(_text_to_emit_text(item) for item in primitive_scene.texts)
    emit_connectors = tuple(_connector_to_emit_connector(item) for item in connectors)
    residuals = tuple(_residual_to_emit_residual(item) for item in primitive_scene.residuals)

    return EmitScene(
        image_size=primitive_scene.image_size,
        coordinate_space="image_space",
        shapes=tuple(shapes),
        texts=texts,
        connectors=emit_connectors,
        residuals=residuals,
        source="phase6_emit_adapter",
        provenance=(
            *primitive_scene.provenance,
            "emit_adapter:scene",
        ),
    )


def _container_to_emit_shape(item) -> EmitShapePrimitive:
    return EmitShapePrimitive(
        id=item.id,
        owner_kind=PortOwnerKind.CONTAINER,
        shape_kind=item.kind,
        bbox=item.bbox,
        confidence=item.confidence,
        label=item.label,
        source=item.source,
        provenance=(*item.provenance, "emit_adapter:shape"),
    )


def _node_to_emit_shape(item) -> EmitShapePrimitive:
    return EmitShapePrimitive(
        id=item.id,
        owner_kind=PortOwnerKind.NODE,
        shape_kind=item.kind,
        bbox=item.bbox,
        confidence=item.confidence,
        label=item.label,
        source=item.source,
        provenance=(*item.provenance, "emit_adapter:shape"),
    )


def _text_to_emit_text(item) -> EmitTextPrimitive:
    return EmitTextPrimitive(
        id=item.id,
        role=item.role,
        bbox=item.bbox,
        confidence=item.confidence,
        text=item.text,
        owner_ids=item.owner_ids,
        source=item.source,
        provenance=(*item.provenance, "emit_adapter:text"),
    )


def _connector_to_emit_connector(item: ConnectorSpec) -> EmitConnectorPrimitive:
    return EmitConnectorPrimitive(
        id=item.id,
        kind=item.kind,
        confidence=item.confidence,
        source_owner_id=item.source_owner_id,
        source_owner_kind=item.source_owner_kind,
        target_owner_id=item.target_owner_id,
        target_owner_kind=item.target_owner_kind,
        source_port_id=item.source_port_id,
        target_port_id=item.target_port_id,
        path_points=item.path_points,
        source_instance_id=item.source_instance_id,
        target_instance_id=item.target_instance_id,
        arrowhead_start=item.arrowhead_start,
        arrowhead_end=item.arrowhead_end,
        source_candidate_id=item.source_candidate_id,
        source_evidence_id=item.source_evidence_id,
        source=item.source,
        provenance=(*item.provenance, "emit_adapter:connector"),
    )


def _residual_to_emit_residual(item) -> EmitResidualPrimitive:
    return EmitResidualPrimitive(
        id=item.id,
        kind=item.kind,
        bbox=item.bbox,
        confidence=item.confidence,
        reason=item.reason,
        source=item.source,
        provenance=(*item.provenance, "emit_adapter:residual"),
    )
