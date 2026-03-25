from __future__ import annotations

import json

from PIL import Image, ImageDraw

from image_to_editable_ppt.v3.app.convert import convert_image
from image_to_editable_ppt.v3.connectors import attach_connector_evidence
from image_to_editable_ppt.v3.core.enums import ConnectorKind, ConnectorOrientation, PortSide
from image_to_editable_ppt.v3.core.types import BBox, Point
from image_to_editable_ppt.v3.diagnostics import run_v3_debug
from image_to_editable_ppt.v3.ir.models import ConnectorEvidence


def test_primitive_scene_contains_ports_and_connector_candidates() -> None:
    result = convert_image(make_arrow_flow_image())

    scene = result.slide_ir.primitive_scene
    assert scene is not None
    assert scene.nodes
    assert scene.containers
    assert scene.ports
    assert scene.connector_candidates
    assert all(candidate.start_attachment is not None for candidate in scene.connector_candidates)
    assert all(candidate.end_attachment is not None for candidate in scene.connector_candidates)
    assert result.slide_ir.connector_candidates == scene.connector_candidates


def test_port_generation_creates_four_ports_per_owner() -> None:
    result = convert_image(make_connected_flow_image())

    scene = result.slide_ir.primitive_scene
    assert scene is not None
    assert scene.nodes
    owner_ports = [port for port in scene.ports if port.owner_id == scene.nodes[0].id]

    assert len(owner_ports) == 4
    assert {port.side for port in owner_ports} == {
        PortSide.TOP,
        PortSide.RIGHT,
        PortSide.BOTTOM,
        PortSide.LEFT,
    }


def test_unattached_connector_evidence_is_retained_with_reason() -> None:
    result = convert_image(make_connected_flow_image())
    scene = result.slide_ir.primitive_scene
    assert scene is not None

    candidates, unattached = attach_connector_evidence(
        connector_evidence=(
            ConnectorEvidence(
                id="connector_evidence:synthetic_unattached",
                kind=ConnectorKind.ORTHOGONAL,
                orientation=ConnectorOrientation.HORIZONTAL,
                bbox=BBox(30.0, 132.0, 220.0, 134.0),
                confidence=0.74,
                path_points=(Point(30.0, 133.0), Point(220.0, 133.0)),
                source="test",
                provenance=("test:phase5",),
            ),
        ),
        ports=scene.ports,
        config=result.config,
    )

    assert candidates == ()
    assert unattached
    assert unattached[0].reason == "no_compatible_ports_near_either_endpoint"


def test_family_instance_maps_to_primitive_scene_nodes_containers_and_texts() -> None:
    result = convert_image(make_connected_flow_image())

    scene = result.slide_ir.primitive_scene
    instance = result.slide_ir.diagram_instances[0]
    assert scene is not None
    assert {item.id for item in scene.nodes}.issuperset({item.id for item in instance.nodes})
    assert {item.id for item in scene.containers}.issuperset({item.id for item in instance.containers})
    assert any(text.owner_ids for text in scene.texts)


def test_debug_runner_writes_primitive_scene_and_attached_connector_artifacts(tmp_path) -> None:
    run = run_v3_debug(make_arrow_flow_image(), output_dir=tmp_path / "debug")

    assert run.artifacts.primitive_scene_json.exists()
    assert run.artifacts.attached_connectors_json.exists()
    assert run.artifacts.overlay_ports_png.exists()
    assert run.artifacts.overlay_primitives_png.exists()
    assert run.artifacts.overlay_attached_connectors_png.exists()

    primitive_payload = json.loads(run.artifacts.primitive_scene_json.read_text(encoding="utf-8"))
    attached_payload = json.loads(run.artifacts.attached_connectors_json.read_text(encoding="utf-8"))
    assert primitive_payload["primitive_scene"]["ports"]
    assert attached_payload["connector_candidates"]


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

