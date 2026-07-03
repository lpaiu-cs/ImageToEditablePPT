"""Conservative per-shape visual style sampling from the source image.

Style tokens are not implemented yet; this is the minimal "대표 단색으로 요약"
step (principle 4): for each emit shape we take the median interior colour as
the fill and the median border-band colour as the stroke. Anything that cannot
be distinguished from the page background is left unfilled — a wrong fill is a
strong signal of misunderstanding the structure (principle 5), so we only fill
when the evidence is clear.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from image_to_editable_ppt.v3.core.enums import NodeKind, PortOwnerKind

if TYPE_CHECKING:
    from image_to_editable_ppt.v3.emit.models import EmitScene, EmitShapePrimitive

# Treat colours at least this far from white (max channel distance) as evidence
# of an intentional fill/stroke; below it we assume page background / AA noise.
_BACKGROUND_DISTANCE = 24


@dataclass(slots=True, frozen=True)
class ShapeVisualStyle:
    fill: tuple[int, int, int] | None = None
    stroke: tuple[int, int, int] | None = None
    stroke_width: float = 1.0


def sample_shape_styles(rgb: np.ndarray, scene: "EmitScene") -> dict[str, ShapeVisualStyle]:
    """Median-colour styles for every shape in the scene, keyed by shape id."""
    height, width = rgb.shape[:2]
    styles: dict[str, ShapeVisualStyle] = {}
    for shape in scene.shapes:
        styles[shape.id] = _sample_shape(rgb, shape, width=width, height=height)
    return styles


def _sample_shape(rgb: np.ndarray, shape: "EmitShapePrimitive", *, width: int, height: int) -> ShapeVisualStyle:
    if shape.shape_kind is NodeKind.LABEL_ANCHOR:
        # Text-only node: borderless, unfilled by definition.
        return ShapeVisualStyle()

    bbox = shape.bbox
    x0, y0 = max(0, int(bbox.x0)), max(0, int(bbox.y0))
    x1, y1 = min(width, int(bbox.x1)), min(height, int(bbox.y1))
    if x1 - x0 < 4 or y1 - y0 < 4:
        return ShapeVisualStyle(stroke=(71, 85, 105))

    if shape.owner_kind is PortOwnerKind.CONTAINER:
        # A container interior mostly holds member nodes; sample a thin band just
        # inside the border where the panel's own colour is visible.
        inset = max(3, min(x1 - x0, y1 - y0) // 12)
        fill = _band_median(rgb, x0, y0, x1, y1, offset=inset, band=max(2, inset // 2))
    else:
        # Node interior, inset past the border stroke and label glyphs are rare
        # enough that the median survives them.
        inset_x = max(2, (x1 - x0) // 5)
        inset_y = max(2, (y1 - y0) // 5)
        patch = rgb[y0 + inset_y : y1 - inset_y, x0 + inset_x : x1 - inset_x]
        fill = _median_color(patch)

    stroke = _band_median(rgb, x0, y0, x1, y1, offset=0, band=2)

    fill_out = fill if fill is not None and _distinct_from_background(fill) else None
    stroke_out = stroke if stroke is not None and _distinct_from_background(stroke) else None
    if fill_out is None and stroke_out is None:
        # The detector saw a shape here; keep it visible and editable with a
        # neutral outline rather than emitting an invisible object.
        stroke_out = (71, 85, 105)
    return ShapeVisualStyle(fill=fill_out, stroke=stroke_out)


def _band_median(
    rgb: np.ndarray, x0: int, y0: int, x1: int, y1: int, *, offset: int, band: int
) -> tuple[int, int, int] | None:
    ox0, oy0, ox1, oy1 = x0 + offset, y0 + offset, x1 - offset, y1 - offset
    if ox1 - ox0 < 2 * band + 2 or oy1 - oy0 < 2 * band + 2:
        return None
    pixels = np.concatenate(
        [
            rgb[oy0 : oy0 + band, ox0:ox1].reshape(-1, 3),
            rgb[oy1 - band : oy1, ox0:ox1].reshape(-1, 3),
            rgb[oy0:oy1, ox0 : ox0 + band].reshape(-1, 3),
            rgb[oy0:oy1, ox1 - band : ox1].reshape(-1, 3),
        ]
    )
    return _median_of(pixels)


def _median_color(patch: np.ndarray) -> tuple[int, int, int] | None:
    if patch.size == 0:
        return None
    return _median_of(patch.reshape(-1, 3))


def _median_of(pixels: np.ndarray) -> tuple[int, int, int] | None:
    if pixels.shape[0] == 0:
        return None
    median = np.median(pixels, axis=0)
    return (int(median[0]), int(median[1]), int(median[2]))


def _distinct_from_background(color: tuple[int, int, int]) -> bool:
    return max(255 - channel for channel in color) >= _BACKGROUND_DISTANCE
