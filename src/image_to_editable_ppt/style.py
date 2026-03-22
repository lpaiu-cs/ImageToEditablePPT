from __future__ import annotations

import math

import numpy as np

from .ir import BBox


def color_distance(color_a: tuple[int, int, int], color_b: tuple[int, int, int]) -> float:
    a = np.asarray(color_a, dtype=np.float32)
    b = np.asarray(color_b, dtype=np.float32)
    return float(np.linalg.norm(a - b))


def median_color(colors: np.ndarray) -> tuple[int, int, int]:
    if colors.size == 0:
        return (0, 0, 0)
    median = np.median(colors.astype(np.float32), axis=0)
    return tuple(int(round(channel)) for channel in median)


def sample_bbox_border_colors(
    array: np.ndarray,
    bbox: BBox,
    stroke_width: float,
) -> tuple[int, int, int]:
    x0 = max(0, int(math.floor(bbox.x0)))
    y0 = max(0, int(math.floor(bbox.y0)))
    x1 = min(array.shape[1], int(math.ceil(bbox.x1)))
    y1 = min(array.shape[0], int(math.ceil(bbox.y1)))
    width = max(1, int(round(stroke_width)))
    if x1 <= x0 or y1 <= y0:
        return (0, 0, 0)
    parts = [
        array[y0 : min(y0 + width, y1), x0:x1, :],
        array[max(y1 - width, y0) : y1, x0:x1, :],
        array[y0:y1, x0 : min(x0 + width, x1), :],
        array[y0:y1, max(x1 - width, x0) : x1, :],
    ]
    colors = np.concatenate([part.reshape(-1, 3) for part in parts if part.size], axis=0)
    return median_color(colors)


def estimate_fill_color(
    array: np.ndarray,
    bbox: BBox,
    stroke_width: float,
    background_color: tuple[int, int, int],
    delta_threshold: float,
) -> tuple[bool, tuple[int, int, int] | None]:
    inset = max(2.0, stroke_width + 1.0)
    inner = bbox.inset(inset)
    x0 = max(0, int(math.floor(inner.x0)))
    y0 = max(0, int(math.floor(inner.y0)))
    x1 = min(array.shape[1], int(math.ceil(inner.x1)))
    y1 = min(array.shape[0], int(math.ceil(inner.y1)))
    if x1 - x0 < 2 or y1 - y0 < 2:
        return False, None
    colors = array[y0:y1, x0:x1, :].reshape(-1, 3)
    fill = median_color(colors)
    if color_distance(fill, background_color) < delta_threshold:
        return False, None
    return True, fill
