"""IR models and validators for v3."""

from .models import (
    ConnectorSpec,
    DiagramInstance,
    DiagramNode,
    FamilyProposal,
    MultiViewBranch,
    MultiViewBundle,
    RasterRegion,
    ResidualRegion,
    SlideIR,
    StyleToken,
    TextRegion,
)
from .validate import validate_multiview_bundle, validate_slide_ir

__all__ = [
    "ConnectorSpec",
    "DiagramInstance",
    "DiagramNode",
    "FamilyProposal",
    "MultiViewBranch",
    "MultiViewBundle",
    "RasterRegion",
    "ResidualRegion",
    "SlideIR",
    "StyleToken",
    "TextRegion",
    "validate_multiview_bundle",
    "validate_slide_ir",
]
