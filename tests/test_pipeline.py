from __future__ import annotations

from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET

from pptx import Presentation

from image_to_editable_ppt.config import PipelineConfig
from image_to_editable_ppt.exporter import export_to_pptx
from image_to_editable_ppt.ir import BBox, Element, FillStyle, Point, PolylineGeometry, StrokeStyle
from image_to_editable_ppt.pipeline import build_elements, convert_image
from image_to_editable_ppt.text import OCRBackend, OCRTextRegion
from tests.synthetic import (
    complex_diagram,
    icon_only,
    occluded_box,
    open_contour,
    paper_like_mixed_figure,
    paper_like_multisegment_connector,
    paper_like_noisy_open_contour,
    paper_like_occluded_box,
    paper_like_weak_gap_conflict,
    save_image,
    text_box_diagram,
)


class FakeOCRBackend(OCRBackend):
    def __init__(self, regions: list[OCRTextRegion]) -> None:
        self._regions = regions

    def extract(self, image):
        return self._regions


XML_NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
}


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


def test_arrow_detection_orders_points_toward_tip() -> None:
    result = build_elements(complex_diagram(), config=PipelineConfig())
    arrows = [element for element in result.elements if element.kind == "arrow"]
    assert len(arrows) == 1
    start, end = arrows[0].geometry.points
    assert end.x > start.x


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


def test_arrow_export_maps_tip_to_ooxml_tail_end(tmp_path: Path) -> None:
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
    with zipfile.ZipFile(output_path) as archive:
        slide_xml = ET.fromstring(archive.read("ppt/slides/slide1.xml"))
    line = slide_xml.find(".//p:cxnSp/p:spPr/a:ln", XML_NS)
    assert line is not None
    assert line.find("a:tailEnd", XML_NS) is not None
    assert line.find("a:headEnd", XML_NS) is None
