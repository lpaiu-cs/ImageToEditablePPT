from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Literal

import numpy as np

from .components import Component, find_connected_components
from .config import PipelineConfig
from .ir import BBox, Element
from .preprocess import ProcessedImage, build_boundary_mask

ComponentLabel = Literal["diagram_like", "text_like", "icon_like", "unknown"]
ProposalStrength = Literal["strong", "weak"]


@dataclass(slots=True)
class ComponentFeatures:
    component: Component
    area: int
    width: float
    height: float
    aspect: float
    density: float
    hole_count: int
    branchiness: float
    endpoint_count: int
    continuity: float
    orth_error: float
    long_axis: float
    short_axis: float
    near_structure_count: int
    alignment_score: float = 0.0


@dataclass(slots=True, frozen=True)
class FilteredComponent:
    component: Component
    features: ComponentFeatures
    strength: ProposalStrength = "strong"


@dataclass(slots=True, frozen=True)
class RejectedRegion:
    bbox: BBox
    label: ComponentLabel
    reason: str
    area: int

    def to_dict(self) -> dict[str, object]:
        return {
            "bbox": self.bbox.to_dict(),
            "label": self.label,
            "reason": self.reason,
            "area": self.area,
        }


@dataclass(slots=True)
class FilteringResult:
    diagram_components: list[FilteredComponent]
    weak_components: list[FilteredComponent]
    text_regions: list[BBox]
    rejected_regions: list[RejectedRegion]


def filter_residual_components(
    mask: np.ndarray,
    *,
    processed: ProcessedImage,
    config: PipelineConfig,
    structural_elements: list[Element],
) -> FilteringResult:
    components = find_connected_components(mask)
    features = [extract_features(component, processed, structural_elements) for component in components]
    annotate_alignment(features, processed, config)
    text_indices, text_regions = detect_text_clusters(features, processed, config)
    diagram_components: list[FilteredComponent] = []
    weak_components: list[FilteredComponent] = []
    rejected_regions: list[RejectedRegion] = []
    for index, feature in enumerate(features):
        if index in text_indices:
            rejected_regions.append(
                RejectedRegion(
                    bbox=feature.component.bbox,
                    label="text_like",
                    reason="rejected_as_text_like",
                    area=feature.area,
                )
            )
            continue
        label, reason = classify_component(feature, processed, config)
        if label == "diagram_like":
            diagram_components.append(FilteredComponent(component=feature.component, features=feature, strength="strong"))
            continue
        if label == "unknown" and reason != "rejected_as_too_small":
            weak_components.append(FilteredComponent(component=feature.component, features=feature, strength="weak"))
            continue
        rejected_regions.append(
            RejectedRegion(
                bbox=feature.component.bbox,
                label=label,
                reason=reason,
                area=feature.area,
            )
        )
    return FilteringResult(
        diagram_components=diagram_components,
        weak_components=weak_components,
        text_regions=text_regions,
        rejected_regions=rejected_regions,
    )


def extract_features(
    component: Component,
    processed: ProcessedImage,
    structural_elements: list[Element],
) -> ComponentFeatures:
    local_mask = component_mask(component)
    aspect, orth_error, continuity, long_axis, short_axis = principal_metrics(component.pixels)
    endpoint_count, branchiness = topology_metrics(build_boundary_mask(local_mask))
    return ComponentFeatures(
        component=component,
        area=component.area,
        width=component.width,
        height=component.height,
        aspect=aspect,
        density=component.area / max(1.0, component.bbox.area),
        hole_count=count_holes(local_mask),
        branchiness=branchiness,
        endpoint_count=endpoint_count,
        continuity=continuity,
        orth_error=orth_error,
        long_axis=long_axis,
        short_axis=short_axis,
        near_structure_count=count_structural_neighbors(component.bbox, structural_elements, processed),
    )


def annotate_alignment(
    features: list[ComponentFeatures],
    processed: ProcessedImage,
    config: PipelineConfig,
) -> None:
    spacing_limit = max(
        processed.scale.estimated_stroke_width * 7.0,
        processed.scale.min_stroke_length * 1.1,
    )
    for feature in features:
        score = 0.0
        center = feature.component.bbox.center
        baseline_tolerance = max(
            processed.scale.estimated_stroke_width * 1.8,
            min(feature.height, feature.width) * config.text_baseline_tolerance_ratio,
        )
        for other in features:
            if other is feature:
                continue
            other_center = other.component.bbox.center
            height_ratio = min(feature.height, other.height) / max(1.0, max(feature.height, other.height))
            if height_ratio < 0.55:
                continue
            horizontal_gap = gap_between_boxes(feature.component.bbox, other.component.bbox, axis="x")
            vertical_gap = gap_between_boxes(feature.component.bbox, other.component.bbox, axis="y")
            if abs(center.y - other_center.y) <= baseline_tolerance and 0 <= horizontal_gap <= spacing_limit:
                score += 1.0
            if abs(center.x - other_center.x) <= baseline_tolerance and 0 <= vertical_gap <= spacing_limit:
                score += 0.5
        feature.alignment_score = score


def detect_text_clusters(
    features: list[ComponentFeatures],
    processed: ProcessedImage,
    config: PipelineConfig,
) -> tuple[set[int], list[BBox]]:
    glyph_indices = [
        index
        for index, feature in enumerate(features)
        if looks_glyph_like(feature, processed, config) or looks_text_row_like(feature, processed, config)
    ]
    assigned: set[int] = set()
    accepted: set[int] = set()
    regions: list[BBox] = []
    ordered = sorted(glyph_indices, key=lambda index: (features[index].component.bbox.center.y, features[index].component.bbox.x0))
    for seed_index in ordered:
        if seed_index in assigned:
            continue
        seed = features[seed_index]
        row_candidates = [
            index
            for index in ordered
            if index not in assigned and same_text_row(seed, features[index], processed, config)
        ]
        row_candidates.sort(key=lambda index: features[index].component.bbox.x0)
        for group in split_regular_spacing_groups(row_candidates, features, processed, config):
            if len(group) < config.text_cluster_min_components:
                continue
            bbox = union_bboxes(features[index].component.bbox for index in group).expand(processed.scale.estimated_stroke_width)
            accepted.update(group)
            assigned.update(group)
            regions.append(bbox)
    remaining = [index for index in ordered if index not in accepted]
    for group in split_stacked_text_blocks(remaining, features, processed):
        accepted.update(group)
        assigned.update(group)
        regions.append(union_bboxes(features[index].component.bbox for index in group).expand(processed.scale.estimated_stroke_width))
    return accepted, dedupe_regions(regions)


def classify_component(
    feature: ComponentFeatures,
    processed: ProcessedImage,
    config: PipelineConfig,
) -> tuple[ComponentLabel, str]:
    if feature.area < processed.scale.min_component_area:
        return "unknown", "rejected_as_too_small"
    if feature.long_axis < processed.scale.min_linear_length * 0.55:
        return "unknown", "rejected_as_too_small"
    if looks_icon_like(feature, processed):
        return "icon_like", "rejected_as_icon_like"
    if looks_diagram_like(feature, processed, config):
        return "diagram_like", "accepted_as_diagram_like"
    if feature.near_structure_count == 0 or feature.endpoint_count > 2:
        return "unknown", "rejected_as_low_connectivity"
    return "unknown", "rejected_as_unknown"


def looks_glyph_like(
    feature: ComponentFeatures,
    processed: ProcessedImage,
    config: PipelineConfig,
) -> bool:
    max_height = max(
        processed.scale.estimated_stroke_width * 9.0,
        processed.size[1] * 0.055,
        10.0,
    )
    max_width = max_height * 4.6
    max_area = max(processed.scale.min_component_area * 10, int(round(max_height * max_height * 2.2)))
    return (
        feature.height <= max_height
        and feature.width <= max_width
        and feature.area <= max_area
        and feature.aspect <= 6.5
        and feature.branchiness <= 0.38
        and feature.alignment_score >= 1.0
        and feature.near_structure_count <= 4
        and feature.long_axis < processed.scale.min_linear_length * 0.95
        and feature.density <= 0.84
        and feature.hole_count <= 2
    )


def looks_text_row_like(
    feature: ComponentFeatures,
    processed: ProcessedImage,
    config: PipelineConfig,
) -> bool:
    max_height = max(
        processed.scale.estimated_stroke_width * 9.5,
        processed.size[1] * 0.06,
        12.0,
    )
    max_width = max(processed.scale.min_linear_length * 5.0, max_height * 5.4)
    max_area = max(processed.scale.min_component_area * 32, int(round(max_height * max_width * 0.9)))
    return (
        feature.height <= max_height
        and feature.width <= max_width
        and feature.area <= max_area
        and 2.4 <= feature.aspect <= 12.0
        and 0.28 <= feature.density <= 0.84
        and feature.near_structure_count <= 6
        and feature.long_axis < processed.scale.min_linear_length * 6.0
        and (feature.alignment_score >= 0.5 or feature.hole_count > 0 or feature.branchiness >= 0.18)
    )


def looks_icon_like(feature: ComponentFeatures, processed: ProcessedImage) -> bool:
    compact = feature.aspect < 2.6 and feature.density > 0.18
    decorative = feature.hole_count > 0 or feature.branchiness > 0.11 or feature.endpoint_count == 0
    oversized_blob = feature.density > 0.42 and feature.aspect < 4.0 and feature.near_structure_count == 0
    return (compact and decorative and feature.long_axis < processed.scale.min_linear_length * 1.6) or oversized_blob


def looks_diagram_like(
    feature: ComponentFeatures,
    processed: ProcessedImage,
    config: PipelineConfig,
) -> bool:
    isolated = feature.near_structure_count == 0
    strong_line = (
        feature.aspect >= max(config.min_line_aspect_ratio + 0.8, 4.0)
        and feature.orth_error <= max(config.max_straight_orth_error * 2.2, processed.scale.estimated_stroke_width * 4.0)
        and feature.continuity >= 0.82
        and feature.long_axis >= processed.scale.min_linear_length
        and feature.short_axis <= max(processed.scale.estimated_stroke_width * 8.0, feature.long_axis * 0.33)
    )
    strong_connector = (
        feature.width >= processed.scale.estimated_stroke_width * 3.0
        and feature.height >= processed.scale.estimated_stroke_width * 3.0
        and feature.continuity >= 0.70
        and feature.long_axis >= processed.scale.min_linear_length * 1.15
        and feature.density <= 0.42
        and max(feature.width, feature.height) >= processed.scale.min_linear_length
    )
    if strong_line and (not isolated or feature.long_axis >= processed.scale.min_linear_length * 1.5):
        return True
    if strong_connector and (not isolated or max(feature.width, feature.height) >= processed.scale.min_linear_length * 1.5):
        return True
    return False


def same_text_row(
    first: ComponentFeatures,
    second: ComponentFeatures,
    processed: ProcessedImage,
    config: PipelineConfig,
) -> bool:
    tolerance = max(
        processed.scale.estimated_stroke_width * 2.0,
        min(first.height, second.height) * config.text_baseline_tolerance_ratio,
    )
    height_ratio = min(first.height, second.height) / max(1.0, max(first.height, second.height))
    return abs(first.component.bbox.center.y - second.component.bbox.center.y) <= tolerance and height_ratio >= 0.58


def split_regular_spacing_groups(
    indices: list[int],
    features: list[ComponentFeatures],
    processed: ProcessedImage,
    config: PipelineConfig,
) -> list[list[int]]:
    if not indices:
        return []
    groups: list[list[int]] = []
    current = [indices[0]]
    for previous_index, current_index in zip(indices[:-1], indices[1:], strict=True):
        previous = features[previous_index]
        current_feature = features[current_index]
        median_height = float(np.median([features[index].height for index in current]))
        gap = current_feature.component.bbox.x0 - previous.component.bbox.x1
        spacing_limit = max(
            processed.scale.estimated_stroke_width * 3.0,
            median_height * config.text_spacing_ratio,
        )
        if -processed.scale.estimated_stroke_width <= gap <= spacing_limit:
            current.append(current_index)
            continue
        if has_regular_row_structure(current, features, processed, config):
            groups.append(current)
        current = [current_index]
    if has_regular_row_structure(current, features, processed, config):
        groups.append(current)
    return groups


def has_regular_row_structure(
    indices: list[int],
    features: list[ComponentFeatures],
    processed: ProcessedImage,
    config: PipelineConfig,
) -> bool:
    if len(indices) < config.text_cluster_min_components:
        return False
    heights = np.asarray([features[index].height for index in indices], dtype=np.float32)
    if float(heights.max() / max(1.0, heights.min())) > 1.9:
        return False
    gaps = np.asarray(
        [
            features[right].component.bbox.x0 - features[left].component.bbox.x1
            for left, right in zip(indices[:-1], indices[1:], strict=True)
        ],
        dtype=np.float32,
    )
    if gaps.size == 0:
        return False
    if float(np.max(gaps)) > max(processed.scale.estimated_stroke_width * 4.0, float(np.median(heights)) * config.text_spacing_ratio):
        return False
    return float(np.std(gaps)) <= max(processed.scale.estimated_stroke_width * 2.2, float(np.median(heights)) * 1.1)


def split_stacked_text_blocks(
    indices: list[int],
    features: list[ComponentFeatures],
    processed: ProcessedImage,
) -> list[list[int]]:
    groups: list[list[int]] = []
    used: set[int] = set()
    ordered = sorted(indices, key=lambda index: (features[index].component.bbox.center.x, features[index].component.bbox.y0))
    for seed_index in ordered:
        if seed_index in used:
            continue
        seed = features[seed_index]
        candidates = [seed_index]
        for index in ordered:
            if index == seed_index or index in used:
                continue
            other = features[index]
            width_ratio = min(seed.width, other.width) / max(1.0, max(seed.width, other.width))
            if width_ratio < 0.45:
                continue
            x_tolerance = max(processed.scale.estimated_stroke_width * 4.0, min(seed.width, other.width) * 0.35)
            if abs(seed.component.bbox.center.x - other.component.bbox.center.x) > x_tolerance:
                continue
            vertical_gap = gap_between_boxes(seed.component.bbox, other.component.bbox, axis="y")
            if 0 <= vertical_gap <= max(seed.height, other.height) * 2.6:
                candidates.append(index)
        candidates = sorted(set(candidates), key=lambda index: features[index].component.bbox.y0)
        if len(candidates) < 2 or not has_regular_vertical_structure(candidates, features, processed):
            continue
        groups.append(candidates)
        used.update(candidates)
    return groups


def has_regular_vertical_structure(
    indices: list[int],
    features: list[ComponentFeatures],
    processed: ProcessedImage,
) -> bool:
    heights = np.asarray([features[index].height for index in indices], dtype=np.float32)
    if float(heights.max() / max(1.0, heights.min())) > 2.0:
        return False
    gaps = np.asarray(
        [
            features[bottom].component.bbox.y0 - features[top].component.bbox.y1
            for top, bottom in zip(indices[:-1], indices[1:], strict=True)
        ],
        dtype=np.float32,
    )
    if gaps.size == 0:
        return False
    return float(np.max(gaps)) <= max(processed.scale.estimated_stroke_width * 5.0, float(np.median(heights)) * 2.6)


def count_structural_neighbors(
    bbox: BBox,
    structural_elements: list[Element],
    processed: ProcessedImage,
) -> int:
    margin = max(processed.scale.estimated_stroke_width * 3.0, processed.scale.min_stroke_length * 0.35)
    return sum(1 for element in structural_elements if element.bbox.expand(margin).overlaps(bbox))


def principal_metrics(pixels: np.ndarray) -> tuple[float, float, float, float, float]:
    points = np.column_stack((pixels[:, 1].astype(np.float32), pixels[:, 0].astype(np.float32)))
    if len(points) < 2:
        return 1.0, 0.0, 0.0, 1.0, 1.0
    centroid = points.mean(axis=0)
    centered = points - centroid
    covariance = np.cov(centered, rowvar=False)
    eigvals, eigvecs = np.linalg.eigh(covariance)
    major = eigvecs[:, int(np.argmax(eigvals))]
    minor = np.array([-major[1], major[0]], dtype=np.float32)
    major_proj = centered @ major
    minor_proj = centered @ minor
    long_axis = float(major_proj.max() - major_proj.min() + 1.0)
    short_axis = max(1.0, float(np.percentile(np.abs(minor_proj), 80) * 2.0 + 1.0))
    aspect = long_axis / short_axis
    orth_error = float(np.sqrt(np.mean(minor_proj**2)))
    bins = np.linspace(major_proj.min(), major_proj.max(), num=12)
    occupancy = []
    for start, end in zip(bins[:-1], bins[1:], strict=True):
        band = (major_proj >= start) & (major_proj <= end)
        occupancy.append(1.0 if band.any() else 0.0)
    continuity = float(np.mean(occupancy)) if occupancy else 0.0
    return aspect, orth_error, continuity, long_axis, short_axis


def topology_metrics(mask: np.ndarray) -> tuple[int, float]:
    height, width = mask.shape
    degrees: list[int] = []
    for y in range(height):
        for x in range(width):
            if not mask[y, x]:
                continue
            degree = 0
            for ny in range(max(0, y - 1), min(height, y + 2)):
                for nx in range(max(0, x - 1), min(width, x + 2)):
                    if (ny != y or nx != x) and mask[ny, nx]:
                        degree += 1
            degrees.append(degree)
    if not degrees:
        return 0, 0.0
    endpoint_count = sum(1 for degree in degrees if degree <= 1)
    branchiness = sum(1 for degree in degrees if degree >= 3) / len(degrees)
    return endpoint_count, float(branchiness)


def count_holes(mask: np.ndarray) -> int:
    background = ~mask
    components = find_connected_components(background)
    height, width = mask.shape
    holes = 0
    for component in components:
        if component.bbox.x0 <= 0 or component.bbox.y0 <= 0:
            continue
        if component.bbox.x1 >= width or component.bbox.y1 >= height:
            continue
        holes += 1
    return holes


def component_mask(component: Component) -> np.ndarray:
    width = max(1, int(math.ceil(component.bbox.width)))
    height = max(1, int(math.ceil(component.bbox.height)))
    mask = np.zeros((height, width), dtype=bool)
    xs = component.pixels[:, 1] - int(math.floor(component.bbox.x0))
    ys = component.pixels[:, 0] - int(math.floor(component.bbox.y0))
    mask[ys, xs] = True
    return mask


def gap_between_boxes(first: BBox, second: BBox, *, axis: str) -> float:
    if axis == "x":
        if second.x0 >= first.x1:
            return second.x0 - first.x1
        if first.x0 >= second.x1:
            return first.x0 - second.x1
        return 0.0
    if second.y0 >= first.y1:
        return second.y0 - first.y1
    if first.y0 >= second.y1:
        return first.y0 - second.y1
    return 0.0


def union_bboxes(boxes) -> BBox:
    iterator = iter(boxes)
    first = next(iterator)
    x0 = first.x0
    y0 = first.y0
    x1 = first.x1
    y1 = first.y1
    for bbox in iterator:
        x0 = min(x0, bbox.x0)
        y0 = min(y0, bbox.y0)
        x1 = max(x1, bbox.x1)
        y1 = max(y1, bbox.y1)
    return BBox(x0, y0, x1, y1)


def dedupe_regions(regions: list[BBox]) -> list[BBox]:
    deduped: list[BBox] = []
    for region in sorted(regions, key=lambda bbox: bbox.area, reverse=True):
        if any(region.iou(existing) >= 0.7 for existing in deduped):
            continue
        deduped.append(region)
    return deduped
