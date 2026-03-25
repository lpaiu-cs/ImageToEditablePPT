from __future__ import annotations

import cv2
import numpy as np

from image_to_editable_ppt.v3.app.config import V3Config
from image_to_editable_ppt.v3.core.enums import BranchKind, TextRegionRole
from image_to_editable_ppt.v3.core.types import BBox
from image_to_editable_ppt.v3.ir.models import MultiViewBundle, TextLayerResult, TextRegion


def extract_text_layer(bundle: MultiViewBundle, *, config: V3Config) -> TextLayerResult:
    text_view = bundle.branch(BranchKind.TEXT).image
    structure_view = bundle.branch(BranchKind.STRUCTURE).image
    height, width = text_view.shape
    image_area = height * width
    _, binary = cv2.threshold(text_view, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    binary = cv2.medianBlur(binary, 3)
    dilation_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(3, width // 80), 3))
    merged = cv2.dilate(binary, dilation_kernel, iterations=1)
    component_count, _, stats, _ = cv2.connectedComponentsWithStats(merged, connectivity=8)

    soft_mask = np.zeros((height, width), dtype=np.float32)
    regions: list[TextRegion] = []
    min_component_area = max(9, image_area // 4000)
    max_text_height = max(8, int(height * 0.18))
    padding = max(1, min(height, width) // 120)

    for component_index in range(1, component_count):
        x, y, w, h, area = stats[component_index]
        if area < min_component_area or w < 4 or h < 4:
            continue
        if h > max_text_height or w > int(width * 0.92):
            continue
        binary_roi = binary[y : y + h, x : x + w]
        density = float(np.count_nonzero(binary_roi)) / float(max(1, w * h))
        if density < 0.03 or density > 0.85:
            continue
        bbox = _expand_bbox(x, y, w, h, width=width, height=height, padding=padding)
        soft_mask[int(bbox.y0) : int(bbox.y1), int(bbox.x0) : int(bbox.x1)] = 1.0
        regions.append(
            TextRegion(
                id=f"text:{len(regions) + 1}",
                bbox=bbox,
                confidence=min(0.95, 0.35 + density * 0.9),
                role=_classify_role(bbox=bbox, image_width=width, image_height=height),
                text=None,
                source="phase2_text_connected_components",
                provenance=("branch:text", "threshold:otsu_inv", "grouping:dilate"),
            )
        )

    if config.soft_mask_text_in_structure and regions:
        soft_mask = cv2.GaussianBlur(soft_mask, ksize=(0, 0), sigmaX=1.2, sigmaY=1.2)
        soft_mask = np.clip(soft_mask, 0.0, 1.0)
    else:
        soft_mask = np.zeros((height, width), dtype=np.float32)
    masked_structure = _apply_soft_mask(structure_view, soft_mask)

    return TextLayerResult(
        image_size=bundle.image_size,
        regions=tuple(regions),
        soft_mask=soft_mask,
        masked_structure_view=masked_structure,
        source_branch=BranchKind.STRUCTURE,
        provenance=("branch:text", "mask:soft" if config.soft_mask_text_in_structure else "mask:none"),
        diagnostics={
            "threshold_mode": "otsu_inv",
            "component_count": component_count - 1,
            "text_region_count": len(regions),
            "soft_mask_applied": bool(config.soft_mask_text_in_structure and regions),
        },
    )


def _apply_soft_mask(structure_view: np.ndarray, soft_mask: np.ndarray) -> np.ndarray:
    masked = structure_view.astype(np.float32) * (1.0 - soft_mask) + 255.0 * soft_mask
    return np.clip(masked, 0.0, 255.0).astype(np.uint8)


def _classify_role(*, bbox: BBox, image_width: int, image_height: int) -> TextRegionRole:
    if bbox.y0 <= image_height * 0.18 and bbox.width >= image_width * 0.22:
        return TextRegionRole.TITLE
    if bbox.height >= image_height * 0.10:
        return TextRegionRole.BODY
    return TextRegionRole.LABEL


def _expand_bbox(x: int, y: int, w: int, h: int, *, width: int, height: int, padding: int) -> BBox:
    x0 = max(0, x - padding)
    y0 = max(0, y - padding)
    x1 = min(width, x + w + padding)
    y1 = min(height, y + h + padding)
    return BBox(float(x0), float(y0), float(x1), float(y1))
