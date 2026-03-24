from __future__ import annotations

from dataclasses import dataclass
import io
from math import ceil, floor

from PIL import Image

from ..config import PipelineConfig
from ..ir import BBox, BoxGeometry, Element, FillStyle, StrokeStyle
from ..schema import EmissionRecord, FallbackRegion, ObjectHypothesis, validate_stage_entities


@dataclass(slots=True)
class RasterFallbackBuildResult:
    regions: list[FallbackRegion]
    elements: list[Element]
    emission_records: list[EmissionRecord]
    dropped_regions: list[dict[str, object]]


@dataclass(slots=True, frozen=True)
class RasterCluster:
    bbox: BBox
    hypothesis_ids: tuple[str, ...]
    source_ids: tuple[str, ...]
    assigned_text_ids: tuple[str, ...]
    assigned_vlm_ids: tuple[str, ...]
    score_total: float


def build_raster_fallback_regions(
    image: Image.Image,
    hypotheses: list[ObjectHypothesis],
    config: PipelineConfig,
    *,
    stage: str = "07_emit",
) -> RasterFallbackBuildResult:
    candidate_clusters = build_raster_clusters(hypotheses, config)
    regions: list[FallbackRegion] = []
    elements: list[Element] = []
    emission_records: list[EmissionRecord] = []
    dropped_regions: list[dict[str, object]] = []
    next_index = 1
    for cluster in candidate_clusters:
        crop = crop_region(image, cluster.bbox)
        if crop is None:
            dropped_regions.append(
                {
                    "cluster_hypothesis_ids": list(cluster.hypothesis_ids),
                    "reason": "invalid_crop",
                    "bbox": cluster.bbox.to_dict(),
                }
            )
            continue
        asset_id = f"raster-asset-{next_index:03d}"
        png_bytes = encode_png(crop)
        region = FallbackRegion(
            id=f"fallback-region:{asset_id}",
            kind="raster_fallback",
            bbox=cluster.bbox,
            score_total=1.0 - min(1.0, cluster.score_total),
            score_terms={
                "cluster_score": cluster.score_total,
                "fallback_triggered": 1.0,
                "cluster_size": float(len(cluster.hypothesis_ids)),
            },
            source_ids=list(cluster.source_ids),
            provenance={
                "hypothesis_ids": list(cluster.hypothesis_ids),
                "source_ids": list(cluster.source_ids),
            },
            assigned_text_ids=list(cluster.assigned_text_ids),
            assigned_vlm_ids=list(cluster.assigned_vlm_ids),
            object_type="raster_region",
            strategy="raster_crop",
            asset_id=asset_id,
        )
        regions.append(region)
        element = Element(
            id=f"raster-{next_index}",
            kind="raster_region",
            geometry=BoxGeometry(cluster.bbox),
            stroke=StrokeStyle(color=(0, 0, 0), width=0.0),
            fill=FillStyle(enabled=False, color=None),
            text=None,
            confidence=max(config.tentative_confidence, cluster.score_total),
            source_region=cluster.bbox,
            inferred=True,
            raster_image=png_bytes,
            raster_asset_id=asset_id,
        )
        elements.append(element)
        emission_records.append(
            EmissionRecord(
                id=f"emit:{element.id}",
                kind="raster_region",
                bbox=cluster.bbox,
                score_total=element.confidence,
                score_terms={"confidence": element.confidence, "raster_fallback": 1.0},
                source_ids=[region.id, *cluster.source_ids],
                provenance={
                    "graph_node_ids": list(cluster.hypothesis_ids),
                    "hypothesis_ids": list(cluster.hypothesis_ids),
                    "fallback_region_ids": [region.id],
                },
                assigned_text_ids=list(cluster.assigned_text_ids),
                assigned_vlm_ids=list(cluster.assigned_vlm_ids),
                object_type="raster_region",
                primitive_kind="raster_region",
                graph_node_ids=list(cluster.hypothesis_ids),
                hypothesis_ids=list(cluster.hypothesis_ids),
                emitted_element_id=element.id,
            )
        )
        next_index += 1
    return RasterFallbackBuildResult(
        regions=list(validate_stage_entities(stage, "raster_fallback_regions", regions, require_bbox=True)),
        elements=elements,
        emission_records=list(validate_stage_entities(stage, "raster_fallback_emission_records", emission_records, require_bbox=True)),
        dropped_regions=dropped_regions,
    )


def prune_raster_fallback_against_native(
    raster_result: RasterFallbackBuildResult,
    native_elements: list[Element],
    config: PipelineConfig,
) -> RasterFallbackBuildResult:
    kept_regions: list[FallbackRegion] = []
    kept_elements: list[Element] = []
    kept_records: list[EmissionRecord] = []
    dropped_regions = list(raster_result.dropped_regions)
    native_boxes = [element.bbox for element in native_elements if element.kind != "raster_region"]
    for region, element, record in zip(raster_result.regions, raster_result.elements, raster_result.emission_records, strict=True):
        native_overlap_ratio = overlap_ratio(region.bbox, native_boxes)
        if native_overlap_ratio >= config.raster_fallback_native_overlap_threshold:
            dropped_regions.append(
                {
                    "fallback_region_id": region.id,
                    "reason": "covered_by_native",
                    "native_overlap_ratio": round(native_overlap_ratio, 4),
                    "bbox": region.bbox.to_dict() if region.bbox is not None else None,
                }
            )
            continue
        kept_regions.append(region)
        kept_elements.append(element)
        kept_records.append(record)
    return RasterFallbackBuildResult(
        regions=kept_regions,
        elements=kept_elements,
        emission_records=kept_records,
        dropped_regions=dropped_regions,
    )


def build_raster_clusters(
    hypotheses: list[ObjectHypothesis],
    config: PipelineConfig,
) -> list[RasterCluster]:
    native_threshold = max(config.raster_fallback_confidence_threshold, config.inclusion_confidence + 0.06)
    candidates = [hypothesis for hypothesis in hypotheses if hypothesis.bbox is not None and should_emit_raster_fallback(hypothesis, native_threshold=native_threshold)]
    clusters: list[RasterCluster] = []
    for hypothesis in candidates:
        merged = False
        for index, cluster in enumerate(clusters):
            if should_merge(cluster.bbox, hypothesis.bbox, config):
                clusters[index] = merge_cluster(cluster, hypothesis)
                merged = True
                break
        if not merged:
            clusters.append(
                RasterCluster(
                    bbox=hypothesis.bbox,
                    hypothesis_ids=(hypothesis.id,),
                    source_ids=tuple(hypothesis.source_ids),
                    assigned_text_ids=tuple(hypothesis.assigned_text_ids),
                    assigned_vlm_ids=tuple(hypothesis.assigned_vlm_ids),
                    score_total=hypothesis.score_total,
                )
            )
    return clusters


def should_emit_raster_fallback(
    hypothesis: ObjectHypothesis,
    *,
    native_threshold: float,
) -> bool:
    if hypothesis.object_type == "connector":
        return False
    if hypothesis.fallback and hypothesis.score_total >= hypothesis_native_confidence_floor(native_threshold):
        return False
    if hypothesis.fallback:
        return True
    return hypothesis.score_total < native_threshold


def hypothesis_native_confidence_floor(native_threshold: float) -> float:
    return min(native_threshold, 0.80)


def should_merge(first: BBox, second: BBox, config: PipelineConfig) -> bool:
    if first.iou(second) >= config.raster_fallback_merge_iou:
        return True
    expanded = first.expand(config.raster_fallback_merge_gap)
    return expanded.contains_point(second.center) or second.expand(config.raster_fallback_merge_gap).contains_point(first.center)


def merge_cluster(cluster: RasterCluster, hypothesis: ObjectHypothesis) -> RasterCluster:
    return RasterCluster(
        bbox=merge_bboxes(cluster.bbox, hypothesis.bbox),
        hypothesis_ids=tuple(dict.fromkeys([*cluster.hypothesis_ids, hypothesis.id])),
        source_ids=tuple(dict.fromkeys([*cluster.source_ids, *hypothesis.source_ids])),
        assigned_text_ids=tuple(dict.fromkeys([*cluster.assigned_text_ids, *hypothesis.assigned_text_ids])),
        assigned_vlm_ids=tuple(dict.fromkeys([*cluster.assigned_vlm_ids, *hypothesis.assigned_vlm_ids])),
        score_total=max(cluster.score_total, hypothesis.score_total),
    )


def overlap_ratio(bbox: BBox | None, others: list[BBox]) -> float:
    if bbox is None or bbox.area <= 0.0 or not others:
        return 0.0
    overlap = 0.0
    for other in others:
        overlap += intersection_area(bbox, other)
    return min(1.0, overlap / bbox.area)


def merge_bboxes(first: BBox, second: BBox) -> BBox:
    return BBox(min(first.x0, second.x0), min(first.y0, second.y0), max(first.x1, second.x1), max(first.y1, second.y1))


def intersection_area(first: BBox, second: BBox) -> float:
    x0 = max(first.x0, second.x0)
    y0 = max(first.y0, second.y0)
    x1 = min(first.x1, second.x1)
    y1 = min(first.y1, second.y1)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    return (x1 - x0) * (y1 - y0)


def crop_region(image: Image.Image, bbox: BBox) -> Image.Image | None:
    x0 = max(0, int(floor(bbox.x0)))
    y0 = max(0, int(floor(bbox.y0)))
    x1 = min(image.size[0], int(ceil(bbox.x1)))
    y1 = min(image.size[1], int(ceil(bbox.y1)))
    if x1 - x0 < 2 or y1 - y0 < 2:
        return None
    return image.crop((x0, y0, x1, y1)).convert("RGB")


def encode_png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
