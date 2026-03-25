from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from image_to_editable_ppt.v3.core.enums import BranchKind, ConnectorKind, DiagramFamily, NodeKind, ResidualKind, StyleTokenKind
from image_to_editable_ppt.v3.core.types import BBox, ImageSize, Point


@dataclass(slots=True)
class MultiViewBranch:
    kind: BranchKind
    image: np.ndarray
    description: str
    soft_mask: np.ndarray | None = None

    @property
    def height(self) -> int:
        return int(self.image.shape[0])

    @property
    def width(self) -> int:
        return int(self.image.shape[1])


@dataclass(slots=True)
class MultiViewBundle:
    image_size: ImageSize
    branches: dict[BranchKind, MultiViewBranch] = field(default_factory=dict)

    def branch(self, kind: BranchKind) -> MultiViewBranch:
        return self.branches[kind]


@dataclass(slots=True, frozen=True)
class TextRegion:
    id: str
    bbox: BBox
    confidence: float
    text: str | None = None
    source: str = "placeholder"


@dataclass(slots=True, frozen=True)
class RasterRegion:
    id: str
    bbox: BBox
    confidence: float
    reason: str
    source: str = "placeholder"


@dataclass(slots=True, frozen=True)
class FamilyProposal:
    id: str
    family: DiagramFamily
    confidence: float
    evidence: tuple[str, ...] = ()
    focus_bbox: BBox | None = None


@dataclass(slots=True, frozen=True)
class DiagramNode:
    id: str
    kind: NodeKind
    bbox: BBox
    label: str | None = None
    text_region_ids: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class DiagramInstance:
    id: str
    family: DiagramFamily
    confidence: float
    bbox: BBox
    nodes: tuple[DiagramNode, ...] = ()
    text_region_ids: tuple[str, ...] = ()
    source_proposal_ids: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class ConnectorSpec:
    id: str
    kind: ConnectorKind
    confidence: float
    source_instance_id: str | None = None
    source_node_id: str | None = None
    target_instance_id: str | None = None
    target_node_id: str | None = None
    waypoints: tuple[Point, ...] = ()


@dataclass(slots=True, frozen=True)
class StyleToken:
    id: str
    kind: StyleTokenKind
    value: str
    target_ids: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class ResidualRegion:
    id: str
    kind: ResidualKind
    bbox: BBox
    confidence: float
    reason: str


@dataclass(slots=True, frozen=True)
class SlideIR:
    image_size: ImageSize
    family_proposals: tuple[FamilyProposal, ...] = ()
    diagram_instances: tuple[DiagramInstance, ...] = ()
    connectors: tuple[ConnectorSpec, ...] = ()
    text_regions: tuple[TextRegion, ...] = ()
    raster_regions: tuple[RasterRegion, ...] = ()
    style_tokens: tuple[StyleToken, ...] = ()
    residual_regions: tuple[ResidualRegion, ...] = ()
