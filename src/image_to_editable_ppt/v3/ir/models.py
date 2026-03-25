from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from image_to_editable_ppt.v3.core.enums import (
    BranchKind,
    ConnectorKind,
    DiagramFamily,
    NodeKind,
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
    connectors: tuple[ConnectorSpec, ...] = ()
    text_regions: tuple[TextRegion, ...] = ()
    raster_regions: tuple[RasterRegion, ...] = ()
    style_tokens: tuple[StyleToken, ...] = ()
    residual_regions: tuple[ResidualRegion, ...] = ()
