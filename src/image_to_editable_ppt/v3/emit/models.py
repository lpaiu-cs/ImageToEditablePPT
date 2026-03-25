from __future__ import annotations

from dataclasses import dataclass

from image_to_editable_ppt.v3.core.enums import (
    ConnectorKind,
    ContainerKind,
    NodeKind,
    PortOwnerKind,
    ResidualKind,
    TextRegionRole,
)
from image_to_editable_ppt.v3.core.types import BBox, ImageSize, Point


@dataclass(slots=True, frozen=True)
class EmitShapePrimitive:
    id: str
    owner_kind: PortOwnerKind
    shape_kind: NodeKind | ContainerKind
    bbox: BBox
    confidence: float
    label: str | None = None
    source: str = "placeholder"
    provenance: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class EmitTextPrimitive:
    id: str
    role: TextRegionRole
    bbox: BBox
    confidence: float
    text: str | None = None
    owner_ids: tuple[str, ...] = ()
    source: str = "placeholder"
    provenance: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class EmitConnectorPrimitive:
    id: str
    kind: ConnectorKind
    confidence: float
    source_owner_id: str
    source_owner_kind: PortOwnerKind
    target_owner_id: str
    target_owner_kind: PortOwnerKind
    source_port_id: str
    target_port_id: str
    path_points: tuple[Point, ...] = ()
    source_instance_id: str | None = None
    target_instance_id: str | None = None
    arrowhead_start: bool = False
    arrowhead_end: bool = False
    source_candidate_id: str | None = None
    source_evidence_id: str | None = None
    source: str = "placeholder"
    provenance: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class EmitResidualPrimitive:
    id: str
    kind: ResidualKind
    bbox: BBox
    confidence: float
    reason: str
    source: str = "placeholder"
    provenance: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class EmitScene:
    image_size: ImageSize
    coordinate_space: str = "image_space"
    shapes: tuple[EmitShapePrimitive, ...] = ()
    texts: tuple[EmitTextPrimitive, ...] = ()
    connectors: tuple[EmitConnectorPrimitive, ...] = ()
    residuals: tuple[EmitResidualPrimitive, ...] = ()
    source: str = "placeholder"
    provenance: tuple[str, ...] = ()
