from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from PIL import Image

from .config import PipelineConfig
from .detector import detect_elements_with_metadata, finalize_detected_elements
from .exporter import export_to_pptx
from .filtering import RejectedRegion
from .gating import gate_elements
from .ir import Element
from .preprocess import load_image, preprocess_image
from .repair import repair_elements
from .text import OCRBackend, extract_text_elements, get_ocr_backend


@dataclass(slots=True)
class ConversionResult:
    elements: list[Element]
    image_size: tuple[int, int]
    rejected_regions: list[RejectedRegion]
    output_path: Path | None = None


def convert_image(
    input_path: str | Path,
    output_path: str | Path,
    *,
    config: PipelineConfig | None = None,
    enable_ocr: bool = False,
    debug_elements_path: str | Path | None = None,
    ocr_backend: OCRBackend | None = None,
) -> ConversionResult:
    image = load_image(input_path)
    result = build_elements(image, config=config, enable_ocr=enable_ocr, ocr_backend=ocr_backend)
    export_to_pptx(result.elements, result.image_size, output_path, config or PipelineConfig())
    if debug_elements_path is not None:
        dump_debug_artifacts(result.elements, result.rejected_regions, debug_elements_path)
    result.output_path = Path(output_path)
    return result


def build_elements(
    image: Image.Image,
    *,
    config: PipelineConfig | None = None,
    enable_ocr: bool = False,
    ocr_backend: OCRBackend | None = None,
) -> ConversionResult:
    active_config = config or PipelineConfig()
    processed = preprocess_image(
        image,
        foreground_threshold=active_config.foreground_threshold,
        min_component_area=active_config.min_component_area,
        min_stroke_length=active_config.min_stroke_length,
        min_box_size=active_config.min_box_size,
        min_relative_line_length=active_config.min_relative_line_length,
        min_relative_box_size=active_config.min_relative_box_size,
        adaptive_background=active_config.adaptive_background,
        background_blur_divisor=active_config.background_blur_divisor,
        fill_region_background_ratio=active_config.fill_region_background_ratio,
        fill_region_uniformity_ratio=active_config.fill_region_uniformity_ratio,
        fill_region_edge_ratio=active_config.fill_region_edge_ratio,
    )
    detection = detect_elements_with_metadata(processed, active_config)
    elements = detection.elements
    elements = repair_elements(elements, processed, active_config, bridge_mask=detection.bridge_mask)
    elements = finalize_detected_elements(elements, processed, active_config)
    backend = ocr_backend or get_ocr_backend(enable_ocr)
    text = extract_text_elements(
        image,
        elements,
        active_config,
        backend=backend,
        candidate_regions=detection.text_regions,
    )
    gated = gate_elements(elements + text, active_config)
    return ConversionResult(
        elements=gated,
        image_size=image.size,
        rejected_regions=detection.rejected_regions,
    )


def dump_elements(elements: list[Element], path: str | Path) -> None:
    with Path(path).open("w", encoding="utf-8") as handle:
        json.dump([element.to_dict() for element in elements], handle, indent=2)


def dump_debug_artifacts(
    elements: list[Element],
    rejected_regions: list[RejectedRegion],
    path: str | Path,
) -> None:
    target = Path(path)
    dump_elements(elements, target)
    rejection_name = f"{target.stem}.rejections{target.suffix or '.json'}"
    rejection_path = target.with_name(rejection_name)
    with rejection_path.open("w", encoding="utf-8") as handle:
        json.dump([region.to_dict() for region in rejected_regions], handle, indent=2)
