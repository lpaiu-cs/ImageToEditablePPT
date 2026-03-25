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
from .filtering import RejectedRegion
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


@dataclass(slots=True, frozen=True)
class DecompositionSeed:
    id: str
    bbox: BBox
    kind: str


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
    rect_candidates.extend(
        build_text_seed_rect_candidates(
            image,
            observations.detection.text_regions,
            rect_candidates,
            config,
        )
    )
    decomposed_candidates = build_parent_decomposition_rect_candidates(
            image,
            boundary_mask=observations.processed.boundary_mask_raw,
            text_regions=observations.detection.text_regions,
            rejected_regions=observations.detection.rejected_regions,
            existing_candidates=rect_candidates,
            config=config,
        )
    rect_candidates.extend(decomposed_candidates)
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
                "decomposed_rect_candidate_count": len(decomposed_candidates),
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


def build_text_seed_rect_candidates(
    image: Image.Image,
    text_regions: list[BBox],
    existing_candidates: list[RectCandidate],
    config: PipelineConfig,
) -> list[RectCandidate]:
    if not text_regions:
        return []
    from .fallback import grow_container_from_text_anchor

    array = np.asarray(image.convert("RGB"), dtype=np.uint8)
    candidates: list[RectCandidate] = []
    for index, region in enumerate(text_regions, start=1):
        if region.width < 32.0 or region.height < 10.0:
            continue
        hint_padding = max(config.text_margin * 2.5, region.height * 2.2, region.width * 0.32)
        hint_bbox = clamp_bbox(region.expand(hint_padding), width=array.shape[1], height=array.shape[0])
        candidate_bbox = grow_container_from_text_anchor(array, region, hint_bbox, config)
        if candidate_bbox.width < max(32.0, config.min_box_size) or candidate_bbox.height < max(24.0, config.min_box_size):
            continue
        if candidate_bbox.area <= region.area * 1.35:
            continue
        if any(candidate.bbox is not None and candidate_bbox.iou(candidate.bbox) >= 0.84 for candidate in [*existing_candidates, *candidates]):
            continue
        area_ratio = candidate_bbox.area / max(region.area, 1.0)
        candidates.append(
            RectCandidate(
                id=f"rect-candidate:text-seed-{index:03d}",
                kind="rect",
                bbox=candidate_bbox,
                score_total=min(0.82, 0.48 + min(0.28, math.log1p(area_ratio) * 0.11)),
                score_terms={
                    "text_seed": 1.0,
                    "area_ratio": round(area_ratio, 4),
                },
                source_ids=[f"text-region:{index:03d}"],
                provenance={"text_region_ids": [f"text-region:{index:03d}"]},
                object_type="container",
            )
        )
    return candidates


def build_parent_decomposition_rect_candidates(
    image: Image.Image,
    *,
    boundary_mask: np.ndarray | None,
    text_regions: list[BBox],
    rejected_regions: list[RejectedRegion],
    existing_candidates: list[RectCandidate],
    config: PipelineConfig,
) -> list[RectCandidate]:
    if not existing_candidates:
        return []

    image_area = float(max(1, image.size[0] * image.size[1]))
    if boundary_mask is None:
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
        active_boundary_mask = processed.boundary_mask_raw
    else:
        active_boundary_mask = boundary_mask
    clustered_text_seeds = [
        *[DecompositionSeed(id=f"text-region:{index:03d}", bbox=region, kind="text_region") for index, region in enumerate(text_regions, start=1)],
        *cluster_text_like_seeds(rejected_regions),
    ]
    candidates: list[RectCandidate] = []
    parents = sorted(
        [
            candidate
            for candidate in existing_candidates
            if candidate.bbox is not None
            and candidate.bbox.area >= max(image_area * 0.035, float(config.min_box_size * config.min_box_size * 18))
        ],
        key=lambda candidate: candidate.bbox.area if candidate.bbox is not None else 0.0,
        reverse=True,
    )[:6]
    for parent_index, parent in enumerate(parents, start=1):
        if parent.bbox is None:
            continue
        seed_pool = collect_parent_decomposition_seeds(parent, existing_candidates, clustered_text_seeds)
        if len(seed_pool) < 2 or not has_aligned_seed_pair(seed_pool, parent.bbox):
            continue
        for seed_index, seed in enumerate(seed_pool, start=1):
            candidate_bbox = decompose_candidate_from_seed(active_boundary_mask, parent.bbox, seed.bbox, config)
            if candidate_bbox is None:
                continue
            seed_count_inside = sum(1 for other in seed_pool if candidate_bbox.contains_point(other.bbox.center))
            if not decomposition_candidate_is_useful(
                candidate_bbox,
                seed=seed,
                parent=parent,
                existing_candidates=[*existing_candidates, *candidates],
                seed_count_inside=seed_count_inside,
                config=config,
            ):
                continue
            candidates.append(
                RectCandidate(
                    id=f"rect-candidate:decompose-{parent_index:02d}-{seed_index:02d}",
                    kind="rounded_rect" if parent.kind == "rounded_rect" else "rect",
                    bbox=candidate_bbox,
                    score_total=min(0.81, parent.score_total * 0.82 + 0.06),
                    score_terms={
                        "decomposed_parent": 1.0,
                        "parent_confidence": round(parent.score_total, 4),
                        "seed_count_inside": float(seed_count_inside),
                    },
                    source_ids=[parent.id, seed.id],
                    provenance={"parent_candidate_ids": [parent.id], "seed_ids": [seed.id]},
                    object_type="container",
                    corner_radius=parent.corner_radius if parent.kind == "rounded_rect" else 0.0,
                )
            )
    return candidates


def cluster_text_like_seeds(rejected_regions: list[RejectedRegion]) -> list[DecompositionSeed]:
    regions = [
        region.bbox
        for region in rejected_regions
        if region.label == "text_like" and region.area >= 10
    ]
    if not regions:
        return []
    ordered = sorted(regions, key=lambda bbox: (bbox.center.y, bbox.x0))
    groups: list[list[BBox]] = []
    for bbox in ordered:
        if not groups:
            groups.append([bbox])
            continue
        last_group = groups[-1]
        reference = last_group[-1]
        same_row = abs(reference.center.y - bbox.center.y) <= max(18.0, min(reference.height, bbox.height) * 2.5)
        near_x = bbox.x0 - reference.x1 <= max(42.0, max(reference.width, bbox.width) * 3.5)
        if same_row and near_x:
            last_group.append(bbox)
        else:
            groups.append([bbox])
    seeds: list[DecompositionSeed] = []
    for index, group in enumerate(groups, start=1):
        merged = group[0]
        for bbox in group[1:]:
            merged = merge_bboxes(merged, bbox)
        if merged.width < 6.0 or merged.height < 3.0:
            continue
        seeds.append(DecompositionSeed(id=f"text-cluster:{index:03d}", bbox=merged.expand(4.0), kind="text_cluster"))
    return seeds


def collect_parent_decomposition_seeds(
    parent: RectCandidate,
    existing_candidates: list[RectCandidate],
    text_seeds: list[DecompositionSeed],
) -> list[DecompositionSeed]:
    if parent.bbox is None:
        return []
    parent_bbox = parent.bbox.inset(4.0)
    seeds: list[DecompositionSeed] = []
    for candidate in existing_candidates:
        if candidate.id == parent.id or candidate.bbox is None:
            continue
        if not bbox_contains(parent_bbox, candidate.bbox):
            continue
        if candidate.bbox.area >= parent_bbox.area * 0.72:
            continue
        if candidate.bbox.area <= parent_bbox.area * 0.015:
            continue
        seeds.append(DecompositionSeed(id=candidate.id, bbox=candidate.bbox, kind="candidate"))
    for seed in text_seeds:
        if bbox_contains(parent_bbox, seed.bbox):
            seeds.append(seed)
    deduped: list[DecompositionSeed] = []
    for seed in seeds:
        if any(seed.bbox.iou(existing.bbox) >= 0.88 for existing in deduped):
            continue
        deduped.append(seed)
    deduped.sort(key=lambda seed: (0 if seed.kind != "candidate" else 1, seed.bbox.area, seed.id))
    return deduped[:8]


def has_aligned_seed_pair(seeds: list[DecompositionSeed], parent_bbox: BBox) -> bool:
    row_tolerance = max(26.0, parent_bbox.height * 0.12)
    column_tolerance = max(26.0, parent_bbox.width * 0.12)
    for index, seed in enumerate(seeds):
        for other in seeds[index + 1 :]:
            if abs(seed.bbox.center.y - other.bbox.center.y) <= row_tolerance:
                return True
            if abs(seed.bbox.center.x - other.bbox.center.x) <= column_tolerance:
                return True
    return False


def decomposition_hint_bbox(
    seed_bbox: BBox,
    parent_bbox: BBox,
    *,
    width: int,
    height: int,
    config: PipelineConfig,
) -> BBox:
    padding = max(config.text_margin * 2.0, seed_bbox.height * 2.2, seed_bbox.width * 0.6)
    return clamp_bbox(
        intersect_bboxes(clamp_bbox(seed_bbox.expand(padding), width=width, height=height), parent_bbox.inset(1.0)) or parent_bbox,
        width=width,
        height=height,
    )


def decompose_candidate_from_seed(
    boundary_mask: np.ndarray,
    parent_bbox: BBox,
    seed_bbox: BBox,
    config: PipelineConfig,
) -> BBox | None:
    search_y0 = max(int(parent_bbox.y0) + 1, int(math.floor(seed_bbox.y0 - max(26.0, seed_bbox.height * 2.8))))
    search_y1 = min(int(parent_bbox.y1) - 1, int(math.ceil(seed_bbox.y1 + max(26.0, seed_bbox.height * 2.8))))
    search_x0 = max(int(parent_bbox.x0) + 1, int(math.floor(seed_bbox.x0 - max(26.0, seed_bbox.width * 0.9))))
    search_x1 = min(int(parent_bbox.x1) - 1, int(math.ceil(seed_bbox.x1 + max(26.0, seed_bbox.width * 0.9))))
    left = find_supported_boundary_x(
        boundary_mask,
        start=int(math.floor(seed_bbox.x0 - max(6.0, seed_bbox.width * 0.18))),
        stop=int(parent_bbox.x0),
        step=-1,
        y0=search_y0,
        y1=search_y1,
    )
    right = find_supported_boundary_x(
        boundary_mask,
        start=int(math.ceil(seed_bbox.x1 + max(6.0, seed_bbox.width * 0.18))),
        stop=int(parent_bbox.x1),
        step=1,
        y0=search_y0,
        y1=search_y1,
    )
    top = find_supported_boundary_y(
        boundary_mask,
        start=int(math.floor(seed_bbox.y0 - max(5.0, seed_bbox.height * 0.3))),
        stop=int(parent_bbox.y0),
        step=-1,
        x0=search_x0,
        x1=search_x1,
    )
    bottom = find_supported_boundary_y(
        boundary_mask,
        start=int(math.ceil(seed_bbox.y1 + max(5.0, seed_bbox.height * 0.3))),
        stop=int(parent_bbox.y1),
        step=1,
        x0=search_x0,
        x1=search_x1,
    )
    if left is None or right is None or top is None or bottom is None:
        return None
    candidate = BBox(left, top, right, bottom)
    if candidate.width <= seed_bbox.width * 1.1 or candidate.height <= seed_bbox.height * 1.35:
        return None
    if not bbox_contains(parent_bbox.expand(1.0), candidate):
        return None
    if not candidate.contains_point(seed_bbox.center):
        return None
    return candidate


def find_supported_boundary_x(
    boundary_mask: np.ndarray,
    *,
    start: int,
    stop: int,
    step: int,
    y0: int,
    y1: int,
    threshold: float = 0.18,
) -> float | None:
    hits: list[int] = []
    for x in range(start, stop, step):
        if support_ratio_x(boundary_mask, x, y0, y1) >= threshold:
            hits.append(x)
            if len(hits) >= 2:
                return sum(hits) / len(hits)
        elif hits:
            return sum(hits) / len(hits)
    if not hits:
        return None
    return sum(hits) / len(hits)


def find_supported_boundary_y(
    boundary_mask: np.ndarray,
    *,
    start: int,
    stop: int,
    step: int,
    x0: int,
    x1: int,
    threshold: float = 0.18,
) -> float | None:
    hits: list[int] = []
    for y in range(start, stop, step):
        if support_ratio_y(boundary_mask, y, x0, x1) >= threshold:
            hits.append(y)
            if len(hits) >= 2:
                return sum(hits) / len(hits)
        elif hits:
            return sum(hits) / len(hits)
    if not hits:
        return None
    return sum(hits) / len(hits)


def support_ratio_x(boundary_mask: np.ndarray, x: int, y0: int, y1: int) -> float:
    x0 = max(0, x - 1)
    x1 = min(boundary_mask.shape[1], x + 2)
    return float(boundary_mask[y0:y1, x0:x1].mean())


def support_ratio_y(boundary_mask: np.ndarray, y: int, x0: int, x1: int) -> float:
    y0 = max(0, y - 1)
    y1 = min(boundary_mask.shape[0], y + 2)
    return float(boundary_mask[y0:y1, x0:x1].mean())


def decomposition_candidate_is_useful(
    bbox: BBox,
    *,
    seed: DecompositionSeed,
    parent: RectCandidate,
    existing_candidates: list[RectCandidate],
    seed_count_inside: int,
    config: PipelineConfig,
) -> bool:
    if parent.bbox is None:
        return False
    if bbox.area >= parent.bbox.area * 0.84:
        return False
    if bbox.area <= seed.bbox.area * 1.12:
        return False
    if bbox.width < max(26.0, config.min_box_size) or bbox.height < max(20.0, config.min_box_size * 0.75):
        return False
    if seed_count_inside > 1 and bbox.area >= parent.bbox.area * 0.42:
        return False
    for candidate in existing_candidates:
        if candidate.bbox is None:
            continue
        if bbox.iou(candidate.bbox) >= 0.82:
            return False
    return True


def intersect_bboxes(first: BBox, second: BBox) -> BBox | None:
    x0 = max(first.x0, second.x0)
    y0 = max(first.y0, second.y0)
    x1 = min(first.x1, second.x1)
    y1 = min(first.y1, second.y1)
    if x1 <= x0 or y1 <= y0:
        return None
    return BBox(x0, y0, x1, y1)


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
