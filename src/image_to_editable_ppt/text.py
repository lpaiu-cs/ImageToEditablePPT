from __future__ import annotations

from dataclasses import dataclass
import math
import re

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
    candidate_regions: list[BBox] | None = None,
) -> list[Element]:
    text_elements: list[Element] = []
    for index, region in enumerate(extract_candidate_regions(image, backend, candidate_regions), start=1):
        content = region.text.strip()
        if not content:
            continue
        if region.confidence < config.text_confidence:
            continue
        if not plausible_text_box(region.bbox, config):
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


def extract_candidate_regions(
    image: Image.Image,
    backend: OCRBackend,
    candidate_regions: list[BBox] | None,
) -> list[OCRTextRegion]:
    if not candidate_regions:
        return backend.extract(image)
    regions: list[OCRTextRegion] = []
    for candidate in candidate_regions:
        crop_box = (
            max(0, int(math.floor(candidate.x0))),
            max(0, int(math.floor(candidate.y0))),
            min(image.size[0], int(math.ceil(candidate.x1))),
            min(image.size[1], int(math.ceil(candidate.y1))),
        )
        if crop_box[2] - crop_box[0] < 2 or crop_box[3] - crop_box[1] < 2:
            continue
        crop = image.crop(crop_box)
        for region in backend.extract(crop):
            regions.append(
                OCRTextRegion(
                    text=region.text,
                    bbox=BBox(
                        region.bbox.x0 + crop_box[0],
                        region.bbox.y0 + crop_box[1],
                        region.bbox.x1 + crop_box[0],
                        region.bbox.y1 + crop_box[1],
                    ),
                    confidence=region.confidence,
                )
            )
    return regions


def merge_ocr_regions(regions: list[OCRTextRegion]) -> list[OCRTextRegion]:
    filtered = [region for region in regions if region.text.strip()]
    if not filtered:
        return []
    lines: list[list[OCRTextRegion]] = []
    for region in sorted(filtered, key=lambda candidate: (candidate.bbox.center.y, candidate.bbox.x0)):
        placed = False
        for line in lines:
            reference = line[0]
            tolerance = max(reference.bbox.height, region.bbox.height) * 0.8
            if abs(reference.bbox.center.y - region.bbox.center.y) <= tolerance:
                line.append(region)
                placed = True
                break
        if not placed:
            lines.append([region])
    merged_lines: list[OCRTextRegion] = []
    for line in lines:
        words = sorted(line, key=lambda candidate: candidate.bbox.x0)
        group: list[OCRTextRegion] = [words[0]]
        for region in words[1:]:
            last = group[-1]
            gap = region.bbox.x0 - last.bbox.x1
            tolerance = max(last.bbox.height, region.bbox.height) * 1.9
            if gap <= max(16.0, tolerance):
                group.append(region)
                continue
            merged_lines.append(_merge_ocr_group(group, separator=" "))
            group = [region]
        merged_lines.append(_merge_ocr_group(group, separator=" "))
    if len(merged_lines) <= 1:
        return merged_lines
    blocks: list[list[OCRTextRegion]] = []
    for region in sorted(merged_lines, key=lambda candidate: (candidate.bbox.y0, candidate.bbox.x0)):
        placed = False
        for block in blocks:
            reference = block[-1]
            gap = region.bbox.y0 - reference.bbox.y1
            overlap = horizontal_overlap_ratio(reference.bbox, region.bbox)
            if overlap >= 0.45 and gap <= max(reference.bbox.height, region.bbox.height) * 1.4:
                block.append(region)
                placed = True
                break
        if not placed:
            blocks.append([region])
    return [_merge_ocr_group(block, separator="\n") for block in blocks]


def normalize_ocr_text(text: str) -> str:
    lowered = text.casefold()
    lowered = re.sub(r"\s+", " ", lowered)
    lowered = re.sub(r"[^0-9a-zA-Z가-힣 ]+", "", lowered)
    return lowered.strip()


def horizontal_overlap_ratio(first: BBox, second: BBox) -> float:
    overlap = min(first.x1, second.x1) - max(first.x0, second.x0)
    if overlap <= 0:
        return 0.0
    return overlap / max(1.0, min(first.width, second.width))


def _merge_ocr_group(group: list[OCRTextRegion], *, separator: str) -> OCRTextRegion:
    text = separator.join(region.text.strip() for region in group if region.text.strip()).strip()
    bbox = BBox(
        min(region.bbox.x0 for region in group),
        min(region.bbox.y0 for region in group),
        max(region.bbox.x1 for region in group),
        max(region.bbox.y1 for region in group),
    )
    confidence = sum(region.confidence for region in group) / max(1, len(group))
    return OCRTextRegion(text=text, bbox=bbox, confidence=confidence)


def plausible_text_box(bbox: BBox, config: PipelineConfig) -> bool:
    if bbox.width < max(8.0, config.text_margin * 0.7):
        return False
    if bbox.height < max(6.0, config.text_margin * 0.45):
        return False
    if bbox.height > bbox.width * 1.8:
        return False
    return True


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
