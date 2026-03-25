from __future__ import annotations

from PIL import Image
import pytest

from image_to_editable_ppt.v3.app.config import V3Config
from image_to_editable_ppt.v3.app.convert import convert_image
from image_to_editable_ppt.v3.core.contracts import ContractViolationError
from image_to_editable_ppt.v3.core.enums import BranchKind, ConnectorKind, DiagramFamily, NodeKind, ResidualKind, StageName
from image_to_editable_ppt.v3.core.types import BBox, ImageSize
from image_to_editable_ppt.v3.ir.models import ConnectorSpec, DiagramInstance, DiagramNode, SlideIR
from image_to_editable_ppt.v3.ir.validate import validate_multiview_bundle, validate_slide_ir
from image_to_editable_ppt.v3.preprocessing.multiview import build_multiview_bundle


def test_multiview_bundle_creates_required_branches() -> None:
    image = Image.new("RGB", (48, 30), "white")

    bundle = build_multiview_bundle(image)

    validate_multiview_bundle(bundle)
    assert set(bundle.branches) == {
        BranchKind.RGB,
        BranchKind.STYLE,
        BranchKind.TEXT,
        BranchKind.STRUCTURE,
        BranchKind.STRUCTURAL_CANVAS,
    }
    assert bundle.branch(BranchKind.STRUCTURAL_CANVAS).soft_mask is not None
    assert bundle.branch(BranchKind.TEXT).image.shape == (30, 48)


def test_v3_config_supports_family_toggle() -> None:
    config = V3Config(enabled_families=frozenset({DiagramFamily.BLOCK_FLOW, DiagramFamily.CYCLE}))

    assert config.family_enabled(DiagramFamily.BLOCK_FLOW)
    assert not config.family_enabled(DiagramFamily.SWIMLANE)

    updated = config.with_family(DiagramFamily.SWIMLANE, enabled=True)
    assert updated.family_enabled(DiagramFamily.SWIMLANE)
    assert config != updated


def test_slide_ir_validation_rejects_unknown_connector_endpoint() -> None:
    slide_ir = SlideIR(
        image_size=ImageSize(width=120, height=80),
        diagram_instances=(
            DiagramInstance(
                id="instance-1",
                family=DiagramFamily.BLOCK_FLOW,
                confidence=0.9,
                bbox=BBox(10.0, 10.0, 60.0, 40.0),
                nodes=(
                    DiagramNode(
                        id="node-1",
                        kind=NodeKind.BOX,
                        bbox=BBox(10.0, 10.0, 60.0, 40.0),
                    ),
                ),
                source_proposal_ids=(),
            ),
        ),
        connectors=(
            ConnectorSpec(
                id="connector-1",
                kind=ConnectorKind.ARROW,
                confidence=0.8,
                source_instance_id="instance-1",
                target_node_id="missing-node",
            ),
        ),
    )

    with pytest.raises(ContractViolationError):
        validate_slide_ir(slide_ir)


def test_placeholder_pipeline_returns_explicit_residual() -> None:
    image = Image.new("RGB", (96, 64), "white")

    result = convert_image(image)

    assert result.slide_ir.diagram_instances == ()
    assert result.slide_ir.family_proposals == ()
    assert result.slide_ir.text_layer is not None
    assert result.slide_ir.raster_layer is not None
    assert result.slide_ir.residual_canvas is not None
    assert len(result.slide_ir.residual_regions) == 1
    residual = result.slide_ir.residual_regions[0]
    assert residual.kind is ResidualKind.UNRESOLVED
    assert residual.reason == "family_parser_not_implemented"
    assert [record.stage for record in result.stage_records] == [
        StageName.MULTIVIEW,
        StageName.TEXT_SPLIT,
        StageName.RASTER_SPLIT,
        StageName.RESIDUAL_CANVAS,
        StageName.FAMILY_DETECT,
        StageName.FAMILY_PARSE,
        StageName.CONNECTOR_EVIDENCE,
        StageName.STYLE_RESOLVE,
        StageName.COMPOSE,
    ]
