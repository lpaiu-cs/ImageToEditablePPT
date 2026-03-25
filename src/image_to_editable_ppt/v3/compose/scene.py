from __future__ import annotations

from image_to_editable_ppt.v3.app.config import V3Config
from image_to_editable_ppt.v3.core.enums import RasterRegionKind, ResidualKind
from image_to_editable_ppt.v3.ir.models import (
    DiagramContainer,
    DiagramInstance,
    DiagramNode,
    PortSpec,
    PrimitiveConnectorCandidate,
    PrimitiveContainer,
    PrimitiveNode,
    PrimitiveResidual,
    PrimitiveScene,
    PrimitiveText,
    RasterLayerResult,
    ResidualCanvasResult,
    ResidualRegion,
    TextLayerResult,
    UnattachedConnectorEvidence,
)


def build_primitive_scene(
    *,
    text_layer: TextLayerResult,
    raster_layer: RasterLayerResult,
    residual_canvas: ResidualCanvasResult,
    instances: tuple[DiagramInstance, ...],
    ports: tuple[PortSpec, ...],
    connector_candidates: tuple[PrimitiveConnectorCandidate, ...],
    unattached_connector_evidence: tuple[UnattachedConnectorEvidence, ...],
    residual_regions: tuple[ResidualRegion, ...],
    config: V3Config,
) -> PrimitiveScene:
    del residual_canvas, config
    node_port_ids = _owner_port_ids(ports)
    nodes = tuple(
        _to_primitive_node(node, port_ids=node_port_ids.get(node.id, ()))
        for instance in instances
        for node in instance.nodes
    )
    containers = tuple(
        _to_primitive_container(container, port_ids=node_port_ids.get(container.id, ()))
        for instance in instances
        for container in instance.containers
    )
    texts = tuple(
        _to_primitive_text(
            region,
            instances=instances,
        )
        for region in text_layer.regions
    )
    residuals = (
        *tuple(_to_raster_residual(item) for item in raster_layer.regions),
        *tuple(_to_unresolved_residual(item) for item in residual_regions),
    )
    return PrimitiveScene(
        image_size=text_layer.image_size,
        nodes=nodes,
        containers=containers,
        texts=texts,
        ports=ports,
        connector_candidates=connector_candidates,
        unattached_connector_evidence=unattached_connector_evidence,
        residuals=tuple(residuals),
        provenance=(
            "compose:primitive_scene",
            "source:diagram_instances",
            "source:text_layer",
            "source:raster_layer",
            "source:connector_attachment",
        ),
    )


def _owner_port_ids(ports: tuple[PortSpec, ...]) -> dict[str, tuple[str, ...]]:
    by_owner: dict[str, list[str]] = {}
    for port in ports:
        by_owner.setdefault(port.owner_id, []).append(port.id)
    return {owner_id: tuple(port_ids) for owner_id, port_ids in by_owner.items()}


def _to_primitive_node(node: DiagramNode, *, port_ids: tuple[str, ...]) -> PrimitiveNode:
    return PrimitiveNode(
        id=node.id,
        kind=node.kind,
        bbox=node.bbox,
        confidence=node.confidence,
        label=node.label,
        text_region_ids=node.text_region_ids,
        port_ids=port_ids,
        source=node.source,
        provenance=(*node.provenance, "compose:primitive_node"),
    )


def _to_primitive_container(container: DiagramContainer, *, port_ids: tuple[str, ...]) -> PrimitiveContainer:
    return PrimitiveContainer(
        id=container.id,
        kind=container.kind,
        bbox=container.bbox,
        confidence=container.confidence,
        member_node_ids=container.member_node_ids,
        label=container.label,
        port_ids=port_ids,
        source=container.source,
        provenance=(*container.provenance, "compose:primitive_container"),
    )


def _to_primitive_text(region, *, instances: tuple[DiagramInstance, ...]) -> PrimitiveText:
    owner_ids = _text_owner_ids(region.id, region.bbox, instances=instances)
    return PrimitiveText(
        id=region.id,
        role=region.role,
        bbox=region.bbox,
        confidence=region.confidence,
        text=region.text,
        owner_ids=owner_ids,
        source=region.source,
        provenance=(*region.provenance, "compose:primitive_text"),
    )


def _text_owner_ids(region_id: str, bbox, *, instances: tuple[DiagramInstance, ...]) -> tuple[str, ...]:
    owners: list[str] = []
    for instance in instances:
        for node in instance.nodes:
            if region_id in node.text_region_ids or node.bbox.overlaps(bbox) or node.bbox.contains_point(bbox.center):
                owners.append(node.id)
        if owners:
            continue
        for container in instance.containers:
            if container.bbox.overlaps(bbox) or container.bbox.contains_point(bbox.center):
                owners.append(container.id)
    return tuple(dict.fromkeys(owners))


def _to_raster_residual(region) -> PrimitiveResidual:
    kind = ResidualKind.NON_DIAGRAM if region.kind is RasterRegionKind.NON_DIAGRAM else ResidualKind.RASTER
    return PrimitiveResidual(
        id=region.id,
        kind=kind,
        bbox=region.bbox,
        confidence=region.confidence,
        reason=region.reason,
        source=region.source,
        provenance=(*region.provenance, "compose:raster_residual"),
    )


def _to_unresolved_residual(region: ResidualRegion) -> PrimitiveResidual:
    return PrimitiveResidual(
        id=region.id,
        kind=region.kind,
        bbox=region.bbox,
        confidence=region.confidence,
        reason=region.reason,
        source="compose:residual_region",
        provenance=("compose:primitive_residual", f"source:{region.id}"),
    )
