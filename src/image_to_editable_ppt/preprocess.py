from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from .components import remove_small_components


@dataclass(slots=True)
class ProcessedImage:
    image: Image.Image
    array: np.ndarray
    gray: np.ndarray
    background_color: tuple[int, int, int]
    foreground_mask: np.ndarray
    boundary_mask: np.ndarray

    @property
    def size(self) -> tuple[int, int]:
        return self.image.size


def load_image(path: str | Path) -> Image.Image:
    return Image.open(path).convert("RGB")


def preprocess_image(
    image: Image.Image,
    *,
    foreground_threshold: float,
    min_component_area: int,
) -> ProcessedImage:
    array = np.asarray(image.convert("RGB"), dtype=np.uint8)
    gray = np.asarray(image.convert("L"), dtype=np.float32)
    background = estimate_background_color(array)
    foreground = build_foreground_mask(array, background, foreground_threshold)
    foreground = remove_small_components(foreground, min_component_area)
    boundary = build_boundary_mask(foreground)
    boundary = remove_small_components(boundary, max(4, min_component_area // 2))
    return ProcessedImage(
        image=image,
        array=array,
        gray=gray,
        background_color=background,
        foreground_mask=foreground,
        boundary_mask=boundary,
    )


def estimate_background_color(array: np.ndarray) -> tuple[int, int, int]:
    border = np.concatenate(
        [
            array[0, :, :],
            array[-1, :, :],
            array[:, 0, :],
            array[:, -1, :],
        ],
        axis=0,
    )
    median = np.median(border, axis=0)
    return tuple(int(channel) for channel in median)


def build_foreground_mask(
    array: np.ndarray,
    background_color: tuple[int, int, int],
    threshold: float,
) -> np.ndarray:
    background = np.asarray(background_color, dtype=np.float32)
    diff = np.linalg.norm(array.astype(np.float32) - background[None, None, :], axis=2)
    return diff > threshold


def build_boundary_mask(mask: np.ndarray) -> np.ndarray:
    eroded = erode_mask(mask)
    return mask & ~eroded


def erode_mask(mask: np.ndarray) -> np.ndarray:
    padded = np.pad(mask, ((1, 1), (1, 1)), mode="constant", constant_values=False)
    height, width = mask.shape
    eroded = mask.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            y0 = 1 + dy
            x0 = 1 + dx
            eroded &= padded[y0 : y0 + height, x0 : x0 + width]
    return eroded
