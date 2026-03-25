from __future__ import annotations

import json

from PIL import Image, ImageDraw

from image_to_editable_ppt.v3.app.config import V3Config
from image_to_editable_ppt.v3.app.convert import convert_image
from image_to_editable_ppt.v3.core.enums import ConnectorOrientation, DiagramFamily
from image_to_editable_ppt.v3.diagnostics import run_v3_debug
from image_to_editable_ppt.v3.preprocessing import build_multiview_bundle, build_residual_canvas
from image_to_editable_ppt.v3.raster import extract_raster_layer
from image_to_editable_ppt.v3.text import extract_text_layer
from image_to_editable_ppt.v3.families import detect_family_proposals, parse_family_proposals


def test_debug_runner_writes_json_and_overlay_artifacts(tmp_path) -> None:
    run = run_v3_debug(make_arrow_flow_image(), output_dir=tmp_path / "debug")

    assert run.artifacts.family_proposals_json.exists()
    assert run.artifacts.diagram_instances_json.exists()
    assert run.artifacts.connector_evidence_json.exists()
    assert run.artifacts.overlay_proposals_png.exists()
    assert run.artifacts.overlay_instances_png.exists()
    assert run.artifacts.overlay_connector_evidence_png.exists()

    proposals_payload = json.loads(run.artifacts.family_proposals_json.read_text(encoding="utf-8"))
    instances_payload = json.loads(run.artifacts.diagram_instances_json.read_text(encoding="utf-8"))
    connector_payload = json.loads(run.artifacts.connector_evidence_json.read_text(encoding="utf-8"))
    assert proposals_payload["family_proposals"]
    assert instances_payload["diagram_instances"]
    assert connector_payload["connector_evidence"]


def test_detector_splits_spatially_separated_flow_clusters() -> None:
    bundle = build_multiview_bundle(make_two_flow_clusters_image())
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

    assert len(proposals) >= 2
    assert {proposal.family for proposal in proposals} == {DiagramFamily.ORTHOGONAL_FLOW}


def test_parser_separates_nodes_and_container_for_orthogonal_flow() -> None:
    result = convert_image(make_connected_flow_image())

    assert result.slide_ir.diagram_instances
    instance = result.slide_ir.diagram_instances[0]
    assert len(instance.nodes) >= 2
    assert len(instance.containers) >= 1
    assert instance.containers[0].member_node_ids


def test_textless_node_fallback_is_allowed_but_low_confidence() -> None:
    result = convert_image(make_textless_box_pair_image())

    instance = result.slide_ir.diagram_instances[0]
    assert instance.nodes
    assert any(node.confidence < 0.7 for node in instance.nodes)


def test_connector_evidence_captures_orthogonal_segments_and_arrowhead_hint() -> None:
    result = convert_image(make_arrow_flow_image())

    assert result.slide_ir.connector_evidence
    assert any(evidence.orientation is ConnectorOrientation.HORIZONTAL for evidence in result.slide_ir.connector_evidence)
    assert any(evidence.arrowhead_end or evidence.arrowhead_start for evidence in result.slide_ir.connector_evidence)
    assert any(evidence.start_nearby_node_ids or evidence.end_nearby_node_ids for evidence in result.slide_ir.connector_evidence)


def make_arrow_flow_image() -> Image.Image:
    image = Image.new("RGB", (320, 150), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((18, 42, 96, 96), outline="black", width=2)
    draw.rectangle((206, 42, 284, 96), outline="black", width=2)
    draw.line((96, 69, 170, 69), fill="black", width=2)
    draw.line((170, 69, 186, 63), fill="black", width=2)
    draw.line((170, 69, 186, 75), fill="black", width=2)
    draw.text((38, 58), "Source", fill="black")
    draw.text((224, 58), "Sink", fill="black")
    return image


def make_connected_flow_image() -> Image.Image:
    image = Image.new("RGB", (260, 150), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((18, 42, 96, 96), outline="black", width=2)
    draw.rectangle((164, 42, 242, 96), outline="black", width=2)
    draw.line((96, 69, 164, 69), fill="black", width=2)
    draw.text((38, 58), "Source", fill="black")
    draw.text((182, 58), "Sink", fill="black")
    return image


def make_two_flow_clusters_image() -> Image.Image:
    image = Image.new("RGB", (280, 160), "white")
    draw = ImageDraw.Draw(image)
    for offset_x in (0, 148):
        draw.rectangle((18 + offset_x, 44, 66 + offset_x, 90), outline="black", width=2)
        draw.rectangle((86 + offset_x, 44, 134 + offset_x, 90), outline="black", width=2)
        draw.line((66 + offset_x, 67, 86 + offset_x, 67), fill="black", width=2)
    return image


def make_textless_box_pair_image() -> Image.Image:
    image = Image.new("RGB", (220, 130), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 36, 82, 88), outline="black", width=2)
    draw.rectangle((132, 36, 194, 88), outline="black", width=2)
    draw.line((82, 62, 132, 62), fill="black", width=2)
    return image
