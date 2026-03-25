from __future__ import annotations

from dataclasses import dataclass

from image_to_editable_ppt.v3.app.config import V3Config
from image_to_editable_ppt.v3.core.enums import PortOwnerKind, PortSide
from image_to_editable_ppt.v3.core.types import Point
from image_to_editable_ppt.v3.ir.models import DiagramInstance, PortSpec


@dataclass(slots=True, frozen=True)
class OrthogonalPortGenerator:
    def generate(
        self,
        *,
        instances: tuple[DiagramInstance, ...],
        config: V3Config,
    ) -> tuple[PortSpec, ...]:
        del config
        ports: list[PortSpec] = []

        for instance in instances:
            for container in instance.containers:
                ports.extend(
                    _ports_for_owner(
                        owner_id=container.id,
                        owner_kind=PortOwnerKind.CONTAINER,
                        bbox=container.bbox,
                        confidence=max(0.45, container.confidence - 0.08),
                        source="phase5_port_generator:container_midpoints",
                        provenance=("family:orthogonal_flow", "port_rule:edge_midpoints"),
                    )
                )
            for node in instance.nodes:
                ports.extend(
                    _ports_for_owner(
                        owner_id=node.id,
                        owner_kind=PortOwnerKind.NODE,
                        bbox=node.bbox,
                        confidence=max(0.52, node.confidence),
                        source="phase5_port_generator:node_midpoints",
                        provenance=("family:orthogonal_flow", "port_rule:edge_midpoints"),
                    )
                )

        return tuple(ports)


def generate_ports(
    *,
    instances: tuple[DiagramInstance, ...],
    config: V3Config,
) -> tuple[PortSpec, ...]:
    return OrthogonalPortGenerator().generate(instances=instances, config=config)


def _ports_for_owner(
    *,
    owner_id: str,
    owner_kind: PortOwnerKind,
    bbox,
    confidence: float,
    source: str,
    provenance: tuple[str, ...],
) -> tuple[PortSpec, ...]:
    return (
        PortSpec(
            id=f"{owner_id}:port:{PortSide.TOP.value}",
            owner_id=owner_id,
            owner_kind=owner_kind,
            side=PortSide.TOP,
            point=Point((bbox.x0 + bbox.x1) / 2.0, bbox.y0),
            confidence=confidence,
            source=source,
            provenance=provenance,
        ),
        PortSpec(
            id=f"{owner_id}:port:{PortSide.RIGHT.value}",
            owner_id=owner_id,
            owner_kind=owner_kind,
            side=PortSide.RIGHT,
            point=Point(bbox.x1, (bbox.y0 + bbox.y1) / 2.0),
            confidence=confidence,
            source=source,
            provenance=provenance,
        ),
        PortSpec(
            id=f"{owner_id}:port:{PortSide.BOTTOM.value}",
            owner_id=owner_id,
            owner_kind=owner_kind,
            side=PortSide.BOTTOM,
            point=Point((bbox.x0 + bbox.x1) / 2.0, bbox.y1),
            confidence=confidence,
            source=source,
            provenance=provenance,
        ),
        PortSpec(
            id=f"{owner_id}:port:{PortSide.LEFT.value}",
            owner_id=owner_id,
            owner_kind=owner_kind,
            side=PortSide.LEFT,
            point=Point(bbox.x0, (bbox.y0 + bbox.y1) / 2.0),
            confidence=confidence,
            source=source,
            provenance=provenance,
        ),
    )
