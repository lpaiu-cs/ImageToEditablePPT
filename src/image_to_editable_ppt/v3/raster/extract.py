from __future__ import annotations

import cv2
import numpy as np

from image_to_editable_ppt.v3.app.config import V3Config
from image_to_editable_ppt.v3.core.enums import BranchKind, RasterRegionKind
from image_to_editable_ppt.v3.core.types import BBox
from image_to_editable_ppt.v3.ir.models import MultiViewBundle, RasterLayerResult, RasterRegion, TextLayerResult


def extract_raster_layer(
    bundle: MultiViewBundle,
    *,
    text_layer: TextLayerResult,
    config: V3Config,
) -> RasterLayerResult:
    style_view = bundle.branch(BranchKind.STYLE).image
    height, width = style_view.shape[:2]
    image_area = height * width
    gray = cv2.cvtColor(style_view, cv2.COLOR_RGB2GRAY)
    gray_f = gray.astype(np.float32)
    mean = cv2.blur(gray_f, (9, 9))
    mean_sq = cv2.blur(gray_f * gray_f, (9, 9))
    local_std = np.sqrt(np.maximum(mean_sq - mean * mean, 0.0))
    candidate = (local_std > 18.0).astype(np.uint8) * 255
    candidate[text_layer.soft_mask > 0.10] = 0
    candidate = cv2.morphologyEx(candidate, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7)))
    candidate = cv2.morphologyEx(candidate, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)))
    component_count, labels, stats, _ = cv2.connectedComponentsWithStats(candidate, connectivity=8)

    subtraction_mask = np.zeros((height, width), dtype=np.float32)
    regions: list[RasterRegion] = []
    min_component_area = max(64, image_area // 80)
    padding = max(1, min(height, width) // 100)

    for component_index in range(1, component_count):
        x, y, w, h, area = stats[component_index]
        if area < min_component_area or w < 12 or h < 12:
            continue
        fill_ratio = float(area) / float(max(1, w * h))
        if fill_ratio < 0.38:
            continue
        label_roi = labels[y : y + h, x : x + w] == component_index
        mean_std = float(local_std[y : y + h, x : x + w][label_roi].mean())
        bbox = _expand_bbox(x, y, w, h, width=width, height=height, padding=padding)
        subtraction_mask[int(bbox.y0) : int(bbox.y1), int(bbox.x0) : int(bbox.x1)] = 1.0
        regions.append(
            RasterRegion(
                id=f"raster:{len(regions) + 1}",
                bbox=bbox,
                confidence=min(0.96, 0.42 + max(0.0, mean_std - 18.0) / 36.0),
                kind=RasterRegionKind.PHOTO_LIKE if mean_std >= 28.0 else RasterRegionKind.COMPLEX_REGION,
                reason="local_texture_variance",
                source="phase2_raster_local_variance",
                provenance=("branch:style", "metric:local_stddev", "morph:close_open"),
            )
        )

    source_structure = text_layer.masked_structure_view if config.soft_mask_text_in_structure else bundle.branch(BranchKind.STRUCTURE).image
    subtracted_structure = source_structure.copy()
    subtracted_structure[subtraction_mask > 0.0] = 255
    return RasterLayerResult(
        image_size=bundle.image_size,
        regions=tuple(regions),
        subtraction_mask=subtraction_mask,
        subtracted_structure_view=subtracted_structure,
        source_branch=BranchKind.STRUCTURE,
        provenance=("branch:style", "subtraction:raster_mask"),
        diagnostics={
            "local_std_threshold": 18.0,
            "component_count": component_count - 1,
            "raster_region_count": len(regions),
            "text_mask_exclusion": bool(np.any(text_layer.soft_mask > 0.0)),
        },
    )


def _expand_bbox(x: int, y: int, w: int, h: int, *, width: int, height: int, padding: int) -> BBox:
    x0 = max(0, x - padding)
    y0 = max(0, y - padding)
    x1 = min(width, x + w + padding)
    y1 = min(height, y + h + padding)
    return BBox(float(x0), float(y0), float(x1), float(y1))
