from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .ir import BBox


@dataclass(slots=True)
class Component:
    pixels: np.ndarray
    bbox: BBox
    area: int

    @property
    def width(self) -> float:
        return self.bbox.width

    @property
    def height(self) -> float:
        return self.bbox.height


def find_connected_components(mask: np.ndarray) -> list[Component]:
    if mask.ndim != 2:
        raise ValueError("mask must be 2D")
    height, width = mask.shape
    visited = np.zeros_like(mask, dtype=bool)
    components: list[Component] = []
    for y in range(height):
        for x in range(width):
            if not mask[y, x] or visited[y, x]:
                continue
            stack = [(y, x)]
            visited[y, x] = True
            pixels: list[tuple[int, int]] = []
            min_x = max_x = x
            min_y = max_y = y
            while stack:
                cy, cx = stack.pop()
                pixels.append((cy, cx))
                if cx < min_x:
                    min_x = cx
                if cx > max_x:
                    max_x = cx
                if cy < min_y:
                    min_y = cy
                if cy > max_y:
                    max_y = cy
                for ny in range(max(0, cy - 1), min(height, cy + 2)):
                    for nx in range(max(0, cx - 1), min(width, cx + 2)):
                        if mask[ny, nx] and not visited[ny, nx]:
                            visited[ny, nx] = True
                            stack.append((ny, nx))
            pixels_arr = np.asarray(pixels, dtype=np.int32)
            components.append(
                Component(
                    pixels=pixels_arr,
                    bbox=BBox(float(min_x), float(min_y), float(max_x + 1), float(max_y + 1)),
                    area=int(len(pixels)),
                )
            )
    return components


def remove_small_components(mask: np.ndarray, min_area: int) -> np.ndarray:
    filtered = mask.copy()
    for component in find_connected_components(mask):
        if component.area >= min_area:
            continue
        ys = component.pixels[:, 0]
        xs = component.pixels[:, 1]
        filtered[ys, xs] = False
    return filtered
