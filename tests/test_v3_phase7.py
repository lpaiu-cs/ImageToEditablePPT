from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from image_to_editable_ppt.ml import eval_detector, infer_detector, train_detector
from image_to_editable_ppt.ml.adapter import AnnotationMLAdapter, DetectorModelOutput
from image_to_editable_ppt.ml.annotation_schema import (
    AnnotationBBox,
    AnnotationConnectorCandidate,
    AnnotationConnectorEndpoint,
    AnnotationContainer,
    AnnotationDiagramInstance,
    AnnotationFamilyProposal,
    AnnotationImageSize,
    AnnotationNode,
    AnnotationPoint,
    AnnotationPort,
    AnnotationPrimitiveText,
    AnnotationResidual,
    AnnotationSchemaError,
    AnnotationTextRegion,
    AnnotationUnattachedConnectorEvidence,
    DetectorAnnotationDocument,
    SCHEMA_VERSION,
)
from image_to_editable_ppt.ml.metrics import evaluate_detector_predictions
from image_to_editable_ppt.v3.core.enums import (
    ConnectorKind,
    ContainerKind,
    DiagramFamily,
    NodeKind,
    PortOwnerKind,
    PortSide,
    ResidualKind,
    TextRegionRole,
)
from image_to_editable_ppt.v3.ir.models import (
    DiagramContainer,
    DiagramInstance,
    DiagramNode,
    FamilyProposal,
    PortSpec,
    PrimitiveConnectorCandidate,
    PrimitiveContainer,
    PrimitiveNode,
    PrimitiveResidual,
    PrimitiveText,
    TextRegion,
    UnattachedConnectorEvidence,
)
from image_to_editable_ppt.v3.ir.validate import validate_slide_ir


def make_synthetic_model_output() -> DetectorModelOutput:
    node_a = AnnotationNode(
        id="node:a",
        kind=NodeKind.BOX,
        bbox=AnnotationBBox(10.0, 10.0, 50.0, 40.0),
        confidence=0.9,
        label="Start",
        text_region_ids=("text:a",),
    )
    node_b = AnnotationNode(
        id="node:b",
        kind=NodeKind.ROUNDED_BOX,
        bbox=AnnotationBBox(120.0, 10.0, 160.0, 40.0),
        confidence=0.8,
    )
    container = AnnotationContainer(
        id="container:flow",
        kind=ContainerKind.FLOW_CLUSTER,
        bbox=AnnotationBBox(5.0, 5.0, 170.0, 45.0),
        confidence=0.7,
        member_node_ids=("node:a", "node:b"),
    )
    return DetectorModelOutput(
        image_id="synthetic:phase7",
        image_size=AnnotationImageSize(width=200, height=100),
        family_predictions=(
            AnnotationFamilyProposal(
                id="family:orthogonal_flow:0",
                family=DiagramFamily.ORTHOGONAL_FLOW,
                confidence=0.75,
                focus_bbox=AnnotationBBox(0.0, 0.0, 200.0, 100.0),
                evidence=("test:synthetic",),
            ),
        ),
        node_predictions=(node_a, node_b),
        container_predictions=(container,),
        text_predictions=(
            AnnotationTextRegion(
                id="text:a",
                bbox=AnnotationBBox(15.0, 18.0, 45.0, 30.0),
                confidence=0.95,
                role=TextRegionRole.LABEL,
                text="Start",
            ),
        ),
        port_predictions=(
            AnnotationPort(
                id="port:a:right",
                owner_id="node:a",
                owner_kind=PortOwnerKind.NODE,
                side=PortSide.RIGHT,
                point=AnnotationPoint(50.0, 25.0),
                confidence=0.9,
            ),
            AnnotationPort(
                id="port:b:left",
                owner_id="node:b",
                owner_kind=PortOwnerKind.NODE,
                side=PortSide.LEFT,
                point=AnnotationPoint(120.0, 25.0),
                confidence=0.9,
            ),
        ),
        connector_predictions=(
            AnnotationConnectorCandidate(
                id="connector:a-b",
                kind=ConnectorKind.ARROW,
                bbox=AnnotationBBox(50.0, 20.0, 120.0, 30.0),
                confidence=0.85,
                source_evidence_id="evidence:a-b",
                path_points=(AnnotationPoint(50.0, 25.0), AnnotationPoint(120.0, 25.0)),
                start_endpoint=AnnotationConnectorEndpoint(
                    point=AnnotationPoint(50.0, 25.0),
                    owner_id="node:a",
                    owner_kind=PortOwnerKind.NODE,
                    side=PortSide.RIGHT,
                ),
                end_endpoint=AnnotationConnectorEndpoint(
                    point=AnnotationPoint(120.0, 25.0),
                    owner_id="node:b",
                    owner_kind=PortOwnerKind.NODE,
                    side=PortSide.LEFT,
                ),
                arrowhead_end=True,
            ),
        ),
        residual_predictions=(
            AnnotationResidual(
                id="residual:bottom",
                kind=ResidualKind.UNRESOLVED,
                bbox=AnnotationBBox(10.0, 60.0, 190.0, 90.0),
                confidence=0.4,
                reason="unparsed strokes",
            ),
        ),
    )


def test_annotation_document_json_roundtrip_preserves_payload() -> None:
    adapter = AnnotationMLAdapter()
    document = adapter.from_model_output(make_synthetic_model_output())

    payload = json.loads(json.dumps(document.to_dict()))
    restored = DetectorAnnotationDocument.from_dict(payload)

    assert restored == document
    assert restored.schema_version == SCHEMA_VERSION
    assert restored.metadata["bootstrap_stage"] == "phase7_ml_experiment_bootstrap"


def test_annotation_schema_rejects_contract_violations() -> None:
    with pytest.raises(AnnotationSchemaError):
        AnnotationBBox(10.0, 10.0, 10.0, 40.0)

    with pytest.raises(AnnotationSchemaError):
        AnnotationNode(
            id="node:bad",
            kind=NodeKind.BOX,
            bbox=AnnotationBBox(0.0, 0.0, 10.0, 10.0),
            confidence=1.5,
        )

    with pytest.raises(AnnotationSchemaError):
        AnnotationFamilyProposal.from_dict(
            {
                "id": "family:bad",
                "family": "not_a_family",
                "confidence": 0.5,
                "focus_bbox": {"x0": 0.0, "y0": 0.0, "x1": 10.0, "y1": 10.0},
            }
        )

    with pytest.raises(AnnotationSchemaError):
        AnnotationConnectorCandidate(
            id="connector:single-point",
            kind=ConnectorKind.LINE,
            bbox=AnnotationBBox(0.0, 0.0, 10.0, 10.0),
            confidence=0.5,
            source_evidence_id="evidence:x",
            path_points=(AnnotationPoint(1.0, 1.0),),
        )

    with pytest.raises(AnnotationSchemaError):
        AnnotationConnectorCandidate(
            id="connector:endpoints-missing",
            kind=ConnectorKind.LINE,
            bbox=AnnotationBBox(0.0, 0.0, 10.0, 10.0),
            confidence=0.5,
            source_evidence_id="evidence:x",
        )

    with pytest.raises(AnnotationSchemaError):
        AnnotationConnectorEndpoint(
            point=AnnotationPoint(1.0, 1.0),
            owner_id="node:a",
        )


def test_adapter_slide_ir_passes_v3_validation() -> None:
    adapter = AnnotationMLAdapter()
    document = adapter.from_model_output(make_synthetic_model_output())
    slide_ir = adapter.to_slide_ir(document)

    validate_slide_ir(slide_ir)

    assert slide_ir.primitive_scene is not None
    assert slide_ir.connector_candidates == slide_ir.primitive_scene.connector_candidates
    assert [item.id for item in slide_ir.connector_evidence] == ["evidence:a-b"]
    assert len(slide_ir.primitive_scene.nodes) == 2
    assert len(slide_ir.primitive_scene.containers) == 1
    assert len(slide_ir.primitive_scene.residuals) == 1
    candidate = slide_ir.connector_candidates[0]
    assert candidate.start_attachment is not None
    assert candidate.start_attachment.port_id == "port:a:right"
    assert candidate.end_attachment is not None
    assert candidate.end_attachment.port_id == "port:b:left"


def test_adapter_rejects_endpoint_without_matching_port() -> None:
    output = make_synthetic_model_output()
    without_ports = dataclasses.replace(output, port_predictions=())
    adapter = AnnotationMLAdapter()
    document = adapter.from_model_output(without_ports)

    with pytest.raises(AnnotationSchemaError, match="missing AnnotationPort"):
        adapter.to_slide_ir(document)


EXACT_FIELD_ALIGNMENT = (
    (AnnotationFamilyProposal, FamilyProposal),
    (AnnotationTextRegion, TextRegion),
    (AnnotationNode, DiagramNode),
    (AnnotationContainer, DiagramContainer),
    (AnnotationDiagramInstance, DiagramInstance),
    (AnnotationPort, PortSpec),
    (AnnotationPrimitiveText, PrimitiveText),
    (AnnotationResidual, PrimitiveResidual),
    (AnnotationUnattachedConnectorEvidence, UnattachedConnectorEvidence),
)


def test_annotation_schema_field_names_track_v3_ir() -> None:
    for annotation_cls, ir_cls in EXACT_FIELD_ALIGNMENT:
        annotation_fields = {item.name for item in dataclasses.fields(annotation_cls)}
        ir_fields = {item.name for item in dataclasses.fields(ir_cls)}
        assert annotation_fields == ir_fields, (
            f"{annotation_cls.__name__} fields drifted from {ir_cls.__name__}: "
            f"annotation-only={sorted(annotation_fields - ir_fields)}, "
            f"ir-only={sorted(ir_fields - annotation_fields)}"
        )

    for annotation_cls, ir_cls in ((AnnotationNode, PrimitiveNode), (AnnotationContainer, PrimitiveContainer)):
        annotation_fields = {item.name for item in dataclasses.fields(annotation_cls)}
        ir_fields = {item.name for item in dataclasses.fields(ir_cls)}
        assert annotation_fields <= ir_fields
        assert ir_fields - annotation_fields == {"port_ids"}

    candidate_fields = {item.name for item in dataclasses.fields(AnnotationConnectorCandidate)}
    primitive_candidate_fields = {item.name for item in dataclasses.fields(PrimitiveConnectorCandidate)}
    assert candidate_fields - {"start_endpoint", "end_endpoint"} <= primitive_candidate_fields
    assert {"start_attachment", "end_attachment"} <= primitive_candidate_fields


def test_metrics_report_perfect_scores_for_identical_documents() -> None:
    adapter = AnnotationMLAdapter()
    document = adapter.from_model_output(make_synthetic_model_output())

    report = evaluate_detector_predictions(document, document)

    assert report.family_proposals.accuracy == 1.0
    assert report.nodes.f1 == 1.0
    assert report.nodes.true_positive == 2
    assert report.containers.f1 == 1.0
    assert report.connectors.endpoint_accuracy == 1.0
    assert report.connectors.correct_endpoints == 2
    assert report.structural.exact is True


def test_metrics_penalize_wrong_endpoint_attachment() -> None:
    adapter = AnnotationMLAdapter()
    reference = adapter.from_model_output(make_synthetic_model_output())

    swapped = make_synthetic_model_output()
    connector = swapped.connector_predictions[0]
    wrong_end = dataclasses.replace(
        connector,
        end_endpoint=dataclasses.replace(connector.end_endpoint, owner_id="node:a", side=PortSide.RIGHT),
    )
    prediction_output = dataclasses.replace(swapped, connector_predictions=(wrong_end,))
    prediction = adapter.from_model_output(prediction_output)

    report = evaluate_detector_predictions(prediction, reference)

    assert report.connectors.matched == 1
    assert report.connectors.correct_endpoints == 1
    assert report.connectors.endpoint_accuracy == 0.5
    assert report.structural.connectors_exact is False
    assert report.structural.exact is False
    assert report.structural.nodes_exact is True


def test_metrics_count_unmatched_reference_connectors_as_misses() -> None:
    adapter = AnnotationMLAdapter()
    reference = adapter.from_model_output(make_synthetic_model_output())
    without_connectors = dataclasses.replace(
        make_synthetic_model_output(),
        connector_predictions=(),
        port_predictions=(),
    )
    prediction = adapter.from_model_output(without_connectors)

    report = evaluate_detector_predictions(prediction, reference)

    assert report.connectors.matched == 0
    assert report.connectors.endpoint_accuracy == 0.0
    assert report.connectors.endpoint_reference_count == 2
    assert report.structural.exact is False


def test_metrics_penalize_shifted_boxes_and_kind_mismatch() -> None:
    adapter = AnnotationMLAdapter()
    reference = adapter.from_model_output(make_synthetic_model_output())

    shifted = make_synthetic_model_output()
    shifted_nodes = (
        dataclasses.replace(shifted.node_predictions[0], bbox=AnnotationBBox(60.0, 60.0, 100.0, 90.0)),
        dataclasses.replace(shifted.node_predictions[1], kind=NodeKind.SECTION),
    )
    prediction = adapter.from_model_output(dataclasses.replace(shifted, node_predictions=shifted_nodes))

    report = evaluate_detector_predictions(prediction, reference)

    assert report.nodes.true_positive == 0
    assert report.nodes.false_positive == 2
    assert report.nodes.false_negative == 2
    assert report.nodes.f1 == 0.0
    assert report.family_proposals.accuracy == 1.0


def test_metrics_match_each_reference_at_most_once() -> None:
    adapter = AnnotationMLAdapter()
    reference = adapter.from_model_output(make_synthetic_model_output())

    duplicated = make_synthetic_model_output()
    duplicate_node = dataclasses.replace(duplicated.node_predictions[0], id="node:a-duplicate")
    prediction = adapter.from_model_output(
        dataclasses.replace(duplicated, node_predictions=(*duplicated.node_predictions, duplicate_node))
    )

    report = evaluate_detector_predictions(prediction, reference)

    assert report.nodes.true_positive == 2
    assert report.nodes.false_positive == 1
    assert report.nodes.false_negative == 0


def test_infer_cli_writes_annotation_document_and_summary(tmp_path: Path) -> None:
    output_json = tmp_path / "predictions.json"
    summary_json = tmp_path / "summary.json"

    exit_code = infer_detector.main(
        [
            "--image-id",
            "cli:test",
            "--image-width",
            "640",
            "--image-height",
            "480",
            "--output-json",
            str(output_json),
            "--summary-json",
            str(summary_json),
            "--family",
            DiagramFamily.ORTHOGONAL_FLOW.value,
            "--validate-ir",
        ]
    )

    assert exit_code == 0
    document = DetectorAnnotationDocument.from_dict(json.loads(output_json.read_text(encoding="utf-8")))
    assert document.image_id == "cli:test"
    assert len(document.family_proposals) == 1
    summary = json.loads(summary_json.read_text(encoding="utf-8"))
    assert summary["family_proposal_count"] == 1
    assert summary["connector_candidate_count"] == 0


def test_eval_cli_scores_prediction_against_reference(tmp_path: Path) -> None:
    adapter = AnnotationMLAdapter()
    document = adapter.from_model_output(make_synthetic_model_output())
    annotations_json = tmp_path / "annotations.json"
    annotations_json.write_text(json.dumps(document.to_dict()), encoding="utf-8")
    report_json = tmp_path / "report.json"

    exit_code = eval_detector.main(
        [
            "--predictions-json",
            str(annotations_json),
            "--ground-truth-json",
            str(annotations_json),
            "--report-json",
            str(report_json),
        ]
    )

    assert exit_code == 0
    report = json.loads(report_json.read_text(encoding="utf-8"))
    assert report["family_proposals"]["accuracy"] == 1.0
    assert report["nodes"]["f1"] == 1.0
    assert report["containers"]["f1"] == 1.0


def test_train_cli_writes_bootstrap_manifest(tmp_path: Path) -> None:
    adapter = AnnotationMLAdapter()
    document = adapter.from_model_output(make_synthetic_model_output())
    annotations_json = tmp_path / "train_annotations.json"
    annotations_json.write_text(json.dumps(document.to_dict()), encoding="utf-8")
    output_dir = tmp_path / "run"

    exit_code = train_detector.main(
        [
            "--train-annotations",
            str(annotations_json),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    manifest = json.loads((output_dir / "train_detector_run.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "bootstrap_ready"
    assert manifest["config"]["train_annotations"] == str(annotations_json)
