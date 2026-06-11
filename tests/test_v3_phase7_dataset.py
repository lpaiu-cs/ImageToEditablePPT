from __future__ import annotations

import json
import random
from pathlib import Path

import pytest
from PIL import Image

import image_to_editable_ppt.ml.generate_dataset as generate_dataset_cli
from image_to_editable_ppt.ml.adapter import AnnotationMLAdapter
from image_to_editable_ppt.ml.annotation_schema import (
    SCHEMA_VERSION,
    AnnotationImageSize,
    DetectorAnnotationDocument,
)
from image_to_editable_ppt.ml.generate_dataset import assign_splits
from image_to_editable_ppt.ml.synthesize import (
    find_soffice,
    generate_slide_spec,
    render_spec_image,
    validate_spec_contract,
    write_spec_pptx,
)
from image_to_editable_ppt.v3.core.enums import DiagramFamily
from image_to_editable_ppt.v3.ir.validate import validate_slide_ir


def test_generated_specs_satisfy_slide_ir_contract() -> None:
    rng = random.Random(42)
    for index in range(25):
        spec = generate_slide_spec(rng, sample_id=f"contract_{index:03d}")
        validate_spec_contract(spec)
        assert 3 <= len(spec.nodes) <= 6
        assert len(spec.connectors) == len(spec.nodes) - 1
        assert len(spec.text_regions) == len(spec.nodes)


def test_generation_is_deterministic_for_equal_seeds() -> None:
    spec_a = generate_slide_spec(random.Random(123), sample_id="det")
    spec_b = generate_slide_spec(random.Random(123), sample_id="det")

    assert spec_a.to_annotation_document() == spec_b.to_annotation_document()
    assert render_spec_image(spec_a).tobytes() == render_spec_image(spec_b).tobytes()

    spec_c = generate_slide_spec(random.Random(124), sample_id="det")
    assert spec_a.to_annotation_document() != spec_c.to_annotation_document()


def test_generator_rejects_unsupported_family() -> None:
    with pytest.raises(ValueError, match="unsupported synthetic family"):
        generate_slide_spec(random.Random(1), sample_id="bad", family=DiagramFamily.CYCLE)


def test_render_draws_structures_at_annotated_positions() -> None:
    spec = generate_slide_spec(random.Random(5), sample_id="render")
    image = render_spec_image(spec)

    assert image.size == (spec.image_size.width, spec.image_size.height)
    background = image.getpixel((2, 2))
    assert background == (255, 255, 255)
    for node in spec.nodes:
        center = (int((node.bbox.x0 + node.bbox.x1) / 2), int((node.bbox.y0 + node.bbox.y1) / 2))
        edge = (int(node.bbox.x0) + 1, int((node.bbox.y0 + node.bbox.y1) / 2))
        assert image.getpixel(center) != (255, 255, 255)
        assert image.getpixel(edge) != (255, 255, 255)


def test_pptx_sidecar_preserves_shape_mapping(tmp_path: Path) -> None:
    pptx = pytest.importorskip("pptx")

    spec = generate_slide_spec(random.Random(9), sample_id="pptx")
    pptx_path = tmp_path / "sample.pptx"
    write_spec_pptx(spec, pptx_path)

    presentation = pptx.Presentation(pptx_path)
    assert presentation.slide_width == spec.image_size.width * 9525
    assert presentation.slide_height == spec.image_size.height * 9525
    shape_names = [shape.name for shape in presentation.slides[0].shapes]
    for node in spec.nodes:
        assert node.id in shape_names
    if spec.container is not None:
        assert spec.container.id in shape_names
    for connector in spec.connectors:
        assert connector.candidate.id in shape_names


def test_assign_splits_partitions_every_sample() -> None:
    splits = assign_splits(100, rng=random.Random(3), train_ratio=0.8, val_ratio=0.1)

    assert len(splits) == 100
    assert splits.count("train") == 80
    assert splits.count("val") == 10
    assert splits.count("test") == 10
    assert assign_splits(100, rng=random.Random(3), train_ratio=0.8, val_ratio=0.1) == splits


def test_generate_dataset_cli_writes_triplets_and_manifest(tmp_path: Path) -> None:
    output_dir = tmp_path / "dataset"
    exit_code = generate_dataset_cli.main(
        [
            "--output-dir",
            str(output_dir),
            "--count",
            "6",
            "--seed",
            "21",
            "--image-width",
            "640",
            "--image-height",
            "360",
            "--train-ratio",
            "0.5",
            "--val-ratio",
            "0.25",
        ]
    )
    assert exit_code == 0

    manifest = json.loads((output_dir / "dataset_manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == SCHEMA_VERSION
    assert manifest["generator"]["seed"] == 21
    assert manifest["split_counts"] == {"train": 3, "val": 2, "test": 1}
    assert sum(manifest["family_counts"].values()) == 6
    assert len(manifest["samples"]) == 6

    adapter = AnnotationMLAdapter()
    for sample in manifest["samples"]:
        image_path = output_dir / sample["image"]
        annotation_path = output_dir / sample["annotation"]
        pptx_path = output_dir / sample["pptx"]
        assert image_path.exists() and annotation_path.exists() and pptx_path.exists()
        assert Path(sample["image"]).parts[0] == sample["split"]

        with Image.open(image_path) as image:
            assert image.size == (640, 360)
        document = DetectorAnnotationDocument.from_dict(json.loads(annotation_path.read_text(encoding="utf-8")))
        assert document.image_id == sample["id"]
        assert document.split == sample["split"]
        assert document.image_size == AnnotationImageSize(width=640, height=360)
        validate_slide_ir(adapter.to_slide_ir(document))


@pytest.mark.skipif(find_soffice() is None, reason="LibreOffice (soffice) not installed")
def test_generate_dataset_cli_supports_soffice_renderer(tmp_path: Path) -> None:
    output_dir = tmp_path / "dataset"
    exit_code = generate_dataset_cli.main(
        ["--output-dir", str(output_dir), "--count", "1", "--seed", "2", "--renderer", "soffice"]
    )
    assert exit_code == 0

    manifest = json.loads((output_dir / "dataset_manifest.json").read_text(encoding="utf-8"))
    assert manifest["generator"]["renderer"] == "soffice_png_v1"
    sample = manifest["samples"][0]
    with Image.open(output_dir / sample["image"]) as image:
        assert image.size == (1280, 720)
    assert (output_dir / sample["pptx"]).exists()


def test_generate_dataset_cli_can_skip_pptx(tmp_path: Path) -> None:
    output_dir = tmp_path / "dataset"
    exit_code = generate_dataset_cli.main(
        ["--output-dir", str(output_dir), "--count", "2", "--seed", "1", "--no-pptx"]
    )
    assert exit_code == 0

    manifest = json.loads((output_dir / "dataset_manifest.json").read_text(encoding="utf-8"))
    assert manifest["generator"]["pptx_written"] is False
    for sample in manifest["samples"]:
        assert sample["pptx"] is None
    assert not list(output_dir.rglob("*.pptx"))
