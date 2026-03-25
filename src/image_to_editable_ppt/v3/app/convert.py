from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from image_to_editable_ppt.v3.app.config import V3Config
from image_to_editable_ppt.v3.core.contracts import StageRecord
from image_to_editable_ppt.v3.core.enums import ResidualKind, StageName
from image_to_editable_ppt.v3.core.types import BBox
from image_to_editable_ppt.v3.ir.models import (
    ConnectorSpec,
    DiagramInstance,
    FamilyProposal,
    MultiViewBundle,
    RasterRegion,
    ResidualRegion,
    SlideIR,
    StyleToken,
    TextRegion,
)
from image_to_editable_ppt.v3.ir.validate import validate_multiview_bundle, validate_slide_ir
from image_to_editable_ppt.v3.preprocessing.multiview import build_multiview_bundle


@dataclass(slots=True)
class V3ConversionResult:
    config: V3Config
    multiview: MultiViewBundle
    slide_ir: SlideIR
    stage_records: tuple[StageRecord, ...]


def convert_image(input_image: str | Path | Image.Image, *, config: V3Config | None = None) -> V3ConversionResult:
    active_config = config or V3Config()
    image = _load_image(input_image)
    multiview = build_multiview_bundle(image, config=active_config)
    validate_multiview_bundle(multiview)

    text_regions = _extract_text_regions(multiview, active_config)
    raster_regions = _extract_raster_regions(multiview, text_regions, active_config)
    family_proposals = _detect_families(multiview, text_regions, raster_regions, active_config)
    instances = _parse_families(multiview, family_proposals, text_regions, raster_regions, active_config)
    connectors = _resolve_connectors(multiview, instances, active_config)
    style_tokens = _resolve_style_tokens(multiview, instances, active_config)
    residual_regions = _build_residuals(multiview, instances, text_regions, raster_regions, active_config)

    slide_ir = SlideIR(
        image_size=multiview.image_size,
        family_proposals=family_proposals,
        diagram_instances=instances,
        connectors=connectors,
        text_regions=text_regions,
        raster_regions=raster_regions,
        style_tokens=style_tokens,
        residual_regions=residual_regions,
    )
    validate_slide_ir(slide_ir)

    stage_records = (
        StageRecord(
            stage=StageName.MULTIVIEW,
            summary={
                "branch_count": len(multiview.branches),
                "image_size": multiview.image_size.as_tuple(),
            },
        ),
        StageRecord(stage=StageName.TEXT_SPLIT, summary={"text_region_count": len(text_regions)}),
        StageRecord(stage=StageName.RASTER_SPLIT, summary={"raster_region_count": len(raster_regions)}),
        StageRecord(
            stage=StageName.FAMILY_DETECT,
            summary={
                "proposal_count": len(family_proposals),
                "enabled_families": sorted(family.value for family in active_config.enabled_families),
            },
        ),
        StageRecord(stage=StageName.FAMILY_PARSE, summary={"instance_count": len(instances)}),
        StageRecord(stage=StageName.CONNECTOR_RESOLVE, summary={"connector_count": len(connectors)}),
        StageRecord(stage=StageName.STYLE_RESOLVE, summary={"style_token_count": len(style_tokens)}),
        StageRecord(stage=StageName.COMPOSE, summary={"residual_region_count": len(residual_regions)}),
    )
    return V3ConversionResult(
        config=active_config,
        multiview=multiview,
        slide_ir=slide_ir,
        stage_records=stage_records,
    )


def _load_image(input_image: str | Path | Image.Image) -> Image.Image:
    if isinstance(input_image, Image.Image):
        return input_image.convert("RGB")
    return Image.open(input_image).convert("RGB")


def _extract_text_regions(multiview: MultiViewBundle, config: V3Config) -> tuple[TextRegion, ...]:
    del multiview, config
    return ()


def _extract_raster_regions(
    multiview: MultiViewBundle,
    text_regions: tuple[TextRegion, ...],
    config: V3Config,
) -> tuple[RasterRegion, ...]:
    del multiview, text_regions, config
    return ()


def _detect_families(
    multiview: MultiViewBundle,
    text_regions: tuple[TextRegion, ...],
    raster_regions: tuple[RasterRegion, ...],
    config: V3Config,
) -> tuple[FamilyProposal, ...]:
    del multiview, text_regions, raster_regions, config
    return ()


def _parse_families(
    multiview: MultiViewBundle,
    family_proposals: tuple[FamilyProposal, ...],
    text_regions: tuple[TextRegion, ...],
    raster_regions: tuple[RasterRegion, ...],
    config: V3Config,
) -> tuple[DiagramInstance, ...]:
    del multiview, family_proposals, text_regions, raster_regions, config
    return ()


def _resolve_connectors(
    multiview: MultiViewBundle,
    instances: tuple[DiagramInstance, ...],
    config: V3Config,
) -> tuple[ConnectorSpec, ...]:
    del multiview, instances, config
    return ()


def _resolve_style_tokens(
    multiview: MultiViewBundle,
    instances: tuple[DiagramInstance, ...],
    config: V3Config,
) -> tuple[StyleToken, ...]:
    del multiview, instances, config
    return ()


def _build_residuals(
    multiview: MultiViewBundle,
    instances: tuple[DiagramInstance, ...],
    text_regions: tuple[TextRegion, ...],
    raster_regions: tuple[RasterRegion, ...],
    config: V3Config,
) -> tuple[ResidualRegion, ...]:
    del text_regions, raster_regions
    if instances or not config.preserve_unresolved_residuals:
        return ()
    return (
        ResidualRegion(
            id="residual:structural_canvas",
            kind=ResidualKind.UNRESOLVED,
            bbox=BBox.from_image_size(multiview.image_size),
            confidence=1.0,
            reason="family_parser_not_implemented",
        ),
    )
