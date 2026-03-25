from __future__ import annotations

from PIL import Image, ImageDraw

from image_to_editable_ppt.v3.app.config import V3Config
from image_to_editable_ppt.v3.app.convert import convert_image
from image_to_editable_ppt.v3.core.enums import DiagramFamily, StageName
from image_to_editable_ppt.v3.families import detect_family_proposals, get_family_registry, iter_enabled_family_definitions, parse_family_proposals
from image_to_editable_ppt.v3.preprocessing import build_multiview_bundle, build_residual_canvas
from image_to_editable_ppt.v3.raster import extract_raster_layer
from image_to_editable_ppt.v3.text import extract_text_layer


def test_family_registry_respects_config_toggle() -> None:
    registry = get_family_registry()
    assert DiagramFamily.ORTHOGONAL_FLOW in registry

    enabled = iter_enabled_family_definitions(V3Config())
    assert tuple(definition.family for definition in enabled) == (DiagramFamily.ORTHOGONAL_FLOW,)

    disabled_config = V3Config().with_family(DiagramFamily.ORTHOGONAL_FLOW, enabled=False)
    assert iter_enabled_family_definitions(disabled_config) == ()


def test_first_family_detector_returns_proposal_with_bbox_and_provenance() -> None:
    bundle = build_multiview_bundle(make_flow_image())
    config = V3Config()
    text_layer = extract_text_layer(bundle, config=config)
    raster_layer = extract_raster_layer(bundle, text_layer=text_layer, config=config)
    residual = build_residual_canvas(bundle, text_layer=text_layer, raster_layer=raster_layer)

    proposals = detect_family_proposals(
        residual.canvas,
        text_layer=text_layer,
        raster_layer=raster_layer,
        config=config,
    )

    assert proposals
    proposal = proposals[0]
    assert proposal.family is DiagramFamily.ORTHOGONAL_FLOW
    assert proposal.focus_bbox is not None
    assert proposal.provenance
    assert proposal.evidence


def test_first_family_parser_returns_minimal_diagram_instance() -> None:
    bundle = build_multiview_bundle(make_flow_image())
    config = V3Config()
    text_layer = extract_text_layer(bundle, config=config)
    raster_layer = extract_raster_layer(bundle, text_layer=text_layer, config=config)
    residual = build_residual_canvas(bundle, text_layer=text_layer, raster_layer=raster_layer)
    proposals = detect_family_proposals(
        residual.canvas,
        text_layer=text_layer,
        raster_layer=raster_layer,
        config=config,
    )

    instances = parse_family_proposals(
        residual.canvas,
        proposals=proposals,
        text_layer=text_layer,
        raster_layer=raster_layer,
        config=config,
    )

    assert instances
    instance = instances[0]
    assert instance.family is DiagramFamily.ORTHOGONAL_FLOW
    assert instance.source_proposal_ids == (proposals[0].id,)
    assert instance.nodes


def test_orchestration_flow_connects_residual_detector_and_parser() -> None:
    result = convert_image(make_flow_image())

    assert result.slide_ir.residual_canvas is not None
    assert result.slide_ir.family_proposals
    assert result.slide_ir.diagram_instances
    assert result.stage_records[4].stage is StageName.FAMILY_DETECT
    assert result.stage_records[5].stage is StageName.FAMILY_PARSE
    assert result.stage_records[4].summary["proposal_count"] >= 1
    assert result.stage_records[5].summary["instance_count"] >= 1


def test_orchestration_respects_family_disable_and_leaves_residual() -> None:
    config = V3Config().with_family(DiagramFamily.ORTHOGONAL_FLOW, enabled=False)

    result = convert_image(make_flow_image(), config=config)

    assert result.slide_ir.family_proposals == ()
    assert result.slide_ir.diagram_instances == ()
    assert len(result.slide_ir.residual_regions) == 1


def make_flow_image() -> Image.Image:
    image = Image.new("RGB", (240, 140), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((18, 34, 92, 84), outline="black", width=2)
    draw.rectangle((146, 34, 220, 84), outline="black", width=2)
    draw.line((92, 59, 118, 59), fill="black", width=2)
    draw.line((118, 59, 118, 59), fill="black", width=2)
    draw.line((118, 59, 146, 59), fill="black", width=2)
    draw.text((34, 49), "Input", fill="black")
    draw.text((160, 49), "Output", fill="black")
    return image
