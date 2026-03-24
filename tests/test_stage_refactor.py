from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
import pytest

from image_to_editable_ppt.config import PipelineConfig
from image_to_editable_ppt.diagnostics import build_recorder
from image_to_editable_ppt.detector import clamp_bbox as detector_clamp_bbox, grow_container_from_text_anchor as detector_grow_container_from_text_anchor
from image_to_editable_ppt.eval_debug import EvalItem, attrition_by_stage, failure_taxonomy, oracle_upper_bound_by_stage, write_eval_debug_artifacts
from image_to_editable_ppt.graph import build_authoring_graph
from image_to_editable_ppt.guides import GuideField
from image_to_editable_ppt.ir import BBox
from image_to_editable_ppt.pipeline import build_elements
from image_to_editable_ppt.reconstructors import build_motif_hypotheses
from image_to_editable_ppt.reconstructors.raster_regions import build_raster_fallback_regions
from image_to_editable_ppt.schema import AuthoringGraph, EmissionRecord, ObjectHypothesis, StageContractError, validate_emission_trace
from image_to_editable_ppt.selection import select_authoring_objects
from image_to_editable_ppt.text import OCRBackend, OCRTextRegion
from image_to_editable_ppt.validation import run_validation_iteration
from image_to_editable_ppt.vlm_parser import DiagramStructure, VLMEdge, VLMNode


class FakeOCRBackend(OCRBackend):
    def __init__(self, regions: list[OCRTextRegion]) -> None:
        self._regions = regions

    def extract(self, image):
        return self._regions


class FakeStructureParser:
    def __init__(self, structure: DiagramStructure) -> None:
        self.structure = structure

    def extract_structure(self, image, *, image_path=None):
        return self.structure


def semantic_fixture():
    image = Image.new("RGB", (320, 200), "white")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((42, 52, 132, 112), radius=16, outline=(24, 78, 128), fill=(220, 235, 248), width=4)
    draw.rounded_rectangle((206, 84, 296, 144), radius=16, outline=(64, 64, 64), fill=(248, 228, 206), width=4)
    draw.line((132, 98, 206, 98), fill=(30, 30, 30), width=4)
    backend = FakeOCRBackend(
        [
            OCRTextRegion(text="Vector Store", bbox=BBox(58.0, 70.0, 118.0, 90.0), confidence=0.98),
            OCRTextRegion(text="Planner", bbox=BBox(228.0, 102.0, 274.0, 122.0), confidence=0.98),
        ]
    )
    parser = FakeStructureParser(
        DiagramStructure(
            nodes=[
                VLMNode("n1", "box", "Vector Store", BBox(620.0, 120.0, 930.0, 420.0)),
                VLMNode("n2", "box", "Planner", BBox(80.0, 640.0, 320.0, 930.0)),
            ],
            edges=[VLMEdge("n1", "n2", "solid_arrow", "retrieves")],
            coordinate_space="normalized_1000",
        )
    )
    return image, backend, parser


def make_hypothesis(
    hypothesis_id: str,
    object_type: str,
    bbox: BBox,
    *,
    score_total: float = 1.0,
    source_ids: list[str] | None = None,
    guide_ids: list[str] | None = None,
    assigned_vlm_ids: list[str] | None = None,
    assigned_text_ids: list[str] | None = None,
) -> ObjectHypothesis:
    return ObjectHypothesis(
        id=hypothesis_id,
        kind=object_type,
        bbox=bbox,
        score_total=score_total,
        score_terms={"score": score_total},
        source_ids=source_ids or [f"rect-candidate:{hypothesis_id}"],
        provenance={"source_ids": source_ids or [f"rect-candidate:{hypothesis_id}"]},
        guide_ids=guide_ids or [],
        assigned_vlm_ids=assigned_vlm_ids or [hypothesis_id],
        assigned_text_ids=assigned_text_ids or [],
        object_type=object_type,
        candidate_id=(source_ids or [f"rect-candidate:{hypothesis_id}"])[0],
    )


def empty_guide_field() -> GuideField:
    return GuideField(
        id="guide-field",
        kind="guide_field",
        bbox=None,
        score_total=0.0,
        score_terms={"guides": 0.0},
        source_ids=["guide-field"],
        provenance={"source_ids": ["guide-field"]},
    )


def test_semantic_pipeline_exposes_stage_artifacts_and_provenance() -> None:
    image, backend, parser = semantic_fixture()
    result = build_elements(
        image,
        config=PipelineConfig(semantic_fallback_to_legacy=False),
        structure_parser=parser,
        ocr_backend=backend,
    )

    assert result.pipeline_mode == "semantic"
    assert set(result.stage_artifacts) == {
        "00_text",
        "01_geometry_raw",
        "02_guides",
        "03_objects",
        "04_motifs",
        "05_selection",
        "06_graph",
        "07_emit",
    }
    object_hypothesis = result.stage_artifacts["03_objects"]["hypotheses"][0]
    emission_record = result.stage_artifacts["07_emit"]["emission_records"][0]
    assert object_hypothesis.id
    assert object_hypothesis.source_ids
    assert object_hypothesis.assigned_vlm_ids
    assert object_hypothesis.score_terms
    assert emission_record.emitted_element_id
    assert emission_record.hypothesis_ids
    assert emission_record.provenance["hypothesis_ids"] == emission_record.hypothesis_ids


def test_diagnostics_recorder_creates_stage_directories_and_files(tmp_path: Path) -> None:
    image, backend, parser = semantic_fixture()
    recorder = build_recorder(enabled=True, run_id="run-1", slide_id="slide-a", root_dir=tmp_path)
    result = build_elements(
        image,
        config=PipelineConfig(
            semantic_fallback_to_legacy=False,
            inclusion_confidence=0.95,
            raster_fallback_confidence_threshold=0.95,
        ),
        structure_parser=parser,
        ocr_backend=backend,
        diagnostics=recorder,
    )

    assert result.diagnostics_dir == tmp_path / "run-1" / "slide-a"
    for stage in ("00_text", "01_geometry_raw", "02_guides", "03_objects", "04_motifs", "05_selection", "06_graph", "07_emit"):
        stage_dir = result.diagnostics_dir / stage
        assert stage_dir.exists()
        assert (stage_dir / "summary.json").exists()
        assert any(path.suffix in {".json", ".jsonl", ".png"} for path in stage_dir.iterdir())


def test_noop_diagnostics_recorder_leaves_filesystem_unchanged(tmp_path: Path) -> None:
    image, backend, parser = semantic_fixture()
    root_dir = tmp_path / "diagnostics"
    recorder = build_recorder(enabled=False, run_id="noop", slide_id="slide-a", root_dir=root_dir)
    result = build_elements(
        image,
        config=PipelineConfig(
            semantic_fallback_to_legacy=False,
            inclusion_confidence=0.95,
            raster_fallback_confidence_threshold=0.95,
        ),
        structure_parser=parser,
        ocr_backend=backend,
        diagnostics=recorder,
    )

    assert result.diagnostics_dir is None
    assert not root_dir.exists()


def test_grow_fallback_remains_explicit_when_geometry_candidates_are_missing() -> None:
    image = Image.new("RGB", (320, 200), "white")
    backend = FakeOCRBackend([OCRTextRegion(text="Lonely Node", bbox=BBox(92.0, 92.0, 180.0, 112.0), confidence=0.99)])
    parser = FakeStructureParser(
        DiagramStructure(
            nodes=[VLMNode("n1", "box", "Lonely Node", BBox(200.0, 320.0, 720.0, 760.0))],
            edges=[],
            coordinate_space="normalized_1000",
        )
    )

    result = build_elements(
        image,
        config=PipelineConfig(semantic_fallback_to_legacy=False),
        structure_parser=parser,
        ocr_backend=backend,
    )

    fallback_hypotheses = result.stage_artifacts["03_objects"]["fallback_hypotheses"]
    assert fallback_hypotheses
    assert all(hypothesis.fallback for hypothesis in fallback_hypotheses)
    assert all("grow_fallback" in hypothesis.source_ids for hypothesis in fallback_hypotheses)


def test_eval_debug_reports_stage_oracle_failure_taxonomy_and_attrition(tmp_path: Path) -> None:
    ground_truth = [
        EvalItem("gt-a", "rect", BBox(0.0, 0.0, 40.0, 40.0)),
        EvalItem("gt-b", "rect", BBox(50.0, 0.0, 90.0, 40.0)),
        EvalItem("gt-c", "rect", BBox(100.0, 0.0, 140.0, 40.0)),
    ]
    stage_artifacts = {
        "01_geometry_raw": [
            EvalItem("cand-a", "rect", BBox(0.0, 0.0, 40.0, 40.0)),
            EvalItem("cand-b", "rect", BBox(50.0, 0.0, 90.0, 40.0)),
            EvalItem("cand-c", "rect", BBox(100.0, 0.0, 140.0, 40.0)),
        ],
        "07_emit": [
            EvalItem("pred-merged", "rect", BBox(0.0, 0.0, 90.0, 40.0)),
            EvalItem("pred-wrong-type", "line", BBox(100.0, 0.0, 140.0, 40.0)),
            EvalItem("pred-hallucinated", "rect", BBox(180.0, 0.0, 220.0, 40.0)),
        ],
    }

    oracle = oracle_upper_bound_by_stage(ground_truth, stage_artifacts)
    assert oracle["01_geometry_raw"]["recoverable_count"] == 3
    assert oracle["07_emit"]["recoverable_count"] == 0

    failures = failure_taxonomy(ground_truth, stage_artifacts["07_emit"])
    gt_tags = {row["gt_id"]: row["tag"] for row in failures["ground_truth"]}
    pred_tags = {row["prediction_id"]: row["tag"] for row in failures["predictions"]}
    assert gt_tags["gt-a"] in {"merged_into_parent", "merged_siblings"}
    assert gt_tags["gt-b"] in {"merged_into_parent", "merged_siblings"}
    assert gt_tags["gt-c"] == "wrong_type"
    assert pred_tags["pred-hallucinated"] == "hallucinated_prediction"

    attrition = attrition_by_stage(ground_truth, stage_artifacts)
    lost = {row["gt_id"]: row["lost_at"] for row in attrition["ground_truth"]}
    assert lost["gt-a"] == "07_emit"
    assert lost["gt-b"] == "07_emit"
    assert lost["gt-c"] == "07_emit"

    eval_dir = tmp_path / "eval"
    write_eval_debug_artifacts(eval_dir, ground_truth, stage_artifacts)
    assert (eval_dir / "oracle_by_stage.json").exists()
    assert (eval_dir / "failure_taxonomy.json").exists()
    assert (eval_dir / "attrition_by_stage.json").exists()
    oracle_payload = json.loads((eval_dir / "oracle_by_stage.json").read_text(encoding="utf-8"))
    assert oracle_payload["status"] == "ok"
    assert oracle_payload["stages"]["01_geometry_raw"]["recoverable_count"] == 3


def test_write_eval_debug_artifacts_marks_unavailable_without_gt(tmp_path: Path) -> None:
    eval_dir = tmp_path / "eval"
    payload = write_eval_debug_artifacts(eval_dir, None, {})

    assert payload["status"] == "unavailable"
    oracle_payload = json.loads((eval_dir / "oracle_by_stage.json").read_text(encoding="utf-8"))
    assert oracle_payload["status"] == "unavailable"
    assert oracle_payload["gt_available"] is False
    assert oracle_payload["reason"] == "ground_truth_annotations_missing"


def test_raster_fallback_emits_real_regions_and_diagnostics(tmp_path: Path) -> None:
    image = Image.new("RGB", (320, 200), "white")
    hypotheses = [
        make_hypothesis(
            "fallback-low",
            "container",
            BBox(60.0, 60.0, 180.0, 140.0),
            score_total=0.62,
            source_ids=["grow_fallback", "rect-candidate:fallback-low"],
        )
    ]

    raster = build_raster_fallback_regions(
        image,
        hypotheses,
        PipelineConfig(
            inclusion_confidence=0.95,
            raster_fallback_confidence_threshold=0.95,
        ),
    )

    assert any(element.kind == "raster_region" for element in raster.elements)
    fallback_regions = raster.regions
    emission_records = raster.emission_records
    assert fallback_regions
    raster_record = next(record for record in emission_records if record.object_type == "raster_region")
    assert raster_record.provenance["fallback_region_ids"] == [fallback_regions[0].id]
    assert "grow_fallback" in raster_record.source_ids


def test_high_confidence_grow_fallback_prefers_native_emission() -> None:
    image = Image.new("RGB", (320, 200), "white")
    backend = FakeOCRBackend([OCRTextRegion(text="Lonely Node", bbox=BBox(92.0, 92.0, 180.0, 112.0), confidence=0.99)])
    parser = FakeStructureParser(
        DiagramStructure(
            nodes=[VLMNode("n1", "box", "Lonely Node", BBox(200.0, 320.0, 720.0, 760.0))],
            edges=[],
            coordinate_space="normalized_1000",
        )
    )

    result = build_elements(
        image,
        config=PipelineConfig(semantic_fallback_to_legacy=False),
        structure_parser=parser,
        ocr_backend=backend,
    )

    assert any(element.kind == "rect" for element in result.elements)
    assert not any(element.kind == "raster_region" for element in result.elements)


def test_validation_iteration_discovers_gt_sidecar_and_writes_real_eval(tmp_path: Path) -> None:
    image, backend, parser = semantic_fixture()
    image_path = tmp_path / "semantic-input.png"
    image.save(image_path)
    gt_path = image_path.with_name(f"{image_path.stem}.gt.json")
    gt_path.write_text(
        json.dumps(
            {
                "version": 1,
                "objects": [
                    {"id": "gt-left", "kind": "container", "bbox": [42.0, 52.0, 132.0, 112.0]},
                    {"id": "gt-right", "kind": "container", "bbox": [206.0, 84.0, 296.0, 144.0]},
                ],
            }
        ),
        encoding="utf-8",
    )

    run = run_validation_iteration(
        image_path,
        tmp_path / "iter",
        config=PipelineConfig(semantic_fallback_to_legacy=False),
        enable_diagnostics=True,
        ocr_backend=backend,
        structure_parser=parser,
        diagnostics_root_dir=tmp_path / "diagnostics",
    )

    assert run.artifacts.oracle_json is not None
    oracle_payload = json.loads(run.artifacts.oracle_json.read_text(encoding="utf-8"))
    failure_payload = json.loads(run.artifacts.failure_taxonomy_json.read_text(encoding="utf-8"))
    manifest_payload = json.loads((run.artifacts.diagnostics_dir / "manifest.json").read_text(encoding="utf-8"))
    assert oracle_payload["status"] == "ok"
    assert oracle_payload["gt_available"] is True
    assert oracle_payload["ground_truth_count"] == 2
    assert "07_emit" in oracle_payload["stages"]
    assert failure_payload["status"] == "ok"
    assert manifest_payload["gt_available"] is True


def test_failure_taxonomy_reports_machine_readable_categories() -> None:
    scenarios = [
        (
            "missing",
            [EvalItem("gt", "rect", BBox(0.0, 0.0, 40.0, 40.0))],
            [],
            {"gt": "missing"},
            {},
        ),
        (
            "merged_into_parent",
            [EvalItem("gt", "rect", BBox(12.0, 12.0, 28.0, 28.0))],
            [EvalItem("pred", "rect", BBox(0.0, 0.0, 40.0, 40.0))],
            {"gt": "merged_into_parent"},
            {"pred": "hallucinated_prediction"},
        ),
        (
            "merged_siblings",
            [
                EvalItem("gt-a", "rect", BBox(0.0, 0.0, 40.0, 40.0)),
                EvalItem("gt-b", "rect", BBox(50.0, 0.0, 90.0, 40.0)),
            ],
            [EvalItem("pred", "rect", BBox(0.0, 0.0, 90.0, 40.0))],
            {"gt-a": "merged_siblings", "gt-b": "merged_siblings"},
            {"pred": "merged_siblings"},
        ),
        (
            "split_fragments",
            [EvalItem("gt", "rect", BBox(0.0, 0.0, 100.0, 40.0))],
            [
                EvalItem("pred-a", "rect", BBox(0.0, 0.0, 40.0, 40.0)),
                EvalItem("pred-b", "rect", BBox(60.0, 0.0, 100.0, 40.0)),
            ],
            {"gt": "split_fragments"},
            {"pred-a": "split_fragments", "pred-b": "split_fragments"},
        ),
        (
            "wrong_type",
            [EvalItem("gt", "rect", BBox(0.0, 0.0, 40.0, 40.0))],
            [EvalItem("pred", "line", BBox(0.0, 0.0, 40.0, 40.0))],
            {"gt": "wrong_type"},
            {"pred": "wrong_type"},
        ),
        (
            "wrong_attachment",
            [EvalItem("gt", "connector", BBox(0.0, 0.0, 40.0, 10.0), attachment_ids=("a", "b"))],
            [EvalItem("pred", "connector", BBox(0.0, 0.0, 40.0, 10.0), attachment_ids=("a", "c"))],
            {"gt": "wrong_attachment"},
            {"pred": "wrong_attachment"},
        ),
        (
            "near_miss_geometry",
            [EvalItem("gt", "rect", BBox(0.0, 0.0, 40.0, 40.0))],
            [EvalItem("pred", "rect", BBox(20.0, 0.0, 60.0, 40.0))],
            {"gt": "near_miss_geometry"},
            {"pred": "near_miss_geometry"},
        ),
        (
            "hallucinated_prediction",
            [EvalItem("gt", "rect", BBox(0.0, 0.0, 40.0, 40.0))],
            [EvalItem("pred", "rect", BBox(120.0, 0.0, 160.0, 40.0))],
            {"gt": "missing"},
            {"pred": "hallucinated_prediction"},
        ),
    ]

    for _, ground_truth, predictions, expected_gt, expected_predictions in scenarios:
        result = failure_taxonomy(ground_truth, predictions)
        gt_tags = {row["gt_id"]: row["tag"] for row in result["ground_truth"]}
        pred_tags = {row["prediction_id"]: row["tag"] for row in result["predictions"]}
        assert gt_tags == expected_gt
        assert pred_tags == expected_predictions


def test_motif_builders_change_grouping_and_graph_edges(tmp_path: Path) -> None:
    image = Image.new("RGB", (320, 220), "white")
    hypotheses = [
        make_hypothesis("panel", "container", BBox(20.0, 20.0, 300.0, 180.0), guide_ids=["gx-panel", "gy-panel"], score_total=3.0),
        make_hypothesis("title", "textbox", BBox(34.0, 28.0, 120.0, 50.0), guide_ids=["gx-panel"], score_total=2.0, assigned_text_ids=["ocr-title"]),
        make_hypothesis("child-a", "container", BBox(36.0, 70.0, 122.0, 130.0), guide_ids=["row-1", "repeat-x"], score_total=2.2),
        make_hypothesis("child-b", "container", BBox(144.0, 70.0, 230.0, 130.0), guide_ids=["row-1", "repeat-x"], score_total=2.1),
        make_hypothesis("child-c", "container", BBox(252.0, 70.0, 338.0, 130.0), guide_ids=["row-1", "repeat-x"], score_total=2.0),
    ]
    recorder = build_recorder(enabled=True, run_id="run-motif", slide_id="slide-a", root_dir=tmp_path)
    guide_field = empty_guide_field()
    motif_result = build_motif_hypotheses(image, hypotheses, guide_field, PipelineConfig(), diagnostics=recorder)
    selection_result = select_authoring_objects(image, hypotheses, motif_result.motifs, PipelineConfig(), diagnostics=recorder)
    graph_result = build_authoring_graph(image, selection_result.selected, selection_result.selected_motifs, [], diagnostics=recorder)

    motif_kinds = {motif.kind for motif in selection_result.selected_motifs}
    assert "titled_panel" in motif_kinds
    assert "repeated_cards" in motif_kinds
    titled_panel = next(motif for motif in selection_result.selected_motifs if motif.kind == "titled_panel")
    repeated_cards = next(motif for motif in selection_result.selected_motifs if motif.kind == "repeated_cards")
    selected_lookup = {hypothesis.id: hypothesis for hypothesis in selection_result.selected}
    assert titled_panel.id in selected_lookup["panel"].parent_ids
    assert titled_panel.id in selected_lookup["title"].parent_ids
    assert repeated_cards.id in selected_lookup["child-a"].parent_ids
    edge_types = {edge.edge_type for edge in graph_result.graph.edges}
    assert {"contains", "repeat", "align_y", "z_before"} <= edge_types
    motif_effects = json.loads((tmp_path / "run-motif" / "slide-a" / "04_motifs" / "effects.json").read_text(encoding="utf-8"))
    assert {row["motif_kind"] for row in motif_effects} >= {"titled_panel", "repeated_cards"}


def test_validate_emission_trace_rejects_broken_provenance() -> None:
    record = EmissionRecord(
        id="emit:1",
        kind="rect",
        bbox=BBox(0.0, 0.0, 20.0, 20.0),
        score_total=1.0,
        score_terms={"confidence": 1.0},
        source_ids=["unknown-source"],
        provenance={"graph_node_ids": ["h1"], "hypothesis_ids": ["h1"]},
        object_type="container",
        primitive_kind="rect",
        graph_node_ids=["h1"],
        hypothesis_ids=["h1"],
        emitted_element_id="rect-1",
    )
    graph = AuthoringGraph(
        id="graph",
        kind="authoring_graph",
        bbox=BBox(0.0, 0.0, 20.0, 20.0),
        score_total=1.0,
        score_terms={"edges": 0.0},
        source_ids=["h1"],
        provenance={"source_ids": ["h1"]},
        node_ids=["h1"],
        edges=[],
    )
    hypothesis = make_hypothesis("h1", "container", BBox(0.0, 0.0, 20.0, 20.0), source_ids=["rect-candidate:h1"])

    with pytest.raises(StageContractError):
        validate_emission_trace(
            emission_records=[record],
            graph=graph,
            object_hypotheses=[hypothesis],
            motif_hypotheses=[],
            geometry_candidates=[],
            fallback_regions=[],
        )


def test_detector_compatibility_wrappers_delegate_to_geometry_and_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    import image_to_editable_ppt.fallback as fallback
    import image_to_editable_ppt.geometry as geometry

    bbox = BBox(10.0, 10.0, 40.0, 40.0)
    calls: list[str] = []

    def fake_clamp(inner: BBox, *, width: int, height: int) -> BBox:
        calls.append(f"geometry:{width}x{height}")
        return inner

    def fake_grow(array, text_anchor: BBox, hint_bbox: BBox, config: PipelineConfig) -> BBox:
        calls.append("fallback:grow")
        return hint_bbox

    monkeypatch.setattr(geometry, "clamp_bbox", fake_clamp)
    monkeypatch.setattr(fallback, "grow_container_from_text_anchor", fake_grow)

    assert detector_clamp_bbox(bbox, width=100, height=80) == bbox
    assert detector_grow_container_from_text_anchor(np.asarray(Image.new("RGB", (8, 8))), bbox, bbox, PipelineConfig()) == bbox
    assert calls == ["geometry:100x80", "fallback:grow"]
