"""IR models and validators for v3."""

from .models import (
    ConnectorSpec,
    DiagramInstance,
    DiagramNode,
    FamilyProposal,
    MultiViewBranch,
    MultiViewBundle,
    RasterLayerResult,
    RasterRegion,
    ResidualCanvasResult,
    ResidualStructuralCanvas,
    ResidualRegion,
    SlideIR,
    StyleToken,
    TextLayerResult,
    TextRegion,
)
from .validate import (
    validate_multiview_bundle,
    validate_raster_layer_result,
    validate_residual_canvas_result,
    validate_slide_ir,
    validate_text_layer_result,
)

__all__ = [
    "ConnectorSpec",
    "DiagramInstance",
    "DiagramNode",
    "FamilyProposal",
    "MultiViewBranch",
    "MultiViewBundle",
    "RasterLayerResult",
    "RasterRegion",
    "ResidualCanvasResult",
    "ResidualStructuralCanvas",
    "ResidualRegion",
    "SlideIR",
    "StyleToken",
    "TextLayerResult",
    "TextRegion",
    "validate_multiview_bundle",
    "validate_raster_layer_result",
    "validate_residual_canvas_result",
    "validate_slide_ir",
    "validate_text_layer_result",
]
