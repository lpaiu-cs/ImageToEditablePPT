from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

try:
    import cv2
except ImportError:  # pragma: no cover - guarded by dependency/tests
    cv2 = None

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
    smoothed_array: np.ndarray
    gray: np.ndarray
    background_color: tuple[int, int, int]
    foreground_mask: np.ndarray
    detail_mask_raw: np.ndarray
    detail_mask: np.ndarray
    fill_region_mask: np.ndarray
    boundary_mask_raw: np.ndarray
    boundary_mask: np.ndarray
    non_diagram_mask: np.ndarray
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
    fill_region_background_ratio: float = 0.68,
    fill_region_uniformity_ratio: float = 0.84,
    fill_region_edge_ratio: float = 0.82,
    non_diagram_edge_density: float = 0.12,
    non_diagram_color_variance: float = 220.0,
    non_diagram_side_support: float = 0.24,
) -> ProcessedImage:
    array = np.asarray(image.convert("RGB"), dtype=np.uint8)
    gray = np.asarray(image.convert("L"), dtype=np.float32)
    smoothed_array = smooth_color_regions(array)
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
    boundary_raw = build_boundary_mask(foreground)
    boundary_raw = remove_small_components(boundary_raw, provisional_area)
    scale = estimate_scale_context(
        image_size=image.size,
        boundary_mask=boundary_raw,
        min_component_area=min_component_area,
        min_stroke_length=min_stroke_length or 18,
        min_box_size=min_box_size or 24,
        min_relative_line_length=min_relative_line_length,
        min_relative_box_size=min_relative_box_size,
    )
    foreground = remove_small_components(foreground, scale.min_component_area)
    detail = remove_small_components(detail_raw, max(4, scale.min_component_area // 2))
    fill_region_mask = build_fill_region_mask(
        array=array,
        smoothed_array=smoothed_array,
        gray=gray,
        background_color=background,
        threshold=foreground_threshold,
        scale=scale,
        background_ratio=fill_region_background_ratio,
        uniformity_ratio=fill_region_uniformity_ratio,
        edge_ratio=fill_region_edge_ratio,
    )
    fill_region_mask = remove_small_components(
        fill_region_mask,
        max(scale.min_component_area * 4, int(round(scale.min_box_size * scale.min_box_size * 0.8))),
    )
    boundary_raw = build_boundary_mask(foreground)
    boundary_raw = remove_small_components(boundary_raw, max(4, scale.min_component_area // 2))
    non_diagram_mask = build_non_diagram_mask(
        array=array,
        gray=gray,
        foreground_mask=foreground,
        boundary_mask=boundary_raw,
        scale=scale,
        edge_density_threshold=non_diagram_edge_density,
        color_variance_threshold=non_diagram_color_variance,
        side_support_threshold=non_diagram_side_support,
    )
    if non_diagram_mask.any():
        detail_raw = detail_raw & ~non_diagram_mask
        detail = detail & ~non_diagram_mask
        fill_region_mask = fill_region_mask & ~non_diagram_mask
    boundary = build_boundary_mask(foreground)
    boundary = remove_small_components(boundary, max(4, scale.min_component_area // 2))
    if non_diagram_mask.any():
        boundary = boundary & ~non_diagram_mask
    return ProcessedImage(
        image=image,
        array=array,
        smoothed_array=smoothed_array,
        gray=gray,
        background_color=background,
        foreground_mask=foreground,
        detail_mask_raw=detail_raw,
        detail_mask=detail,
        fill_region_mask=fill_region_mask,
        boundary_mask_raw=boundary_raw,
        boundary_mask=boundary,
        non_diagram_mask=non_diagram_mask,
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


def smooth_color_regions(array: np.ndarray) -> np.ndarray:
    if cv2 is None:
        return array.copy()
    max_dimension = max(array.shape[0], array.shape[1])
    spatial_radius = max(6, int(round(max_dimension / 140.0)))
    color_radius = max(14, int(round(max_dimension / 95.0)))
    return cv2.pyrMeanShiftFiltering(array, sp=spatial_radius, sr=color_radius)


def build_fill_region_mask(
    *,
    array: np.ndarray,
    smoothed_array: np.ndarray,
    gray: np.ndarray,
    background_color: tuple[int, int, int],
    threshold: float,
    scale: ScaleContext,
    background_ratio: float,
    uniformity_ratio: float,
    edge_ratio: float,
) -> np.ndarray:
    background = np.asarray(background_color, dtype=np.float32)
    smoothed = smoothed_array.astype(np.float32)
    raw = array.astype(np.float32)
    diff = np.linalg.norm(smoothed - background[None, None, :], axis=2)
    uniformity = np.linalg.norm(raw - smoothed, axis=2)
    smoothed_gray = smoothed.mean(axis=2)
    smoothed_edges = gray_edge_magnitude(smoothed_gray)
    raw_edges = gray_edge_magnitude(gray)
    fill_mask = diff > max(threshold * background_ratio, 18.0)
    fill_mask &= uniformity <= max(threshold * uniformity_ratio, 16.0)
    fill_mask &= smoothed_edges <= max(threshold * edge_ratio, 18.0)
    fill_mask &= raw_edges <= max(threshold * 1.2, 36.0)
    if cv2 is not None and fill_mask.any():
        kernel_size = max(3, int(round(scale.estimated_stroke_width * 3.0)))
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
        fill_mask = cv2.morphologyEx(fill_mask.astype(np.uint8), cv2.MORPH_CLOSE, kernel) > 0
    return fill_mask


def build_non_diagram_mask(
    *,
    array: np.ndarray,
    gray: np.ndarray,
    foreground_mask: np.ndarray,
    boundary_mask: np.ndarray,
    scale: ScaleContext,
    edge_density_threshold: float,
    color_variance_threshold: float,
    side_support_threshold: float,
) -> np.ndarray:
    if not foreground_mask.any():
        return np.zeros_like(foreground_mask, dtype=bool)
    edge_mask = canny_edge_mask(gray)
    suppression = np.zeros_like(foreground_mask, dtype=bool)
    min_bbox_area = max(
        scale.min_component_area * 12,
        int(round(scale.min_box_size * scale.min_box_size * 2.2)),
    )
    for component in find_connected_components(foreground_mask):
        if component.area < scale.min_component_area * 4 or component.bbox.area < min_bbox_area:
            continue
        bbox = component.bbox.expand(max(2.0, scale.estimated_stroke_width * 1.6))
        x0 = max(0, int(np.floor(bbox.x0)))
        y0 = max(0, int(np.floor(bbox.y0)))
        x1 = min(array.shape[1], int(np.ceil(bbox.x1)))
        y1 = min(array.shape[0], int(np.ceil(bbox.y1)))
        if x1 <= x0 or y1 <= y0:
            continue
        window = array[y0:y1, x0:x1, :]
        if window.size == 0:
            continue
        edge_density = float(edge_mask[y0:y1, x0:x1].mean())
        color_variance = float(np.var(window.reshape(-1, 3), axis=0).mean())
        side_support = bbox_side_support(boundary_mask, x0=x0, y0=y0, x1=x1, y1=y1, scale=scale)
        rectangularity = component.area / max(1.0, component.bbox.area)
        if side_support >= side_support_threshold and rectangularity >= 0.34:
            continue
        if (
            rectangularity >= 0.84
            and edge_density < edge_density_threshold * 1.35
            and color_variance < color_variance_threshold * 0.72
        ):
            continue
        high_texture = edge_density >= edge_density_threshold and color_variance >= color_variance_threshold * 0.65
        high_variance = color_variance >= color_variance_threshold and edge_density >= edge_density_threshold * 0.75
        chaotic_edges = edge_density >= edge_density_threshold * 1.85 and side_support < side_support_threshold * 0.75
        if not (high_texture or high_variance or chaotic_edges):
            continue
        suppression[y0:y1, x0:x1] = True
    return suppression


def canny_edge_mask(gray: np.ndarray) -> np.ndarray:
    gray_u8 = np.clip(gray, 0.0, 255.0).astype(np.uint8)
    if cv2 is not None:
        return cv2.Canny(gray_u8, 48, 144) > 0
    return gray_edge_magnitude(gray) >= 32.0


def bbox_side_support(
    mask: np.ndarray,
    *,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    scale: ScaleContext,
) -> float:
    if x1 <= x0 or y1 <= y0:
        return 0.0
    band = max(1, int(round(scale.estimated_stroke_width * 1.6)))
    top = float(mask[y0 : min(mask.shape[0], y0 + band), x0:x1].mean()) if y0 < y1 else 0.0
    bottom = float(mask[max(0, y1 - band) : y1, x0:x1].mean()) if y0 < y1 else 0.0
    left = float(mask[y0:y1, x0 : min(mask.shape[1], x0 + band)].mean()) if x0 < x1 else 0.0
    right = float(mask[y0:y1, max(0, x1 - band) : x1].mean()) if x0 < x1 else 0.0
    return max(top, bottom, left, right)


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
