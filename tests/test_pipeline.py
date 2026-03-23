from __future__ import annotations

from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET
import json

from pptx import Presentation
import pytest

from image_to_editable_ppt.config import PipelineConfig
from image_to_editable_ppt.exporter import export_to_pptx
from image_to_editable_ppt.ir import BBox, Element, FillStyle, Point, PolylineGeometry, StrokeStyle
from image_to_editable_ppt.pipeline import build_elements, convert_image
from image_to_editable_ppt.text import OCRBackend, OCRTextRegion
from image_to_editable_ppt.validation import run_validation_iteration
from tests.synthetic import (
    boxed_text_cluster_diagram,
    complex_diagram,
    directional_arrow,
    icon_only,
    occluded_box,
    open_contour,
    paper_like_directional_arrow,
    paper_like_dense_text_diagram,
    paper_like_insufficient_widening,
    paper_like_mixed_arrow_with_connector,
    paper_like_mixed_figure,
    paper_like_multisegment_connector,
    paper_like_noisy_line_ending,
    paper_like_noisy_open_contour,
    paper_like_occluded_box,
    paper_like_symmetric_wedge,
    paper_like_weak_gap_conflict,
    save_image,
    text_box_diagram,
)


class FakeOCRBackend(OCRBackend):
    def __init__(self, regions: list[OCRTextRegion]) -> None:
        self._regions = regions

    def extract(self, image):
        return self._regions


class CropAwareOCRBackend(OCRBackend):
    def __init__(self) -> None:
        self.calls: list[tuple[int, int]] = []

    def extract(self, image):
        self.calls.append(image.size)
        if image.size[0] >= 260:
            return []
        return [
            OCRTextRegion(
                text="Encoder Stage",
                bbox=BBox(8.0, 6.0, min(140.0, image.size[0] - 4.0), min(34.0, image.size[1] - 4.0)),
                confidence=0.97,
            )
        ]


XML_NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
}


def assert_arrow_tip_points_to_direction(element: Element, direction: str) -> None:
    start, end = element.geometry.points
    if direction == "right":
        assert end.x > start.x
        return
    if direction == "left":
        assert end.x < start.x
        return
    if direction == "up":
        assert end.y < start.y
        return
    if direction == "down":
        assert end.y > start.y
        return
    raise ValueError(f"unsupported direction: {direction}")


def assert_slide_connector_uses_tail_end_only(output_path: Path, *, expected_tail_count: int = 1) -> None:
    with zipfile.ZipFile(output_path) as archive:
        slide_xml = ET.fromstring(archive.read("ppt/slides/slide1.xml"))
    assert len(slide_xml.findall(".//a:tailEnd", XML_NS)) == expected_tail_count
    assert slide_xml.findall(".//a:headEnd", XML_NS) == []


def test_acceptance_pipeline_detects_core_primitives_and_exports(tmp_path: Path) -> None:
    image_path = save_image(complex_diagram(), tmp_path / "diagram.png")
    output_path = tmp_path / "diagram.pptx"
    result = convert_image(image_path, output_path, config=PipelineConfig())

    kinds = {element.kind for element in result.elements}
    assert "rect" in kinds
    assert "rounded_rect" in kinds
    assert "line" in kinds
    assert "orthogonal_connector" in kinds
    assert "arrow" in kinds
    assert output_path.exists()

    presentation = Presentation(str(output_path))
    slide = presentation.slides[0]
    assert len(slide.shapes) >= len(result.elements)
    for element in result.elements:
        if element.kind in {"rect", "rounded_rect"}:
            if element.fill.enabled:
                assert element.fill.color is not None
        else:
            assert not element.fill.enabled


def test_occlusion_repair_reconstructs_box_with_inferred_flag() -> None:
    result = build_elements(occluded_box(), config=PipelineConfig())
    boxes = [element for element in result.elements if element.kind in {"rect", "rounded_rect"}]
    assert len(boxes) == 1
    assert boxes[0].inferred


def test_open_contour_never_receives_fill() -> None:
    result = build_elements(open_contour(), config=PipelineConfig())
    filled_boxes = [
        element
        for element in result.elements
        if element.kind in {"rect", "rounded_rect"} and element.fill.enabled
    ]
    assert filled_boxes == []


def test_non_diagram_icon_is_omitted() -> None:
    result = build_elements(icon_only(), config=PipelineConfig())
    assert result.elements == []


def test_text_is_only_included_when_high_confidence_and_structural() -> None:
    backend = FakeOCRBackend(
        [
            OCRTextRegion(text="Encoder", bbox=BBox(60.0, 65.0, 150.0, 95.0), confidence=0.97),
            OCRTextRegion(text="noise", bbox=BBox(10.0, 10.0, 30.0, 20.0), confidence=0.98),
            OCRTextRegion(text="low", bbox=BBox(70.0, 70.0, 120.0, 90.0), confidence=0.40),
        ]
    )
    result = build_elements(text_box_diagram(), config=PipelineConfig(), ocr_backend=backend)
    texts = [element for element in result.elements if element.kind == "text"]
    assert len(texts) == 1
    assert texts[0].text is not None
    assert texts[0].text.content == "Encoder"


def test_ocr_routes_text_like_clusters_to_candidate_crops() -> None:
    backend = CropAwareOCRBackend()
    result = build_elements(boxed_text_cluster_diagram(), config=PipelineConfig(), ocr_backend=backend)
    texts = [element for element in result.elements if element.kind == "text"]
    assert texts
    assert texts[0].text is not None
    assert texts[0].text.content == "Encoder Stage"
    assert any(size[0] < 260 for size in backend.calls)


def test_realistic_occluded_box_is_repaired_only_when_evidence_is_strong() -> None:
    result = build_elements(paper_like_occluded_box(), config=PipelineConfig())
    inferred_boxes = [
        element
        for element in result.elements
        if element.kind in {"rect", "rounded_rect"} and element.inferred
    ]
    assert len(inferred_boxes) == 1
    assert inferred_boxes[0].fill.enabled


def test_weak_geometry_with_conflict_does_not_trigger_repair() -> None:
    result = build_elements(paper_like_weak_gap_conflict(), config=PipelineConfig())
    lines = [element for element in result.elements if element.kind == "line"]
    assert lines
    assert all(not element.inferred for element in lines)
    assert max(element.bbox.width for element in lines) < 110


def test_multisegment_orthogonal_connector_is_detected_conservatively() -> None:
    result = build_elements(paper_like_multisegment_connector(), config=PipelineConfig())
    connectors = [element for element in result.elements if element.kind == "orthogonal_connector"]
    assert connectors
    assert any(len(element.geometry.points) >= 4 for element in connectors)


@pytest.mark.parametrize("direction", ["right", "left", "up", "down"])
def test_arrow_detection_orders_points_toward_tip(direction: str) -> None:
    result = build_elements(directional_arrow(direction), config=PipelineConfig())
    arrows = [element for element in result.elements if element.kind == "arrow"]
    assert len(arrows) == 1
    assert_arrow_tip_points_to_direction(arrows[0], direction)


def test_mixed_figure_omits_non_diagram_region() -> None:
    result = build_elements(paper_like_mixed_figure(), config=PipelineConfig())
    assert any(element.kind in {"rect", "line"} for element in result.elements)
    assert all(element.bbox.center.x < 185 for element in result.elements)


def test_no_fill_on_open_contour_under_noise() -> None:
    result = build_elements(paper_like_noisy_open_contour(), config=PipelineConfig())
    assert not any(
        element.kind in {"rect", "rounded_rect"} and element.fill.enabled
        for element in result.elements
    )


def test_dense_text_heavy_diagram_suppresses_text_fragments_with_ocr_off() -> None:
    result = build_elements(paper_like_dense_text_diagram(), config=PipelineConfig())
    large_boxes = [
        element
        for element in result.elements
        if element.kind in {"rect", "rounded_rect"} and element.bbox.width > 260 and element.bbox.height > 150
    ]
    long_connectors = [
        element
        for element in result.elements
        if element.kind in {"line", "orthogonal_connector", "arrow"} and max(element.bbox.width, element.bbox.height) > 150
    ]
    tiny_primitives = [
        element
        for element in result.elements
        if element.kind in {"rect", "rounded_rect", "line", "orthogonal_connector", "arrow"}
        and max(element.bbox.width, element.bbox.height) < 60
    ]
    assert len(large_boxes) >= 2
    assert long_connectors
    assert tiny_primitives == []
    assert not any(element.kind == "text" for element in result.elements)
    assert len(result.elements) <= 8
    assert any(region.reason == "rejected_as_text_like" for region in result.rejected_regions)


def test_arrow_exporter_unit_maps_tip_to_ooxml_tail_end(tmp_path: Path) -> None:
    output_path = tmp_path / "arrow.pptx"
    export_to_pptx(
        [
            Element(
                id="arrow-1",
                kind="arrow",
                geometry=PolylineGeometry(points=(Point(20.0, 40.0), Point(180.0, 40.0))),
                stroke=StrokeStyle(color=(0, 0, 0), width=4.0),
                fill=FillStyle(enabled=False, color=None),
                text=None,
                confidence=0.95,
                source_region=BBox(20.0, 34.0, 180.0, 46.0),
            )
        ],
        (200, 80),
        output_path,
        PipelineConfig(),
    )
    assert_slide_connector_uses_tail_end_only(output_path)


@pytest.mark.parametrize("direction", ["right", "left", "up", "down"])
def test_arrow_convert_image_exports_tip_to_ooxml_tail_end(
    tmp_path: Path,
    direction: str,
) -> None:
    image_path = save_image(directional_arrow(direction), tmp_path / f"{direction}-arrow.png")
    output_path = tmp_path / f"{direction}-arrow.pptx"
    result = convert_image(image_path, output_path, config=PipelineConfig())
    arrows = [element for element in result.elements if element.kind == "arrow"]
    assert len(arrows) == 1
    assert_arrow_tip_points_to_direction(arrows[0], direction)
    assert_slide_connector_uses_tail_end_only(output_path)


@pytest.mark.parametrize("direction", ["right", "left", "up", "down"])
def test_paper_like_arrow_convert_image_exports_tip_to_ooxml_tail_end(
    tmp_path: Path,
    direction: str,
) -> None:
    image_path = save_image(paper_like_directional_arrow(direction), tmp_path / f"paper-like-{direction}-arrow.png")
    output_path = tmp_path / f"paper-like-{direction}-arrow.pptx"
    result = convert_image(image_path, output_path, config=PipelineConfig())
    arrows = [element for element in result.elements if element.kind == "arrow"]
    assert len(arrows) == 1
    assert_arrow_tip_points_to_direction(arrows[0], direction)
    assert_slide_connector_uses_tail_end_only(output_path)


def test_paper_like_insufficient_widening_degrades_to_line(tmp_path: Path) -> None:
    image_path = save_image(paper_like_insufficient_widening(), tmp_path / "insufficient-widening.png")
    output_path = tmp_path / "insufficient-widening.pptx"
    result = convert_image(image_path, output_path, config=PipelineConfig())
    arrows = [element for element in result.elements if element.kind == "arrow"]
    lines = [element for element in result.elements if element.kind == "line"]
    assert arrows == []
    assert lines
    assert_slide_connector_uses_tail_end_only(output_path, expected_tail_count=0)


def test_paper_like_symmetric_wedge_is_omitted(tmp_path: Path) -> None:
    image_path = save_image(paper_like_symmetric_wedge(), tmp_path / "symmetric-wedge.png")
    output_path = tmp_path / "symmetric-wedge.pptx"
    result = convert_image(image_path, output_path, config=PipelineConfig())
    assert result.elements == []
    assert_slide_connector_uses_tail_end_only(output_path, expected_tail_count=0)


def test_paper_like_noisy_line_ending_is_not_exported_as_arrow(tmp_path: Path) -> None:
    image_path = save_image(paper_like_noisy_line_ending(), tmp_path / "noisy-line-ending.png")
    output_path = tmp_path / "noisy-line-ending.pptx"
    result = convert_image(image_path, output_path, config=PipelineConfig())
    arrows = [element for element in result.elements if element.kind == "arrow"]
    lines = [element for element in result.elements if element.kind == "line"]
    assert arrows == []
    assert lines
    assert_slide_connector_uses_tail_end_only(output_path, expected_tail_count=0)


def test_paper_like_mixed_arrow_exports_single_tail_end_marker(tmp_path: Path) -> None:
    image_path = save_image(paper_like_mixed_arrow_with_connector(), tmp_path / "mixed-arrow.png")
    output_path = tmp_path / "mixed-arrow.pptx"
    result = convert_image(image_path, output_path, config=PipelineConfig())
    arrows = [element for element in result.elements if element.kind == "arrow"]
    other_linear = [
        element
        for element in result.elements
        if element.kind in {"line", "orthogonal_connector"}
    ]
    assert len(arrows) == 1
    assert_arrow_tip_points_to_direction(arrows[0], "right")
    assert other_linear
    assert_slide_connector_uses_tail_end_only(output_path)


def test_convert_image_debug_dump_serializes_slot_dataclasses(tmp_path: Path) -> None:
    image_path = save_image(complex_diagram(), tmp_path / "debug-diagram.png")
    output_path = tmp_path / "debug-diagram.pptx"
    debug_path = tmp_path / "debug-elements.json"
    convert_image(image_path, output_path, config=PipelineConfig(), debug_elements_path=debug_path)
    assert debug_path.exists()
    rejection_path = tmp_path / "debug-elements.rejections.json"
    assert rejection_path.exists()
    with debug_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    assert isinstance(data, list)
    assert data
    assert "geometry" in data[0]


def test_validation_iteration_exports_pptx_svg_and_comparison_artifacts(tmp_path: Path) -> None:
    image_path = save_image(complex_diagram(), tmp_path / "validate-diagram.png")
    run = run_validation_iteration(image_path, tmp_path / "iter", config=PipelineConfig())
    assert run.artifacts.output_pptx.exists()
    assert run.artifacts.output_svg.exists()
    assert run.artifacts.rendered_png.exists()
    assert run.artifacts.overlay_png.exists()
    assert run.artifacts.edge_diff_png.exists()
    assert run.artifacts.metrics_json.exists()
    assert run.metrics.rendered_shape_count >= 4
    svg_text = run.artifacts.output_svg.read_text(encoding="utf-8")
    assert "<svg" in svg_text
