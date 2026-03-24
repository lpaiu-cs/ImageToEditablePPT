from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from PIL import Image, ImageDraw

from .config import PipelineConfig
from .detector import DetectionResult, detect_elements_with_metadata, verify_edge_exists
from .diagnostics import DiagnosticsRecorder
from .ir import Element
from .preprocess import ProcessedImage, preprocess_image
from .schema import ConnectorCandidate, CornerPrimitive, LinePrimitive, RectCandidate, RegionPrimitive


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
