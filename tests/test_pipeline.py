from __future__ import annotations

from pathlib import Path

from pptx import Presentation

from image_to_editable_ppt.config import PipelineConfig
from image_to_editable_ppt.ir import BBox
from image_to_editable_ppt.pipeline import build_elements, convert_image
from image_to_editable_ppt.text import OCRBackend, OCRTextRegion
from tests.synthetic import complex_diagram, icon_only, occluded_box, open_contour, save_image, text_box_diagram


class FakeOCRBackend(OCRBackend):
    def __init__(self, regions: list[OCRTextRegion]) -> None:
        self._regions = regions

    def extract(self, image):
        return self._regions


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
