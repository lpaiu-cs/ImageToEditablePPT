from __future__ import annotations

from PIL import Image, ImageDraw
import numpy as np

from image_to_editable_ppt.v3.app.config import V3Config
from image_to_editable_ppt.v3.app.convert import convert_image
from image_to_editable_ppt.v3.core.enums import BranchKind, RasterRegionKind, StageName, TextRegionRole
from image_to_editable_ppt.v3.ir.validate import validate_raster_layer_result, validate_residual_canvas_result, validate_text_layer_result
from image_to_editable_ppt.v3.preprocessing import build_multiview_bundle, build_residual_canvas
from image_to_editable_ppt.v3.raster import extract_raster_layer
from image_to_editable_ppt.v3.text import extract_text_layer


def test_text_branch_contract_handles_empty_region_set_and_builds_masked_view() -> None:
    image = Image.new("RGB", (96, 64), "white")
    bundle = build_multiview_bundle(image)

    text_layer = extract_text_layer(bundle, config=V3Config())

    validate_text_layer_result(text_layer)
    assert text_layer.regions == ()
    assert text_layer.masked_structure_view.shape == (64, 96)
    assert text_layer.soft_mask.shape == (64, 96)


def test_text_branch_detects_text_regions_and_preserves_metadata() -> None:
    image = Image.new("RGB", (160, 100), "white")
    draw = ImageDraw.Draw(image)
    draw.text((14, 16), "Encoder", fill="black")
    bundle = build_multiview_bundle(image)

    text_layer = extract_text_layer(bundle, config=V3Config())

    validate_text_layer_result(text_layer)
    assert text_layer.regions
    assert all(region.source for region in text_layer.regions)
    assert all(region.provenance for region in text_layer.regions)
    assert {region.role for region in text_layer.regions} <= {TextRegionRole.LABEL, TextRegionRole.TITLE, TextRegionRole.BODY}
    assert np.count_nonzero(text_layer.soft_mask > 0.0) > 0


def test_raster_branch_contract_returns_mask_and_region_payload() -> None:
    image = make_raster_image()
    bundle = build_multiview_bundle(image)
    text_layer = extract_text_layer(bundle, config=V3Config())

    raster_layer = extract_raster_layer(
        bundle,
        text_layer=text_layer,
        config=V3Config(),
    )

    validate_raster_layer_result(raster_layer)
    assert raster_layer.regions
    assert raster_layer.subtraction_mask.shape == (96, 160)
    assert raster_layer.subtracted_structure_view.shape == (96, 160)
    assert any(region.kind in {RasterRegionKind.COMPLEX_REGION, RasterRegionKind.PHOTO_LIKE} for region in raster_layer.regions)
    assert np.count_nonzero(raster_layer.subtraction_mask > 0.0) > 0


def test_residual_canvas_contract_combines_text_and_raster_outputs() -> None:
    image = make_mixed_image()
    bundle = build_multiview_bundle(image)
    config = V3Config()
    text_layer = extract_text_layer(bundle, config=config)
    raster_layer = extract_raster_layer(bundle, text_layer=text_layer, config=config)

    residual_result = build_residual_canvas(bundle, text_layer=text_layer, raster_layer=raster_layer)

    validate_residual_canvas_result(residual_result)
    assert residual_result.canvas is not None
    assert residual_result.canvas.image.shape == (120, 200)
    assert residual_result.text_mask.shape == (120, 200)
    assert residual_result.raster_mask.shape == (120, 200)
    assert residual_result.canvas.text_region_ids == tuple(region.id for region in text_layer.regions)
    assert residual_result.canvas.raster_region_ids == tuple(region.id for region in raster_layer.regions)
    assert bundle.branch(BranchKind.STRUCTURAL_CANVAS).image.shape == (120, 200)


def test_orchestration_flow_connects_multiview_text_raster_and_residual() -> None:
    result = convert_image(make_mixed_image())

    assert result.slide_ir.text_layer is not None
    assert result.slide_ir.raster_layer is not None
    assert result.slide_ir.residual_canvas is not None
    assert [record.stage for record in result.stage_records[:4]] == [
        StageName.MULTIVIEW,
        StageName.TEXT_SPLIT,
        StageName.RASTER_SPLIT,
        StageName.RESIDUAL_CANVAS,
    ]
    assert result.stage_records[1].summary["text_region_count"] >= 1
    assert result.stage_records[2].summary["raster_region_count"] >= 1
    assert result.stage_records[3].summary["canvas_ready"] is True


def make_raster_image() -> Image.Image:
    image = Image.new("RGB", (160, 96), "white")
    rng = np.random.default_rng(7)
    noise = rng.integers(0, 255, size=(42, 56, 3), dtype=np.uint8)
    array = np.asarray(image).copy()
    array[28:70, 70:126] = noise
    return Image.fromarray(array, mode="RGB")


def make_mixed_image() -> Image.Image:
    image = Image.new("RGB", (200, 120), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((16, 22, 88, 76), outline="black", width=2)
    draw.text((26, 36), "Node", fill="black")
    rng = np.random.default_rng(11)
    noise = rng.integers(0, 255, size=(44, 64, 3), dtype=np.uint8)
    array = np.asarray(image).copy()
    array[52:96, 118:182] = noise
    return Image.fromarray(array, mode="RGB")
