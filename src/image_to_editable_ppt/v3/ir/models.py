from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from image_to_editable_ppt.v3.core.enums import (
    BranchKind,
    ConnectorKind,
    ConnectorOrientation,
    ContainerKind,
    DiagramFamily,
    NodeKind,
    PortOwnerKind,
    PortSide,
    RasterRegionKind,
    ResidualKind,
    StyleTokenKind,
    TextRegionRole,
)
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
    role: TextRegionRole = TextRegionRole.UNKNOWN
    text: str | None = None
    source: str = "placeholder"
    provenance: tuple[str, ...] = ()


@dataclass(slots=True)
class TextLayerResult:
    image_size: ImageSize
    regions: tuple[TextRegion, ...] = ()
    soft_mask: np.ndarray = field(default_factory=lambda: np.zeros((0, 0), dtype=np.float32))
    masked_structure_view: np.ndarray = field(default_factory=lambda: np.zeros((0, 0), dtype=np.uint8))
    source_branch: BranchKind = BranchKind.STRUCTURE
    provenance: tuple[str, ...] = ()
    diagnostics: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class RasterRegion:
    id: str
    bbox: BBox
    confidence: float
    reason: str
    kind: RasterRegionKind = RasterRegionKind.COMPLEX_REGION
    source: str = "placeholder"
    provenance: tuple[str, ...] = ()


@dataclass(slots=True)
class RasterLayerResult:
    image_size: ImageSize
    regions: tuple[RasterRegion, ...] = ()
    subtraction_mask: np.ndarray = field(default_factory=lambda: np.zeros((0, 0), dtype=np.float32))
    subtracted_structure_view: np.ndarray = field(default_factory=lambda: np.zeros((0, 0), dtype=np.uint8))
    source_branch: BranchKind = BranchKind.STRUCTURE
    provenance: tuple[str, ...] = ()
    diagnostics: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class FamilyProposal:
    id: str
    family: DiagramFamily
    confidence: float
    evidence: tuple[str, ...] = ()
    provenance: tuple[str, ...] = ()
    focus_bbox: BBox | None = None


@dataclass(slots=True, frozen=True)
class DiagramNode:
    id: str
    kind: NodeKind
    bbox: BBox
    confidence: float = 1.0
    label: str | None = None
    text_region_ids: tuple[str, ...] = ()
    source: str = "placeholder"
    provenance: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class DiagramContainer:
    id: str
    kind: ContainerKind
    bbox: BBox
    confidence: float
    member_node_ids: tuple[str, ...] = ()
    label: str | None = None
    source: str = "placeholder"
    provenance: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class DiagramInstance:
    id: str
    family: DiagramFamily
    confidence: float
    bbox: BBox
    containers: tuple[DiagramContainer, ...] = ()
    nodes: tuple[DiagramNode, ...] = ()
    text_region_ids: tuple[str, ...] = ()
    source_proposal_ids: tuple[str, ...] = ()
    provenance: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class ConnectorSpec:
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

    @property
    def waypoints(self) -> tuple[Point, ...]:
        return self.path_points


@dataclass(slots=True, frozen=True)
class ConnectorEvidence:
    id: str
    kind: ConnectorKind
    orientation: ConnectorOrientation
    bbox: BBox
    confidence: float
    path_points: tuple[Point, ...] = ()
    arrowhead_start: bool = False
    arrowhead_end: bool = False
    start_nearby_node_ids: tuple[str, ...] = ()
    end_nearby_node_ids: tuple[str, ...] = ()
    nearby_container_ids: tuple[str, ...] = ()
    source: str = "placeholder"
    provenance: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class PortSpec:
    id: str
    owner_id: str
    owner_kind: PortOwnerKind
    side: PortSide
    point: Point
    confidence: float
    source: str = "placeholder"
    provenance: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class ConnectorAttachment:
    port_id: str
    owner_id: str
    owner_kind: PortOwnerKind
    side: PortSide
    point: Point
    distance: float
    confidence: float
    source: str = "placeholder"
    provenance: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class PrimitiveNode:
    id: str
    kind: NodeKind
    bbox: BBox
    confidence: float
    label: str | None = None
    text_region_ids: tuple[str, ...] = ()
    port_ids: tuple[str, ...] = ()
    source: str = "placeholder"
    provenance: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class PrimitiveContainer:
    id: str
    kind: ContainerKind
    bbox: BBox
    confidence: float
    member_node_ids: tuple[str, ...] = ()
    label: str | None = None
    port_ids: tuple[str, ...] = ()
    source: str = "placeholder"
    provenance: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class PrimitiveText:
    id: str
    role: TextRegionRole
    bbox: BBox
    confidence: float
    text: str | None = None
    owner_ids: tuple[str, ...] = ()
    source: str = "placeholder"
    provenance: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class PrimitiveConnectorCandidate:
    id: str
    kind: ConnectorKind
    bbox: BBox
    confidence: float
    source_evidence_id: str
    path_points: tuple[Point, ...] = ()
    start_attachment: ConnectorAttachment | None = None
    end_attachment: ConnectorAttachment | None = None
    arrowhead_start: bool = False
    arrowhead_end: bool = False
    source: str = "placeholder"
    provenance: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class UnattachedConnectorEvidence:
    id: str
    evidence_id: str
    reason: str
    confidence: float
    candidate_port_ids: tuple[str, ...] = ()
    source: str = "placeholder"
    provenance: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class PrimitiveResidual:
    id: str
    kind: ResidualKind
    bbox: BBox
    confidence: float
    reason: str
    source: str = "placeholder"
    provenance: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class PrimitiveScene:
    image_size: ImageSize
    nodes: tuple[PrimitiveNode, ...] = ()
    containers: tuple[PrimitiveContainer, ...] = ()
    texts: tuple[PrimitiveText, ...] = ()
    ports: tuple[PortSpec, ...] = ()
    connector_candidates: tuple[PrimitiveConnectorCandidate, ...] = ()
    unattached_connector_evidence: tuple[UnattachedConnectorEvidence, ...] = ()
    residuals: tuple[PrimitiveResidual, ...] = ()
    provenance: tuple[str, ...] = ()


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


@dataclass(slots=True)
class ResidualStructuralCanvas:
    id: str
    bbox: BBox
    image: np.ndarray
    source_branch: BranchKind = BranchKind.STRUCTURAL_CANVAS
    text_region_ids: tuple[str, ...] = ()
    raster_region_ids: tuple[str, ...] = ()
    provenance: tuple[str, ...] = ()


@dataclass(slots=True)
class ResidualCanvasResult:
    image_size: ImageSize
    text_mask: np.ndarray = field(default_factory=lambda: np.zeros((0, 0), dtype=np.float32))
    raster_mask: np.ndarray = field(default_factory=lambda: np.zeros((0, 0), dtype=np.float32))
    combined_mask: np.ndarray = field(default_factory=lambda: np.zeros((0, 0), dtype=np.float32))
    text_suppressed_view: np.ndarray = field(default_factory=lambda: np.zeros((0, 0), dtype=np.uint8))
    raster_suppressed_view: np.ndarray = field(default_factory=lambda: np.zeros((0, 0), dtype=np.uint8))
    canvas: ResidualStructuralCanvas | None = None
    provenance: tuple[str, ...] = ()
    diagnostics: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class SlideIR:
    image_size: ImageSize
    text_layer: TextLayerResult | None = None
    raster_layer: RasterLayerResult | None = None
    residual_canvas: ResidualCanvasResult | None = None
    family_proposals: tuple[FamilyProposal, ...] = ()
    diagram_instances: tuple[DiagramInstance, ...] = ()
    connector_evidence: tuple[ConnectorEvidence, ...] = ()
    connector_candidates: tuple[PrimitiveConnectorCandidate, ...] = ()
    unattached_connector_evidence: tuple[UnattachedConnectorEvidence, ...] = ()
    connectors: tuple[ConnectorSpec, ...] = ()
    primitive_scene: PrimitiveScene | None = None
    text_regions: tuple[TextRegion, ...] = ()
    raster_regions: tuple[RasterRegion, ...] = ()
    style_tokens: tuple[StyleToken, ...] = ()
    residual_regions: tuple[ResidualRegion, ...] = ()
