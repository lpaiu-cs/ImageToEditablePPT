from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from image_to_editable_ppt.v3.app.config import V3Config
from image_to_editable_ppt.v3.compose import build_primitive_scene
from image_to_editable_ppt.v3.connectors import (
    attach_connector_evidence,
    extract_connector_evidence,
    generate_ports,
    resolve_connector_candidates,
)
from image_to_editable_ppt.v3.core.contracts import StageRecord
from image_to_editable_ppt.v3.core.enums import ResidualKind, StageName
from image_to_editable_ppt.v3.families import detect_family_proposals, parse_family_proposals
from image_to_editable_ppt.v3.ir.models import (
    ConnectorSpec,
    ConnectorEvidence,
    DiagramInstance,
    FamilyProposal,
    MultiViewBundle,
    PortSpec,
    PrimitiveConnectorCandidate,
    PrimitiveScene,
    RasterLayerResult,
    ResidualRegion,
    ResidualCanvasResult,
    SlideIR,
    StyleToken,
    TextLayerResult,
    UnattachedConnectorEvidence,
)
from image_to_editable_ppt.v3.ir.validate import (
    validate_multiview_bundle,
    validate_primitive_scene,
    validate_raster_layer_result,
    validate_residual_canvas_result,
    validate_slide_ir,
    validate_text_layer_result,
)
from image_to_editable_ppt.v3.preprocessing import build_multiview_bundle, build_residual_canvas
from image_to_editable_ppt.v3.raster import extract_raster_layer
from image_to_editable_ppt.v3.text import extract_text_layer


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

    text_layer = _extract_text_layer(multiview, active_config)
    validate_text_layer_result(text_layer)
    raster_layer = _extract_raster_layer(multiview, text_layer, active_config)
    validate_raster_layer_result(raster_layer)
    residual_canvas = _build_residual_canvas(multiview, text_layer, raster_layer)
    validate_residual_canvas_result(residual_canvas)
    family_proposals = _detect_families(residual_canvas, text_layer, raster_layer, active_config)
    instances = _parse_families(residual_canvas, family_proposals, text_layer, raster_layer, active_config)
    connector_evidence = _extract_connector_evidence(residual_canvas, instances, active_config)
    ports = _generate_ports(instances, active_config)
    connector_candidates, unattached_connector_evidence = _attach_connector_evidence(
        connector_evidence,
        ports,
        active_config,
    )
    connectors = _resolve_connector_candidates(connector_candidates, active_config)
    style_tokens = _resolve_style_tokens(residual_canvas, instances, active_config)
    residual_regions = _build_residual_regions(residual_canvas, instances, active_config)
    primitive_scene = _build_primitive_scene(
        text_layer=text_layer,
        raster_layer=raster_layer,
        residual_canvas=residual_canvas,
        instances=instances,
        ports=ports,
        connector_candidates=connector_candidates,
        unattached_connector_evidence=unattached_connector_evidence,
        residual_regions=residual_regions,
        config=active_config,
    )
    validate_primitive_scene(primitive_scene)

    slide_ir = SlideIR(
        image_size=multiview.image_size,
        text_layer=text_layer,
        raster_layer=raster_layer,
        residual_canvas=residual_canvas,
        family_proposals=family_proposals,
        diagram_instances=instances,
        connector_evidence=connector_evidence,
        connector_candidates=connector_candidates,
        unattached_connector_evidence=unattached_connector_evidence,
        connectors=connectors,
        primitive_scene=primitive_scene,
        text_regions=text_layer.regions,
        raster_regions=raster_layer.regions,
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
        StageRecord(
            stage=StageName.TEXT_SPLIT,
            summary={
                "text_region_count": len(text_layer.regions),
                "soft_mask_pixels": int((text_layer.soft_mask > 0.0).sum()),
            },
        ),
        StageRecord(
            stage=StageName.RASTER_SPLIT,
            summary={
                "raster_region_count": len(raster_layer.regions),
                "subtraction_mask_pixels": int((raster_layer.subtraction_mask > 0.0).sum()),
            },
        ),
        StageRecord(
            stage=StageName.RESIDUAL_CANVAS,
            summary={
                "canvas_ready": residual_canvas.canvas is not None,
                "combined_mask_pixels": int((residual_canvas.combined_mask > 0.0).sum()),
            },
        ),
        StageRecord(
            stage=StageName.FAMILY_DETECT,
            summary={
                "proposal_count": len(family_proposals),
                "enabled_families": sorted(family.value for family in active_config.enabled_families),
            },
        ),
        StageRecord(stage=StageName.FAMILY_PARSE, summary={"instance_count": len(instances)}),
        StageRecord(
            stage=StageName.CONNECTOR_EVIDENCE,
            summary={
                "connector_evidence_count": len(connector_evidence),
                "arrow_evidence_count": sum(
                    1 for evidence in connector_evidence if evidence.arrowhead_start or evidence.arrowhead_end
                ),
            },
        ),
        StageRecord(
            stage=StageName.PORT_GENERATE,
            summary={
                "port_count": len(ports),
                "owner_count": len({port.owner_id for port in ports}),
            },
        ),
        StageRecord(
            stage=StageName.CONNECTOR_ATTACH,
            summary={
                "connector_candidate_count": len(connector_candidates),
                "unattached_evidence_count": len(unattached_connector_evidence),
            },
        ),
        StageRecord(
            stage=StageName.CONNECTOR_RESOLVE,
            summary={
                "connector_candidate_count": len(connector_candidates),
                "solved_connector_count": len(connectors),
                "unsolved_candidate_count": len(connector_candidates) - len(connectors),
            },
        ),
        StageRecord(stage=StageName.STYLE_RESOLVE, summary={"style_token_count": len(style_tokens)}),
        StageRecord(
            stage=StageName.COMPOSE,
            summary={
                "primitive_node_count": len(primitive_scene.nodes),
                "primitive_container_count": len(primitive_scene.containers),
                "primitive_text_count": len(primitive_scene.texts),
                "primitive_residual_count": len(primitive_scene.residuals),
            },
        ),
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


def _extract_text_layer(multiview: MultiViewBundle, config: V3Config) -> TextLayerResult:
    return extract_text_layer(multiview, config=config)


def _extract_raster_layer(
    multiview: MultiViewBundle,
    text_layer: TextLayerResult,
    config: V3Config,
) -> RasterLayerResult:
    return extract_raster_layer(multiview, text_layer=text_layer, config=config)


def _detect_families(
    residual_canvas: ResidualCanvasResult,
    text_layer: TextLayerResult,
    raster_layer: RasterLayerResult,
    config: V3Config,
) -> tuple[FamilyProposal, ...]:
    if residual_canvas.canvas is None:
        return ()
    return detect_family_proposals(
        residual_canvas.canvas,
        text_layer=text_layer,
        raster_layer=raster_layer,
        config=config,
    )


def _parse_families(
    residual_canvas: ResidualCanvasResult,
    family_proposals: tuple[FamilyProposal, ...],
    text_layer: TextLayerResult,
    raster_layer: RasterLayerResult,
    config: V3Config,
) -> tuple[DiagramInstance, ...]:
    if residual_canvas.canvas is None or not family_proposals:
        return ()
    return parse_family_proposals(
        residual_canvas.canvas,
        proposals=family_proposals,
        text_layer=text_layer,
        raster_layer=raster_layer,
        config=config,
    )


def _extract_connector_evidence(
    residual_canvas: ResidualCanvasResult,
    instances: tuple[DiagramInstance, ...],
    config: V3Config,
) -> tuple[ConnectorEvidence, ...]:
    if residual_canvas.canvas is None or not instances:
        return ()
    return extract_connector_evidence(
        residual_canvas.canvas,
        instances=instances,
        config=config,
    )


def _generate_ports(
    instances: tuple[DiagramInstance, ...],
    config: V3Config,
) -> tuple[PortSpec, ...]:
    if not instances:
        return ()
    return generate_ports(instances=instances, config=config)


def _attach_connector_evidence(
    connector_evidence: tuple[ConnectorEvidence, ...],
    ports: tuple[PortSpec, ...],
    config: V3Config,
) -> tuple[tuple[PrimitiveConnectorCandidate, ...], tuple[UnattachedConnectorEvidence, ...]]:
    if not connector_evidence or not ports:
        return (), ()
    return attach_connector_evidence(
        connector_evidence=connector_evidence,
        ports=ports,
        config=config,
    )


def _resolve_style_tokens(
    residual_canvas: ResidualCanvasResult,
    instances: tuple[DiagramInstance, ...],
    config: V3Config,
) -> tuple[StyleToken, ...]:
    del residual_canvas, instances, config
    return ()


def _build_residual_canvas(
    multiview: MultiViewBundle,
    text_layer: TextLayerResult,
    raster_layer: RasterLayerResult,
) -> ResidualCanvasResult:
    return build_residual_canvas(multiview, text_layer=text_layer, raster_layer=raster_layer)


def _build_residual_regions(
    residual_canvas: ResidualCanvasResult,
    instances: tuple[DiagramInstance, ...],
    config: V3Config,
) -> tuple[ResidualRegion, ...]:
    if instances or not config.preserve_unresolved_residuals or residual_canvas.canvas is None:
        return ()
    return (
        ResidualRegion(
            id="residual:structural_canvas",
            kind=ResidualKind.UNRESOLVED,
            bbox=residual_canvas.canvas.bbox,
            confidence=1.0,
            reason="family_parser_not_implemented",
        ),
    )


def _build_primitive_scene(
    *,
    text_layer: TextLayerResult,
    raster_layer: RasterLayerResult,
    residual_canvas: ResidualCanvasResult,
    instances: tuple[DiagramInstance, ...],
    ports: tuple[PortSpec, ...],
    connector_candidates: tuple[PrimitiveConnectorCandidate, ...],
    unattached_connector_evidence: tuple[UnattachedConnectorEvidence, ...],
    residual_regions: tuple[ResidualRegion, ...],
    config: V3Config,
    ) -> PrimitiveScene:
    return build_primitive_scene(
        text_layer=text_layer,
        raster_layer=raster_layer,
        residual_canvas=residual_canvas,
        instances=instances,
        ports=ports,
        connector_candidates=connector_candidates,
        unattached_connector_evidence=unattached_connector_evidence,
        residual_regions=residual_regions,
        config=config,
    )


def _resolve_connector_candidates(
    connector_candidates: tuple[PrimitiveConnectorCandidate, ...],
    config: V3Config,
) -> tuple[ConnectorSpec, ...]:
    if not connector_candidates:
        return ()
    return resolve_connector_candidates(
        connector_candidates=connector_candidates,
        config=config,
    )
