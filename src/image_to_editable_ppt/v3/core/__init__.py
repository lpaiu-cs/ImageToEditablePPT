"""Core enums, primitives, and contracts for v3."""

from .contracts import ContractViolationError, StageRecord
from .enums import (
    BranchKind,
    ConnectorKind,
    DiagramFamily,
    NodeKind,
    RasterRegionKind,
    ResidualKind,
    StageName,
    StyleTokenKind,
    TextRegionRole,
)
from .types import BBox, ImageSize, Point, RGBColor

__all__ = [
    "BBox",
    "BranchKind",
    "ConnectorKind",
    "ContractViolationError",
    "DiagramFamily",
    "ImageSize",
    "NodeKind",
    "Point",
    "RasterRegionKind",
    "ResidualKind",
    "RGBColor",
    "StageName",
    "StageRecord",
    "StyleTokenKind",
    "TextRegionRole",
]
