from __future__ import annotations

from dataclasses import dataclass
import io

from PIL import Image

from ..config import PipelineConfig
from ..ir import BoxGeometry, Element, FillStyle, StrokeStyle
from ..schema import DropReason, EmissionRecord, FallbackRegion, ObjectHypothesis, validate_stage_entities


@dataclass(slots=True)
class RasterFallbackBuildResult:
    regions: list[FallbackRegion]
    elements: list[Element]
    emission_records: list[EmissionRecord]


def build_raster_fallback_regions(
    image: Image.Image,
    hypotheses: list[ObjectHypothesis],
    config: PipelineConfig,
    *,
    stage: str = "07_emit",
) -> RasterFallbackBuildResult:
    regions: list[FallbackRegion] = []
    elements: list[Element] = []
    emission_records: list[EmissionRecord] = []
    native_threshold = max(0.86, config.inclusion_confidence + 0.06)
    next_index = 1
    for hypothesis in hypotheses:
        if hypothesis.bbox is None:
            continue
        if not should_emit_raster_fallback(hypothesis, native_threshold=native_threshold):
            continue
        crop = crop_region(image, hypothesis.bbox)
        if crop is None:
            continue
        asset_id = f"raster-asset-{next_index:03d}"
        png_bytes = encode_png(crop)
        region = FallbackRegion(
            id=f"fallback-region:{hypothesis.id}",
            kind="raster_fallback",
            bbox=hypothesis.bbox,
            score_total=1.0 - min(1.0, hypothesis.score_total),
            score_terms={
                "hypothesis_score": hypothesis.score_total,
                "fallback_triggered": 1.0,
            },
            source_ids=[hypothesis.id, *hypothesis.source_ids],
            provenance={
                "hypothesis_ids": [hypothesis.id],
                "source_ids": list(hypothesis.source_ids),
            },
            assigned_text_ids=list(hypothesis.assigned_text_ids),
            assigned_vlm_ids=list(hypothesis.assigned_vlm_ids),
            object_type="raster_region",
            strategy="raster_crop",
            asset_id=asset_id,
        )
        regions.append(region)
        element = Element(
            id=f"raster-{next_index}",
            kind="raster_region",
            geometry=BoxGeometry(hypothesis.bbox),
            stroke=StrokeStyle(color=(0, 0, 0), width=0.0),
            fill=FillStyle(enabled=False, color=None),
            text=None,
            confidence=max(config.tentative_confidence, hypothesis.score_total),
            source_region=hypothesis.bbox,
            inferred=True,
            raster_image=png_bytes,
            raster_asset_id=asset_id,
        )
        elements.append(element)
        emission_records.append(
            EmissionRecord(
                id=f"emit:{element.id}",
                kind="raster_region",
                bbox=hypothesis.bbox,
                score_total=element.confidence,
                score_terms={"confidence": element.confidence, "raster_fallback": 1.0},
                source_ids=[region.id, *hypothesis.source_ids],
                provenance={
                    "graph_node_ids": [hypothesis.id],
                    "hypothesis_ids": [hypothesis.id],
                    "fallback_region_ids": [region.id],
                },
                assigned_text_ids=list(hypothesis.assigned_text_ids),
                assigned_vlm_ids=list(hypothesis.assigned_vlm_ids),
                object_type="raster_region",
                primitive_kind="raster_region",
                graph_node_ids=[hypothesis.id],
                hypothesis_ids=[hypothesis.id],
                emitted_element_id=element.id,
            )
        )
        next_index += 1
    return RasterFallbackBuildResult(
        regions=list(validate_stage_entities(stage, "raster_fallback_regions", regions, require_bbox=True)),
        elements=elements,
        emission_records=list(validate_stage_entities(stage, "raster_fallback_emission_records", emission_records, require_bbox=True)),
    )


def should_emit_raster_fallback(
    hypothesis: ObjectHypothesis,
    *,
    native_threshold: float,
) -> bool:
    if hypothesis.object_type == "connector":
        return False
    if hypothesis.fallback:
        return True
    return hypothesis.score_total < native_threshold


def crop_region(image: Image.Image, bbox) -> Image.Image | None:
    x0 = max(0, int(round(bbox.x0)))
    y0 = max(0, int(round(bbox.y0)))
    x1 = min(image.size[0], int(round(bbox.x1)))
    y1 = min(image.size[1], int(round(bbox.y1)))
    if x1 - x0 < 2 or y1 - y0 < 2:
        return None
    return image.crop((x0, y0, x1, y1)).convert("RGB")


def encode_png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
