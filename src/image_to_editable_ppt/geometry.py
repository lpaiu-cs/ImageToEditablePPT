from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

import numpy as np
from PIL import Image, ImageDraw

try:
    import cv2
except ImportError:  # pragma: no cover - guarded by dependency/tests
    cv2 = None

from .config import PipelineConfig
from .detector import DetectionResult, detect_elements_with_metadata
from .diagnostics import DiagnosticsRecorder
from .ir import BBox, Element, Point
from .preprocess import ProcessedImage, preprocess_image
from .schema import ConnectorCandidate, CornerPrimitive, LinePrimitive, RectCandidate, RegionPrimitive, validate_stage_entities
from .style import median_color


@dataclass(slots=True)
class GeometryObservations:
    processed: ProcessedImage
    detection: DetectionResult


@dataclass(slots=True)
class GeometryStageResult:
    observations: GeometryObservations
    rect_candidates: list[RectCandidate]
    connector_candidates: list[ConnectorCandidate]
    line_primitives: list[LinePrimitive]
    corner_primitives: list[CornerPrimitive]
    region_primitives: list[RegionPrimitive]


def collect_observations(
    image: Image.Image,
    config: PipelineConfig,
) -> GeometryObservations:
    processed = preprocess_image(
        image,
        foreground_threshold=config.foreground_threshold,
        min_component_area=config.min_component_area,
        min_stroke_length=config.min_stroke_length,
        min_box_size=config.min_box_size,
        min_relative_line_length=config.min_relative_line_length,
        min_relative_box_size=config.min_relative_box_size,
        adaptive_background=config.adaptive_background,
        background_blur_divisor=config.background_blur_divisor,
        fill_region_background_ratio=config.fill_region_background_ratio,
        fill_region_uniformity_ratio=config.fill_region_uniformity_ratio,
        fill_region_edge_ratio=config.fill_region_edge_ratio,
        non_diagram_edge_density=config.non_diagram_edge_density,
        non_diagram_color_variance=config.non_diagram_color_variance,
        non_diagram_side_support=config.non_diagram_side_support,
    )
    return GeometryObservations(
        processed=processed,
        detection=detect_elements_with_metadata(processed, config),
    )


def build_geometry_candidates(
    image: Image.Image,
    config: PipelineConfig,
    *,
    diagnostics: DiagnosticsRecorder | None = None,
    stage: str = "01_geometry_raw",
) -> GeometryStageResult:
    recorder = diagnostics or DiagnosticsRecorder()
    observations = collect_observations(image, config)
    rect_candidates = [
        rect_candidate_from_element(element)
        for element in observations.detection.elements
        if element.kind in {"rect", "rounded_rect"}
    ]
    connector_candidates = [
        connector_candidate_from_element(element)
        for element in observations.detection.elements
        if element.kind in {"line", "orthogonal_connector", "arrow"}
    ]
    line_primitives = [
        line_primitive_from_element(element)
        for element in observations.detection.elements
        if element.kind in {"line", "orthogonal_connector", "arrow"}
    ]
    region_primitives = [
        region_primitive_from_element(element)
        for element in observations.detection.elements
        if element.kind in {"rect", "rounded_rect"}
    ]
    rect_candidates = list(validate_stage_entities(stage, "rect_candidates", rect_candidates, require_bbox=True))
    connector_candidates = list(validate_stage_entities(stage, "connector_candidates", connector_candidates, require_bbox=True))
    line_primitives = list(validate_stage_entities(stage, "line_primitives", line_primitives, require_bbox=True))
    region_primitives = list(validate_stage_entities(stage, "region_primitives", region_primitives, require_bbox=True))
    result = GeometryStageResult(
        observations=observations,
        rect_candidates=rect_candidates,
        connector_candidates=connector_candidates,
        line_primitives=line_primitives,
        corner_primitives=[],
        region_primitives=region_primitives,
    )
    if recorder.enabled:
        recorder.summary(
            stage,
            {
                "rect_candidate_count": len(rect_candidates),
                "connector_candidate_count": len(connector_candidates),
                "line_primitive_count": len(line_primitives),
                "rejected_region_count": len(observations.detection.rejected_regions),
            },
        )
        recorder.items(stage, "rect_candidates", rect_candidates)
        recorder.items(stage, "connector_candidates", connector_candidates)
        recorder.items(stage, "line_primitives", line_primitives)
        recorder.items(stage, "region_primitives", region_primitives)
        recorder.artifact(
            stage,
            "rejected_regions",
            [region.to_dict() for region in observations.detection.rejected_regions],
        )
        recorder.overlay(stage, "overlay", draw_geometry_overlay(image, rect_candidates, connector_candidates))
    return result


def rect_candidate_from_element(element: Element) -> RectCandidate:
    return RectCandidate(
        id=f"rect-candidate:{element.id}",
        kind=element.kind,
        object_type="container",
        bbox=element.bbox,
        score_total=element.confidence,
        score_terms={"element_confidence": element.confidence},
        source_ids=[element.id],
        provenance={"elements": [element.id]},
        corner_radius=getattr(element.geometry, "corner_radius", 0.0),
    )


def connector_candidate_from_element(element: Element) -> ConnectorCandidate:
    return ConnectorCandidate(
        id=f"connector-candidate:{element.id}",
        kind=element.kind,
        object_type="connector",
        edge_type="arrow" if element.kind == "arrow" else "line",
        bbox=element.bbox,
        score_total=element.confidence,
        score_terms={"element_confidence": element.confidence},
        source_ids=[element.id],
        provenance={"elements": [element.id]},
        point_ids=[f"{element.id}:p{index}" for index, _ in enumerate(getattr(element.geometry, "points", ()))],
    )


def line_primitive_from_element(element: Element) -> LinePrimitive:
    bbox = element.bbox
    orientation = "horizontal" if bbox.width >= bbox.height else "vertical"
    return LinePrimitive(
        id=f"line-primitive:{element.id}",
        kind=element.kind,
        bbox=bbox,
        score_total=element.confidence,
        score_terms={"element_confidence": element.confidence},
        source_ids=[element.id],
        provenance={"elements": [element.id]},
        orientation=orientation,
        point_ids=[f"{element.id}:p{index}" for index, _ in enumerate(getattr(element.geometry, "points", ()))],
    )


def region_primitive_from_element(element: Element) -> RegionPrimitive:
    return RegionPrimitive(
        id=f"region-primitive:{element.id}",
        kind=element.kind,
        bbox=element.bbox,
        score_total=element.confidence,
        score_terms={"element_confidence": element.confidence},
        source_ids=[element.id],
        provenance={"elements": [element.id]},
        fill_enabled=element.fill.enabled,
    )


def draw_geometry_overlay(
    image: Image.Image,
    rect_candidates: Iterable[RectCandidate],
    connector_candidates: Iterable[ConnectorCandidate],
) -> Image.Image:
    overlay = image.convert("RGB").copy()
    draw = ImageDraw.Draw(overlay)
    for candidate in rect_candidates:
        if candidate.bbox is None:
            continue
        draw.rectangle(
            (
                candidate.bbox.x0,
                candidate.bbox.y0,
                candidate.bbox.x1,
                candidate.bbox.y1,
            ),
            outline=(30, 144, 255),
            width=2,
        )
    for candidate in connector_candidates:
        if candidate.bbox is None:
            continue
        draw.rectangle(
            (
                candidate.bbox.x0,
                candidate.bbox.y0,
                candidate.bbox.x1,
                candidate.bbox.y1,
            ),
            outline=(255, 140, 0),
            width=1,
        )
    return overlay


def clamp_bbox(bbox: BBox, *, width: int, height: int) -> BBox:
    x0 = min(max(0.0, bbox.x0), float(width - 1))
    y0 = min(max(0.0, bbox.y0), float(height - 1))
    x1 = min(max(x0 + 1.0, bbox.x1), float(width))
    y1 = min(max(y0 + 1.0, bbox.y1), float(height))
    return BBox(x0, y0, x1, y1)


def snap_bbox_to_local_contour(
    array: np.ndarray,
    approx_bbox: BBox,
    config: PipelineConfig,
) -> BBox:
    if cv2 is None:
        return approx_bbox
    padding = max(config.local_refine_padding, max(approx_bbox.width, approx_bbox.height) * 0.08)
    crop_bbox = clamp_bbox(approx_bbox.expand(padding), width=array.shape[1], height=array.shape[0])
    x0 = int(math.floor(crop_bbox.x0))
    y0 = int(math.floor(crop_bbox.y0))
    x1 = int(math.ceil(crop_bbox.x1))
    y1 = int(math.ceil(crop_bbox.y1))
    crop = array[y0:y1, x0:x1]
    if crop.size == 0:
        return approx_bbox
    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    sobel_x = cv2.Sobel(blurred, cv2.CV_32F, 1, 0, ksize=3)
    sobel_y = cv2.Sobel(blurred, cv2.CV_32F, 0, 1, ksize=3)
    gradient = cv2.magnitude(sobel_x, sobel_y)
    threshold = max(float(np.percentile(gradient, config.local_refine_gradient_percentile)), float(np.mean(gradient) + config.local_refine_threshold_bias))
    canny = cv2.Canny(blurred, 48, 144)
    binary = np.zeros_like(gray, dtype=np.uint8)
    binary[gradient >= threshold] = 255
    binary = cv2.bitwise_or(binary, canny)
    kernel = np.ones((5, 5), dtype=np.uint8)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return approx_bbox
    target_center = approx_bbox.center
    best_bbox = approx_bbox
    best_score = -1.0
    approx_area = max(approx_bbox.area, 1.0)
    for contour in contours:
        rx, ry, rw, rh = cv2.boundingRect(contour)
        candidate = BBox(x0 + rx, y0 + ry, x0 + rx + rw, y0 + ry + rh)
        if candidate.width < 8 or candidate.height < 8:
            continue
        score = candidate.iou(approx_bbox) * 4.0
        if candidate.contains_point(target_center):
            score += 1.5
        area_ratio = min(candidate.area, approx_area) / max(candidate.area, approx_area)
        score += area_ratio
        if score > best_score:
            best_score = score
            best_bbox = candidate
    if best_score < config.local_refine_min_iou * 4.0:
        return approx_bbox
    return clamp_bbox(best_bbox, width=array.shape[1], height=array.shape[0])


def estimate_local_stroke_width(bbox: BBox) -> float:
    return max(2.0, min(bbox.width, bbox.height) * 0.03)


def estimate_surrounding_background(array: np.ndarray, bbox: BBox) -> tuple[int, int, int]:
    outer = clamp_bbox(bbox.expand(max(6.0, min(bbox.width, bbox.height) * 0.08)), width=array.shape[1], height=array.shape[0])
    x0 = int(math.floor(outer.x0))
    y0 = int(math.floor(outer.y0))
    x1 = int(math.ceil(outer.x1))
    y1 = int(math.ceil(outer.y1))
    ix0 = int(math.floor(bbox.x0))
    iy0 = int(math.floor(bbox.y0))
    ix1 = int(math.ceil(bbox.x1))
    iy1 = int(math.ceil(bbox.y1))
    ring = array[y0:y1, x0:x1].copy()
    ring[iy0 - y0 : iy1 - y0, ix0 - x0 : ix1 - x0] = 0
    mask = np.ones(ring.shape[:2], dtype=bool)
    mask[iy0 - y0 : iy1 - y0, ix0 - x0 : ix1 - x0] = False
    colors = ring[mask]
    if colors.size == 0:
        colors = array.reshape(-1, 3)
    return median_color(colors)


def estimate_corner_radius(array: np.ndarray, bbox: BBox, proposal_type: str) -> float:
    if proposal_type == "cylinder":
        return min(bbox.width, bbox.height) * 0.18
    if proposal_type == "document":
        return 0.0
    stroke_width = estimate_local_stroke_width(bbox)
    sample = max(4, int(round(min(bbox.width, bbox.height) * 0.12)))
    x0 = int(math.floor(bbox.x0))
    y0 = int(math.floor(bbox.y0))
    x1 = int(math.ceil(bbox.x1))
    y1 = int(math.ceil(bbox.y1))
    if x1 - x0 < sample * 2 or y1 - y0 < sample * 2:
        return 0.0
    gray = np.asarray(array[y0:y1, x0:x1].mean(axis=2), dtype=np.float32)
    edge_threshold = np.percentile(gray, 30)
    corners = [gray[:sample, :sample], gray[:sample, -sample:], gray[-sample:, :sample], gray[-sample:, -sample:]]
    dark_ratio = [float((corner <= edge_threshold).mean()) for corner in corners]
    if max(dark_ratio) < 0.18:
        return max(stroke_width * 2.0, min(bbox.width, bbox.height) * 0.08)
    return 0.0


def merge_bboxes(first: BBox, second: BBox) -> BBox:
    return BBox(min(first.x0, second.x0), min(first.y0, second.y0), max(first.x1, second.x1), max(first.y1, second.y1))


def bbox_contains(container: BBox, inner: BBox) -> bool:
    return container.x0 <= inner.x0 and container.y0 <= inner.y0 and container.x1 >= inner.x1 and container.y1 >= inner.y1


def verify_edge_exists(
    image: Image.Image,
    source_bbox: BBox,
    target_bbox: BBox,
    config: PipelineConfig,
    *,
    expect_dashed: bool = False,
) -> bool:
    array = np.asarray(image.convert("RGB"), dtype=np.uint8)
    gray = np.asarray(image.convert("L"), dtype=np.float32)
    background = estimate_image_background(array)
    if cv2 is not None:
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        sobel_x = cv2.Sobel(blurred, cv2.CV_32F, 1, 0, ksize=3)
        sobel_y = cv2.Sobel(blurred, cv2.CV_32F, 0, 1, ksize=3)
        gradient = cv2.magnitude(sobel_x, sobel_y)
    else:
        gradient = np.zeros_like(gray)
    start, end = shortest_anchor_segment(source_bbox, target_bbox)
    if math.hypot(end.x - start.x, end.y - start.y) < 12.0:
        return False
    steps = max(24, int(math.hypot(end.x - start.x, end.y - start.y) / 10.0))
    evidence = 0
    strongest = 0.0
    color_threshold = config.edge_verification_color_distance
    gradient_threshold = max(14.0, float(np.percentile(gradient, 72)))
    for index in range(steps):
        ratio = (index + 0.5) / steps
        point = Point(start.x + (end.x - start.x) * ratio, start.y + (end.y - start.y) * ratio)
        patch = sample_patch(array, point, radius=2)
        patch_gradient = sample_patch(gradient, point, radius=2)
        if patch.size == 0 or patch_gradient.size == 0:
            continue
        mean_gradient = float(np.mean(patch_gradient))
        colors = patch.reshape(-1, 3)
        contrast = float(np.percentile(np.linalg.norm(colors.astype(np.float32) - background[None, :], axis=1), 75))
        strongest = max(strongest, mean_gradient, contrast)
        if mean_gradient >= gradient_threshold or contrast >= color_threshold:
            evidence += 1
    ratio = evidence / max(1, steps)
    required = config.edge_verification_dashed_ratio if expect_dashed else config.edge_verification_min_ratio
    return ratio >= required and strongest >= min(color_threshold, gradient_threshold)


def shortest_anchor_segment(source_bbox: BBox, target_bbox: BBox) -> tuple[Point, Point]:
    source_center = source_bbox.center
    target_center = target_bbox.center
    dx = target_center.x - source_center.x
    dy = target_center.y - source_center.y
    if abs(dx) >= abs(dy):
        return Point(source_bbox.x1 if dx >= 0 else source_bbox.x0, source_center.y), Point(target_bbox.x0 if dx >= 0 else target_bbox.x1, target_center.y)
    return Point(source_center.x, source_bbox.y1 if dy >= 0 else source_bbox.y0), Point(target_center.x, target_bbox.y0 if dy >= 0 else target_bbox.y1)


def estimate_image_background(array: np.ndarray) -> np.ndarray:
    border = np.concatenate([array[0, :, :], array[-1, :, :], array[:, 0, :], array[:, -1, :]], axis=0)
    return np.median(border.astype(np.float32), axis=0)


def sample_patch(array: np.ndarray, point: Point, *, radius: int) -> np.ndarray:
    x = int(round(point.x))
    y = int(round(point.y))
    y0 = max(0, y - radius)
    y1 = min(array.shape[0], y + radius + 1)
    x0 = max(0, x - radius)
    x1 = min(array.shape[1], x + radius + 1)
    return array[y0:y1, x0:x1]
