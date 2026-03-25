from __future__ import annotations

import numpy as np

from image_to_editable_ppt.v3.core.enums import BranchKind
from image_to_editable_ppt.v3.core.types import BBox
from image_to_editable_ppt.v3.ir.models import MultiViewBundle, RasterLayerResult, ResidualCanvasResult, ResidualStructuralCanvas, TextLayerResult


def build_residual_canvas(
    bundle: MultiViewBundle,
    *,
    text_layer: TextLayerResult,
    raster_layer: RasterLayerResult,
) -> ResidualCanvasResult:
    text_mask = np.clip(text_layer.soft_mask.astype(np.float32), 0.0, 1.0)
    raster_mask = np.clip(raster_layer.subtraction_mask.astype(np.float32), 0.0, 1.0)
    combined_mask = np.maximum(text_mask, raster_mask)
    final_canvas_view = raster_layer.subtracted_structure_view.copy()
    canvas = ResidualStructuralCanvas(
        id="residual_canvas:1",
        bbox=BBox.from_image_size(bundle.image_size),
        image=final_canvas_view,
        source_branch=BranchKind.STRUCTURAL_CANVAS,
        text_region_ids=tuple(region.id for region in text_layer.regions),
        raster_region_ids=tuple(region.id for region in raster_layer.regions),
        provenance=("text:soft_mask", "raster:subtraction"),
    )
    bundle.branch(BranchKind.STRUCTURAL_CANVAS).image = final_canvas_view.copy()
    bundle.branch(BranchKind.STRUCTURAL_CANVAS).soft_mask = combined_mask
    bundle.branch(BranchKind.STRUCTURAL_CANVAS).description = "Residual structural canvas after text masking and raster subtraction."
    return ResidualCanvasResult(
        image_size=bundle.image_size,
        text_mask=text_mask,
        raster_mask=raster_mask,
        combined_mask=combined_mask,
        text_suppressed_view=text_layer.masked_structure_view.copy(),
        raster_suppressed_view=raster_layer.subtracted_structure_view.copy(),
        canvas=canvas,
        provenance=("branch:structure", "text:soft_mask", "raster:subtraction"),
        diagnostics={
            "text_region_count": len(text_layer.regions),
            "raster_region_count": len(raster_layer.regions),
            "text_mask_pixels": int(np.count_nonzero(text_mask > 0.0)),
            "raster_mask_pixels": int(np.count_nonzero(raster_mask > 0.0)),
        },
    )
