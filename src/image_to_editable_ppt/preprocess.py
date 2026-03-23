from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

from .components import find_connected_components, remove_small_components


@dataclass(slots=True)
class ScaleContext:
    estimated_stroke_width: float
    min_component_area: int
    min_stroke_length: int
    min_linear_length: int
    min_box_size: int


@dataclass(slots=True)
class ProcessedImage:
    image: Image.Image
    array: np.ndarray
    gray: np.ndarray
    background_color: tuple[int, int, int]
    foreground_mask: np.ndarray
    detail_mask_raw: np.ndarray
    detail_mask: np.ndarray
    boundary_mask_raw: np.ndarray
    boundary_mask: np.ndarray
    scale: ScaleContext

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
    min_stroke_length: int | None = None,
    min_box_size: int | None = None,
    min_relative_line_length: float = 0.04,
    min_relative_box_size: float = 0.02,
    adaptive_background: bool = True,
    background_blur_divisor: float = 72.0,
) -> ProcessedImage:
    array = np.asarray(image.convert("RGB"), dtype=np.uint8)
    gray = np.asarray(image.convert("L"), dtype=np.float32)
    background = estimate_background_color(array)
    foreground, detail = build_foreground_mask(
        image=image,
        array=array,
        gray=gray,
        background_color=background,
        threshold=foreground_threshold,
        adaptive_background=adaptive_background,
        background_blur_divisor=background_blur_divisor,
    )
    provisional_area = max(4, min_component_area // 2)
    foreground = remove_small_components(foreground, provisional_area)
    detail_raw = remove_small_components(detail, provisional_area)
    boundary = build_boundary_mask(foreground)
    boundary = remove_small_components(boundary, provisional_area)
    scale = estimate_scale_context(
        image_size=image.size,
        boundary_mask=boundary,
        min_component_area=min_component_area,
        min_stroke_length=min_stroke_length or 18,
        min_box_size=min_box_size or 24,
        min_relative_line_length=min_relative_line_length,
        min_relative_box_size=min_relative_box_size,
    )
    foreground = remove_small_components(foreground, scale.min_component_area)
    detail = remove_small_components(detail_raw, max(4, scale.min_component_area // 2))
    boundary = build_boundary_mask(foreground)
    boundary = remove_small_components(boundary, max(4, scale.min_component_area // 2))
    return ProcessedImage(
        image=image,
        array=array,
        gray=gray,
        background_color=background,
        foreground_mask=foreground,
        detail_mask_raw=detail_raw,
        detail_mask=detail,
        boundary_mask_raw=boundary,
        boundary_mask=boundary,
        scale=scale,
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
    *,
    image: Image.Image,
    array: np.ndarray,
    gray: np.ndarray,
    background_color: tuple[int, int, int],
    threshold: float,
    adaptive_background: bool,
    background_blur_divisor: float,
) -> tuple[np.ndarray, np.ndarray]:
    background = np.asarray(background_color, dtype=np.float32)
    diff = np.linalg.norm(array.astype(np.float32) - background[None, None, :], axis=2)
    if not adaptive_background:
        foreground = diff > threshold
        detail = gray_edge_magnitude(gray) > threshold * 0.58
        return foreground, detail
    blur_radius = max(4.0, max(image.size) / max(8.0, background_blur_divisor))
    blurred = np.asarray(image.convert("RGB").filter(ImageFilter.GaussianBlur(radius=blur_radius)), dtype=np.float32)
    local_diff = np.linalg.norm(array.astype(np.float32) - blurred, axis=2)
    gray_blurred = np.asarray(image.convert("L").filter(ImageFilter.GaussianBlur(radius=blur_radius)), dtype=np.float32)
    local_contrast = np.abs(gray - gray_blurred)
    edges = gray_edge_magnitude(gray)
    detail = (local_contrast > threshold * 0.42) | (edges > threshold * 0.52)
    foreground = diff > threshold
    foreground |= (local_diff > threshold * 0.72) & (edges > threshold * 0.34)
    return foreground, detail


def gray_edge_magnitude(gray: np.ndarray) -> np.ndarray:
    left = np.pad(gray[:, :-1], ((0, 0), (1, 0)), mode="edge")
    right = np.pad(gray[:, 1:], ((0, 0), (0, 1)), mode="edge")
    up = np.pad(gray[:-1, :], ((1, 0), (0, 0)), mode="edge")
    down = np.pad(gray[1:, :], ((0, 1), (0, 0)), mode="edge")
    grad_x = np.abs(right - left)
    grad_y = np.abs(down - up)
    return np.maximum(grad_x, grad_y)


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


def estimate_scale_context(
    *,
    image_size: tuple[int, int],
    boundary_mask: np.ndarray,
    min_component_area: int,
    min_stroke_length: int,
    min_box_size: int,
    min_relative_line_length: float,
    min_relative_box_size: float,
) -> ScaleContext:
    max_dimension = max(image_size)
    estimated_stroke_width = estimate_stroke_width(boundary_mask, max_dimension=max_dimension)
    scale_factor = max(1.0, max_dimension / 256.0)
    effective_component_area = max(
        min_component_area,
        int(round(min_component_area * scale_factor * 0.72)),
        int(round((estimated_stroke_width + 1.0) ** 2 * 1.8)),
    )
    effective_stroke_length = max(
        min_stroke_length,
        int(round(estimated_stroke_width * 8.0)),
        int(round(max_dimension * min_relative_line_length * 0.55)),
    )
    effective_linear_length = max(
        effective_stroke_length,
        int(round(max_dimension * min_relative_line_length)),
    )
    effective_box_size = max(
        min_box_size,
        int(round(estimated_stroke_width * 9.0)),
        int(round(max_dimension * min_relative_box_size)),
    )
    return ScaleContext(
        estimated_stroke_width=estimated_stroke_width,
        min_component_area=effective_component_area,
        min_stroke_length=effective_stroke_length,
        min_linear_length=effective_linear_length,
        min_box_size=effective_box_size,
    )


def estimate_stroke_width(mask: np.ndarray, *, max_dimension: int) -> float:
    widths: list[float] = []
    for component in find_connected_components(mask):
        major = max(component.width, component.height)
        if major < 4:
            continue
        estimate = component.area / max(1.0, major)
        if 0.6 <= estimate <= max(12.0, min(component.width, component.height) * 1.5):
            widths.append(float(estimate))
    if widths:
        return float(np.clip(np.median(np.asarray(widths, dtype=np.float32)), 1.0, 12.0))
    return float(np.clip(max_dimension / 220.0, 1.0, 10.0))
