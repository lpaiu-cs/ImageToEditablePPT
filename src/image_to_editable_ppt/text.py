from __future__ import annotations

from dataclasses import dataclass
import math

from PIL import Image

from .config import PipelineConfig
from .ir import BBox, BoxGeometry, Element, FillStyle, Point, PolylineGeometry, StrokeStyle, TextPayload


@dataclass(slots=True, frozen=True)
class OCRTextRegion:
    text: str
    bbox: BBox
    confidence: float


class OCRBackend:
    def extract(self, image: Image.Image) -> list[OCRTextRegion]:
        raise NotImplementedError


class NullOCRBackend(OCRBackend):
    def extract(self, image: Image.Image) -> list[OCRTextRegion]:
        return []


class TesseractOCRBackend(OCRBackend):
    def __init__(self) -> None:
        import pytesseract

        self._pytesseract = pytesseract

    def extract(self, image: Image.Image) -> list[OCRTextRegion]:
        try:
            data = self._pytesseract.image_to_data(
                image,
                output_type=self._pytesseract.Output.DICT,
            )
        except Exception:
            return []
        regions: list[OCRTextRegion] = []
        for text, conf, left, top, width, height in zip(
            data["text"],
            data["conf"],
            data["left"],
            data["top"],
            data["width"],
            data["height"],
            strict=True,
        ):
            content = text.strip()
            if not content:
                continue
            try:
                confidence = float(conf) / 100.0
            except Exception:
                continue
            regions.append(
                OCRTextRegion(
                    text=content,
                    bbox=BBox(float(left), float(top), float(left + width), float(top + height)),
                    confidence=confidence,
                )
            )
        return regions


def get_ocr_backend(enabled: bool) -> OCRBackend:
    if not enabled:
        return NullOCRBackend()
    try:
        return TesseractOCRBackend()
    except Exception:
        return NullOCRBackend()


def extract_text_elements(
    image: Image.Image,
    structural_elements: list[Element],
    config: PipelineConfig,
    *,
    backend: OCRBackend,
) -> list[Element]:
    text_elements: list[Element] = []
    for index, region in enumerate(backend.extract(image), start=1):
        content = region.text.strip()
        if not content:
            continue
        if region.confidence < config.text_confidence:
            continue
        if not looks_structural(region.bbox, structural_elements, config):
            continue
        text_elements.append(
            Element(
                id=f"text-{index}",
                kind="text",
                geometry=BoxGeometry(bbox=region.bbox),
                stroke=StrokeStyle(color=(0, 0, 0), width=0.0),
                fill=FillStyle(enabled=False, color=None),
                text=TextPayload(content=content, alignment="center", confidence=region.confidence),
                confidence=min(0.99, 0.80 + region.confidence * 0.18),
                source_region=region.bbox,
                inferred=False,
            )
        )
    return text_elements


def looks_structural(bbox: BBox, structural_elements: list[Element], config: PipelineConfig) -> bool:
    center = bbox.center
    for element in structural_elements:
        if element.kind in {"rect", "rounded_rect"} and element.bbox.inset(config.text_margin).contains_point(center):
            return True
        if element.kind in {"line", "orthogonal_connector", "arrow"} and is_near_polyline(center, element, config.text_margin):
            return True
    return False


def is_near_polyline(point: Point, element: Element, margin: float) -> bool:
    if not isinstance(element.geometry, PolylineGeometry):
        return False
    if not element.bbox.expand(margin).contains_point(point):
        return False
    for start, end in zip(element.geometry.points[:-1], element.geometry.points[1:], strict=True):
        if point_segment_distance(point, start, end) <= margin:
            return True
    return False


def point_segment_distance(point: Point, start: Point, end: Point) -> float:
    dx = end.x - start.x
    dy = end.y - start.y
    if dx == 0 and dy == 0:
        return math.hypot(point.x - start.x, point.y - start.y)
    projection = ((point.x - start.x) * dx + (point.y - start.y) * dy) / (dx * dx + dy * dy)
    projection = max(0.0, min(1.0, projection))
    closest = Point(start.x + projection * dx, start.y + projection * dy)
    return math.hypot(point.x - closest.x, point.y - closest.y)
