"""Optional OCR annotation for text regions (Phase 10).

Fills ``TextRegion.text`` from the source image using rapidocr (ONNX runtime,
no system binary required). The backend is optional: when it is not installed
the regions pass through unchanged, so the pipeline stays alive and simply
leaves text blank — a blank is honest, a hallucinated label is not.

Recognition below ``min_confidence`` is discarded per the project principle
"텍스트도 신뢰할 수 있을 때만 변환한다".
"""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from image_to_editable_ppt.v3.ir.models import TextRegion

_ENGINE: object | None = None
_ENGINE_FAILED = False
_REGION_PAD = 3
# Small crops recognize poorly; upscale short text lines to roughly this height.
_MIN_CROP_HEIGHT = 32


def ocr_available() -> bool:
    return _load_engine() is not None


def annotate_text_regions(
    rgb: np.ndarray,
    regions: tuple["TextRegion", ...],
    *,
    min_confidence: float = 0.6,
) -> tuple["TextRegion", ...]:
    """Return regions with ``text`` filled where OCR is confident enough."""
    engine = _load_engine()
    if engine is None or not regions:
        return regions
    height, width = rgb.shape[:2]
    annotated: list[TextRegion] = []
    for region in regions:
        if region.text:
            annotated.append(region)
            continue
        text, confidence = _recognize(engine, rgb, region, width=width, height=height)
        if text and confidence >= min_confidence:
            annotated.append(
                replace(
                    region,
                    text=text,
                    provenance=(*region.provenance, f"ocr:rapidocr:{confidence:.2f}"),
                )
            )
        else:
            annotated.append(region)
    return tuple(annotated)


def _recognize(engine, rgb: np.ndarray, region: "TextRegion", *, width: int, height: int) -> tuple[str | None, float]:
    x0 = max(0, int(region.bbox.x0) - _REGION_PAD)
    y0 = max(0, int(region.bbox.y0) - _REGION_PAD)
    x1 = min(width, int(region.bbox.x1) + _REGION_PAD)
    y1 = min(height, int(region.bbox.y1) + _REGION_PAD)
    if x1 - x0 < 4 or y1 - y0 < 4:
        return None, 0.0
    crop = rgb[y0:y1, x0:x1]
    if crop.shape[0] < _MIN_CROP_HEIGHT:
        scale = _MIN_CROP_HEIGHT / crop.shape[0]
        import cv2

        crop = cv2.resize(crop, (max(8, int(crop.shape[1] * scale)), _MIN_CROP_HEIGHT), interpolation=cv2.INTER_CUBIC)

    result, _ = engine(crop)
    if not result:
        return None, 0.0
    # Order detected snippets top-to-bottom then left-to-right; snippets whose
    # vertical extents overlap belong to the same visual line (joined with a
    # space), the rest become separate lines so emit can size fonts honestly.
    entries = sorted(result, key=lambda item: (min(p[1] for p in item[0]), min(p[0] for p in item[0])))
    lines: list[list[tuple[str, float, float]]] = []  # (text, y0, y1) per snippet
    scores: list[float] = []
    for box, raw_text, raw_score in entries:
        text = str(raw_text).strip()
        if not text:
            continue
        y0 = min(point[1] for point in box)
        y1 = max(point[1] for point in box)
        scores.append(float(raw_score))
        if lines:
            _, last_y0, last_y1 = lines[-1][-1]
            overlap = min(last_y1, y1) - max(last_y0, y0)
            if overlap > 0.5 * min(last_y1 - last_y0, y1 - y0):
                lines[-1].append((text, y0, y1))
                continue
        lines.append([(text, y0, y1)])
    if not lines:
        return None, 0.0
    joined = "\n".join(" ".join(snippet[0] for snippet in line) for line in lines)
    return joined, min(scores)


def _load_engine() -> object | None:
    global _ENGINE, _ENGINE_FAILED
    if _ENGINE is not None:
        return _ENGINE
    if _ENGINE_FAILED:
        return None
    try:
        from rapidocr_onnxruntime import RapidOCR

        _ENGINE = RapidOCR()
    except Exception:
        _ENGINE_FAILED = True
        return None
    return _ENGINE
