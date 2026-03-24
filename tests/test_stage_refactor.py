from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw

from image_to_editable_ppt.config import PipelineConfig
from image_to_editable_ppt.diagnostics import build_recorder
from image_to_editable_ppt.eval_debug import EvalItem, attrition_by_stage, failure_taxonomy, oracle_upper_bound_by_stage, write_eval_debug_artifacts
from image_to_editable_ppt.ir import BBox
from image_to_editable_ppt.pipeline import build_elements
from image_to_editable_ppt.text import OCRBackend, OCRTextRegion
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
        config=PipelineConfig(semantic_fallback_to_legacy=False),
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
        config=PipelineConfig(semantic_fallback_to_legacy=False),
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
    assert oracle_payload["01_geometry_raw"]["recoverable_count"] == 3
