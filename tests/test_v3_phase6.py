from __future__ import annotations

from dataclasses import replace
import json

from PIL import Image, ImageDraw
import pytest

from image_to_editable_ppt.v3.app.config import V3Config
from image_to_editable_ppt.v3.app.convert import convert_image
from image_to_editable_ppt.v3.connectors import resolve_connector_candidates
from image_to_editable_ppt.v3.core.contracts import ContractViolationError
from image_to_editable_ppt.v3.core.enums import ConnectorKind, PortOwnerKind, PortSide, StageName
from image_to_editable_ppt.v3.core.types import BBox, Point
from image_to_editable_ppt.v3.diagnostics import run_v3_debug
from image_to_editable_ppt.v3.emit import build_emit_scene
from image_to_editable_ppt.v3.ir.models import ConnectorAttachment, PrimitiveConnectorCandidate
from image_to_editable_ppt.v3.ir.validate import validate_slide_ir


def test_connector_resolve_preserves_owner_port_and_arrowhead_fields() -> None:
    candidate = PrimitiveConnectorCandidate(
        id="connector_candidate:manual",
        kind=ConnectorKind.ARROW,
        bbox=BBox(10.0, 10.0, 80.0, 40.0),
        confidence=0.88,
        source_evidence_id="connector_evidence:manual",
        path_points=(Point(12.0, 20.0), Point(48.0, 20.0), Point(76.0, 20.0)),
        start_attachment=ConnectorAttachment(
            port_id="node-1:port:right",
            owner_id="node-1",
            owner_kind=PortOwnerKind.NODE,
            side=PortSide.RIGHT,
            point=Point(12.0, 20.0),
            distance=1.0,
            confidence=0.91,
            source="test",
            provenance=("test:phase6",),
        ),
        end_attachment=ConnectorAttachment(
            port_id="container-1:port:left",
            owner_id="container-1",
            owner_kind=PortOwnerKind.CONTAINER,
            side=PortSide.LEFT,
            point=Point(76.0, 20.0),
            distance=1.5,
            confidence=0.83,
            source="test",
            provenance=("test:phase6",),
        ),
        arrowhead_end=True,
        source="test",
        provenance=("test:phase6",),
    )

    solved = resolve_connector_candidates(connector_candidates=(candidate,), config=V3Config())

    assert len(solved) == 1
    connector = solved[0]
    assert connector.source_owner_id == "node-1"
    assert connector.source_owner_kind is PortOwnerKind.NODE
    assert connector.target_owner_id == "container-1"
    assert connector.target_owner_kind is PortOwnerKind.CONTAINER
    assert connector.source_port_id == "node-1:port:right"
    assert connector.target_port_id == "container-1:port:left"
    assert connector.path_points == candidate.path_points
    assert connector.arrowhead_start is False
    assert connector.arrowhead_end is True
    assert connector.source_candidate_id == candidate.id
    assert connector.source_evidence_id == candidate.source_evidence_id
    assert connector.source == "phase6_connector_resolve"


def test_connector_resolve_skips_same_owner_candidates() -> None:
    candidate = PrimitiveConnectorCandidate(
        id="connector_candidate:same-owner",
        kind=ConnectorKind.LINE,
        bbox=BBox(0.0, 0.0, 20.0, 20.0),
        confidence=0.7,
        source_evidence_id="connector_evidence:same-owner",
        path_points=(Point(1.0, 10.0), Point(19.0, 10.0)),
        start_attachment=ConnectorAttachment(
            port_id="node-1:port:left",
            owner_id="node-1",
            owner_kind=PortOwnerKind.NODE,
            side=PortSide.LEFT,
            point=Point(1.0, 10.0),
            distance=0.0,
            confidence=0.8,
            source="test",
            provenance=("test:phase6",),
        ),
        end_attachment=ConnectorAttachment(
            port_id="node-1:port:right",
            owner_id="node-1",
            owner_kind=PortOwnerKind.NODE,
            side=PortSide.RIGHT,
            point=Point(19.0, 10.0),
            distance=0.0,
            confidence=0.8,
            source="test",
            provenance=("test:phase6",),
        ),
        source="test",
        provenance=("test:phase6",),
    )

    solved = resolve_connector_candidates(connector_candidates=(candidate,), config=V3Config())

    assert solved == ()


def test_convert_stage_records_include_connector_resolve() -> None:
    result = convert_image(make_synthetic_orthogonal_flow_image())

    stages = [record.stage for record in result.stage_records]
    assert StageName.CONNECTOR_ATTACH in stages
    assert StageName.CONNECTOR_RESOLVE in stages
    assert StageName.STYLE_RESOLVE in stages
    assert stages.index(StageName.CONNECTOR_ATTACH) < stages.index(StageName.CONNECTOR_RESOLVE)
    assert stages.index(StageName.CONNECTOR_RESOLVE) < stages.index(StageName.STYLE_RESOLVE)
    assert result.slide_ir.connectors


def test_validate_slide_ir_rejects_unknown_solved_connector_port() -> None:
    result = convert_image(make_synthetic_orthogonal_flow_image())
    connector = result.slide_ir.connectors[0]

    with pytest.raises(ContractViolationError, match="unknown source port"):
        validate_slide_ir(
            replace(
                result.slide_ir,
                connectors=(replace(connector, source_port_id="missing-port"),),
            )
        )


def test_validate_slide_ir_rejects_same_owner_solved_connector() -> None:
    result = convert_image(make_synthetic_orthogonal_flow_image())
    connector = result.slide_ir.connectors[0]
    scene = result.slide_ir.primitive_scene
    assert scene is not None

    same_owner_target_port = next(
        port.id
        for port in scene.ports
        if port.owner_id == connector.source_owner_id and port.id != connector.source_port_id
    )

    with pytest.raises(ContractViolationError, match="same owner"):
        validate_slide_ir(
            replace(
                result.slide_ir,
                connectors=(
                    replace(
                        connector,
                        target_owner_id=connector.source_owner_id,
                        target_owner_kind=connector.source_owner_kind,
                        target_port_id=same_owner_target_port,
                    ),
                ),
            )
        )


def test_validate_slide_ir_rejects_empty_solved_connector_path() -> None:
    result = convert_image(make_synthetic_orthogonal_flow_image())
    connector = result.slide_ir.connectors[0]

    with pytest.raises(ContractViolationError, match="at least two path points"):
        validate_slide_ir(
            replace(
                result.slide_ir,
                connectors=(replace(connector, path_points=(connector.path_points[0],)),),
            )
        )


def test_emit_adapter_builds_expected_counts_for_synthetic_orthogonal_flow() -> None:
    result = convert_image(make_synthetic_orthogonal_flow_image())
    scene = result.slide_ir.primitive_scene
    assert scene is not None

    emit_scene = build_emit_scene(
        primitive_scene=scene,
        connectors=result.slide_ir.connectors,
    )

    assert emit_scene.coordinate_space == "image_space"
    assert len(emit_scene.shapes) == 3
    assert len(emit_scene.texts) == 3
    assert len(emit_scene.connectors) == 2
    assert len(emit_scene.residuals) == 0


def test_debug_runner_writes_solved_connector_and_emit_scene_artifacts(tmp_path) -> None:
    run = run_v3_debug(make_synthetic_orthogonal_flow_image(), output_dir=tmp_path / "debug")

    assert run.artifacts.solved_connectors_json.exists()
    assert run.artifacts.emit_scene_json.exists()
    assert run.artifacts.overlay_solved_connectors_png.exists()
    assert run.artifacts.overlay_emit_scene_png.exists()

    solved_payload = json.loads(run.artifacts.solved_connectors_json.read_text(encoding="utf-8"))
    emit_payload = json.loads(run.artifacts.emit_scene_json.read_text(encoding="utf-8"))
    summary_payload = json.loads(run.artifacts.debug_summary_json.read_text(encoding="utf-8"))

    assert solved_payload["connectors"]
    assert emit_payload["emit_scene"]["connectors"]
    assert summary_payload["connector_resolve"]["solved_connectors"] == len(solved_payload["connectors"])
    assert summary_payload["emit_adapter"]["connectors"] == len(emit_payload["emit_scene"]["connectors"])


def make_synthetic_orthogonal_flow_image() -> Image.Image:
    image = Image.new("RGB", (260, 150), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((18, 42, 96, 96), outline="black", width=2)
    draw.rectangle((164, 42, 242, 96), outline="black", width=2)
    draw.line((96, 69, 164, 69), fill="black", width=2)
    draw.text((38, 58), "Source", fill="black")
    draw.text((182, 58), "Sink", fill="black")
    return image
