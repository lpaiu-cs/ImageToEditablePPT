"""Phase 10: editable pptx writer + text merge + OCR annotation contracts."""
from __future__ import annotations

import json
import numpy as np
import pytest
from PIL import Image, ImageDraw

from image_to_editable_ppt.shared.geometry import BBox, ImageSize, Point
from image_to_editable_ppt.v3.compose.merge_text import merge_text_layer_into_slide_ir
from image_to_editable_ppt.v3.core.enums import (
    ConnectorKind,
    ContainerKind,
    NodeKind,
    PortOwnerKind,
    TextRegionRole,
)
from image_to_editable_ppt.v3.emit.models import (
    EmitConnectorPrimitive,
    EmitScene,
    EmitShapePrimitive,
    EmitTextPrimitive,
)
from image_to_editable_ppt.v3.emit.pptx_writer import EMU_PER_PIXEL, write_pptx
from image_to_editable_ppt.v3.emit.style import ShapeVisualStyle, sample_shape_styles
from image_to_editable_ppt.v3.ir.models import (
    DiagramNode,
    PrimitiveContainer,
    PrimitiveNode,
    PrimitiveScene,
    SlideIR,
    TextLayerResult,
    TextRegion,
)


def _scene() -> EmitScene:
    return EmitScene(
        image_size=ImageSize(width=400, height=300),
        shapes=(
            EmitShapePrimitive(
                id="container:1",
                owner_kind=PortOwnerKind.CONTAINER,
                shape_kind=ContainerKind.PANEL,
                bbox=BBox(10, 10, 380, 280),
                confidence=0.9,
            ),
            EmitShapePrimitive(
                id="node:1",
                owner_kind=PortOwnerKind.NODE,
                shape_kind=NodeKind.BOX,
                bbox=BBox(40, 40, 160, 100),
                confidence=0.9,
            ),
            EmitShapePrimitive(
                id="node:2",
                owner_kind=PortOwnerKind.NODE,
                shape_kind=NodeKind.LABEL_ANCHOR,
                bbox=BBox(200, 60, 280, 84),
                confidence=0.9,
            ),
        ),
        texts=(
            EmitTextPrimitive(
                id="text:1",
                role=TextRegionRole.LABEL,
                bbox=BBox(52, 60, 148, 80),
                confidence=0.9,
                text="Encoder",
                owner_ids=("node:1",),
            ),
            EmitTextPrimitive(
                id="text:2",
                role=TextRegionRole.LABEL,
                bbox=BBox(202, 62, 278, 82),
                confidence=0.9,
                text="NP",
                owner_ids=("node:2",),
            ),
            EmitTextPrimitive(
                id="text:3",
                role=TextRegionRole.TITLE,
                bbox=BBox(20, 240, 200, 262),
                confidence=0.9,
                text="Figure title",
            ),
            EmitTextPrimitive(
                id="text:4",
                role=TextRegionRole.LABEL,
                bbox=BBox(300, 240, 360, 260),
                confidence=0.9,
                text=None,  # unrecognized -> must not be emitted
            ),
        ),
        connectors=(
            EmitConnectorPrimitive(
                id="connector:1",
                kind=ConnectorKind.ARROW,
                confidence=0.9,
                source_owner_id="node:1",
                source_owner_kind=PortOwnerKind.NODE,
                target_owner_id="node:2",
                target_owner_kind=PortOwnerKind.NODE,
                source_port_id="port:1",
                target_port_id="port:2",
                path_points=(Point(160, 70), Point(200, 70)),
                arrowhead_end=True,
            ),
            EmitConnectorPrimitive(
                id="connector:2",
                kind=ConnectorKind.LINE,
                confidence=0.9,
                source_owner_id="node:1",
                source_owner_kind=PortOwnerKind.NODE,
                target_owner_id="node:2",
                target_owner_kind=PortOwnerKind.NODE,
                source_port_id="port:3",
                target_port_id="port:4",
                path_points=(),  # no geometry -> must not be drawn
            ),
        ),
    )


def test_write_pptx_writes_native_editable_primitives(tmp_path):
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE
    from zipfile import ZipFile

    output = tmp_path / "scene.pptx"
    styles = {"node:1": ShapeVisualStyle(fill=(59, 130, 246), stroke=(30, 64, 175))}
    write_pptx(_scene(), output, styles=styles)

    presentation = Presentation(str(output))
    assert presentation.slide_width == 400 * EMU_PER_PIXEL
    assert presentation.slide_height == 300 * EMU_PER_PIXEL
    shapes = {shape.name: shape for shape in presentation.slides[0].shapes}

    # container + box node are autoshapes; label-anchor node and title are text boxes
    assert shapes["container:1"].shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE
    assert shapes["node:1"].shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE
    assert shapes["node:1"].text_frame.text == "Encoder"
    assert str(shapes["node:1"].fill.fore_color.rgb) == "3B82F6"
    assert str(shapes["node:1"].text_frame.paragraphs[0].runs[0].font.color.rgb) == "F8FAFC"
    assert shapes["node:2"].shape_type == MSO_SHAPE_TYPE.TEXT_BOX
    assert shapes["node:2"].text_frame.text == "NP"
    assert shapes["text:3"].text_frame.text == "Figure title"

    # owned texts are absorbed into shapes, unrecognized standalone text is skipped
    assert "text:1" not in shapes
    assert "text:2" not in shapes
    assert "text:4" not in shapes

    # exactly one connector with an end arrowhead; the geometry-less one is skipped
    assert "connector:2" not in shapes
    connector = shapes["connector:1"]
    assert connector.shape_type == MSO_SHAPE_TYPE.LINE
    assert "tailEnd" in connector._element.xml
    slide_xml = ZipFile(output).read("ppt/slides/slide1.xml").decode("utf-8")
    assert slide_xml.count("<a:stCxn") == 1
    assert slide_xml.count("<a:endCxn") == 1
    # geometry matches the path in EMU
    assert connector.begin_x == 160 * EMU_PER_PIXEL
    assert connector.end_x == 200 * EMU_PER_PIXEL
    assert connector._element.spPr.xfrm.get("flipV") is None


def test_write_pptx_uses_one_bound_connector_for_multi_segment_route(tmp_path):
    from dataclasses import replace
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE
    from zipfile import ZipFile

    scene = _scene()
    bent = replace(
        scene.connectors[0],
        path_points=(Point(160, 70), Point(180, 70), Point(180, 72), Point(200, 72)),
    )
    output = tmp_path / "elbow.pptx"

    write_pptx(replace(scene, connectors=(bent,)), output)

    presentation = Presentation(str(output))
    lines = [shape for shape in presentation.slides[0].shapes if shape.shape_type == MSO_SHAPE_TYPE.LINE]
    assert len(lines) == 1
    slide_xml = ZipFile(output).read("ppt/slides/slide1.xml").decode("utf-8")
    assert slide_xml.count("<a:stCxn") == 1
    assert slide_xml.count("<a:endCxn") == 1
    assert "bentConnector" in slide_xml


def test_write_pptx_keeps_offset_axial_binding_orthogonal(tmp_path):
    from dataclasses import replace
    from zipfile import ZipFile

    scene = _scene()
    shifted_target = replace(scene.shapes[2], bbox=BBox(200, 150, 280, 210))
    vertical = replace(
        scene.connectors[0],
        path_points=(Point(150, 100), Point(150, 150)),
    )
    output = tmp_path / "offset-vertical.pptx"

    write_pptx(replace(scene, shapes=(*scene.shapes[:2], shifted_target), connectors=(vertical,)), output)

    slide_xml = ZipFile(output).read("ppt/slides/slide1.xml").decode("utf-8")
    assert slide_xml.count("<a:stCxn") == 1
    assert slide_xml.count("<a:endCxn") == 1
    assert "bentConnector" in slide_xml


def test_write_pptx_preserves_distinct_visual_container_edge_coordinate(tmp_path):
    from pptx import Presentation
    from zipfile import ZipFile

    source = EmitShapePrimitive(
        id="container:source",
        owner_kind=PortOwnerKind.CONTAINER,
        shape_kind=ContainerKind.PANEL,
        bbox=BBox(20, 20, 180, 80),
        confidence=1.0,
    )
    target = EmitShapePrimitive(
        id="container:target",
        owner_kind=PortOwnerKind.CONTAINER,
        shape_kind=ContainerKind.PANEL,
        bbox=BBox(20, 220, 380, 280),
        confidence=1.0,
    )
    connector = EmitConnectorPrimitive(
        id="connector:visual-container",
        kind=ConnectorKind.ARROW,
        confidence=1.0,
        source_owner_id=source.id,
        source_owner_kind=PortOwnerKind.CONTAINER,
        target_owner_id=target.id,
        target_owner_kind=PortOwnerKind.CONTAINER,
        source_port_id="port:source",
        target_port_id="port:target",
        path_points=(Point(40, 80), Point(40, 220)),
        arrowhead_end=True,
        provenance=("visual_connector:source_pixels",),
    )
    scene = EmitScene(image_size=ImageSize(width=400, height=300), shapes=(source, target), connectors=(connector,))
    output = tmp_path / "visual-container-coordinate.pptx"

    write_pptx(scene, output)

    presentation = Presentation(str(output))
    line = next(shape for shape in presentation.slides[0].shapes if shape.name == connector.id)
    slide_xml = ZipFile(output).read("ppt/slides/slide1.xml").decode("utf-8")
    assert slide_xml.count("<a:stCxn") == 0
    assert slide_xml.count("<a:endCxn") == 0
    assert "bentConnector" not in slide_xml
    assert line.begin_x == 40 * EMU_PER_PIXEL
    assert line.end_x == 40 * EMU_PER_PIXEL


def test_write_pptx_positions_match_image_space(tmp_path):
    from pptx import Presentation

    output = tmp_path / "scene.pptx"
    write_pptx(_scene(), output)
    shapes = {shape.name: shape for shape in Presentation(str(output)).slides[0].shapes}
    node = shapes["node:1"]
    assert node.left == 40 * EMU_PER_PIXEL
    assert node.top == 40 * EMU_PER_PIXEL
    assert node.width == 120 * EMU_PER_PIXEL
    assert node.height == 60 * EMU_PER_PIXEL


def test_write_pptx_omits_unowned_non_title_text(tmp_path):
    from dataclasses import replace
    from pptx import Presentation

    scene = _scene()
    floating_label = EmitTextPrimitive(
        id="text:floating",
        role=TextRegionRole.LABEL,
        bbox=BBox(170, 150, 240, 170),
        confidence=0.95,
        text="edge label",
    )
    output = tmp_path / "conservative-text.pptx"

    write_pptx(replace(scene, texts=(*scene.texts, floating_label)), output)

    names = {shape.name for shape in Presentation(str(output)).slides[0].shapes}
    assert floating_label.id not in names
    assert "text:3" in names  # trusted title remains


def test_sample_shape_styles_is_conservative():
    rgb = np.full((300, 400, 3), 255, dtype=np.uint8)
    # filled blue node with dark border
    rgb[40:100, 40:160] = (37, 99, 235)
    scene = _scene()
    styles = sample_shape_styles(rgb, scene)

    node_style = styles["node:1"]
    assert node_style.fill is not None
    assert abs(node_style.fill[2] - 235) <= 3  # blue interior sampled

    # container over plain white background: no fill invented, but stays visible
    container_style = styles["container:1"]
    assert container_style.fill is None
    assert container_style.stroke is not None

    # label anchors are borderless text: never filled/stroked
    label_style = styles["node:2"]
    assert label_style.fill is None and label_style.stroke is None


def test_merge_text_layer_promotes_labels_and_keeps_standalone():
    image_size = ImageSize(width=400, height=300)
    scene = PrimitiveScene(
        image_size=image_size,
        nodes=(
            PrimitiveNode(id="node:1", kind=NodeKind.BOX, bbox=BBox(40, 40, 160, 100), confidence=0.9),
            PrimitiveNode(id="node:2", kind=NodeKind.BOX, bbox=BBox(30, 30, 300, 200), confidence=0.9),
        ),
    )
    slide_ir = SlideIR(image_size=image_size, primitive_scene=scene)
    text_layer = TextLayerResult(
        image_size=image_size,
        regions=(
            TextRegion(id="text:1", bbox=BBox(50, 60, 150, 80), confidence=0.9, text="Encoder"),
            TextRegion(id="text:2", bbox=BBox(200, 250, 280, 270), confidence=0.9, text="caption"),
            TextRegion(id="text:3", bbox=BBox(60, 82, 140, 96), confidence=0.9, text=None),
        ),
    )

    merged = merge_text_layer_into_slide_ir(slide_ir, text_layer)
    merged_scene = merged.primitive_scene
    nodes = {node.id: node for node in merged_scene.nodes}
    # the smallest containing node owns the text and gets the label
    assert nodes["node:1"].label == "Encoder"
    assert nodes["node:2"].label is None
    texts = {text.id: text for text in merged_scene.texts}
    assert texts["text:1"].owner_ids == ("node:1",)
    assert texts["text:2"].owner_ids == ()  # standalone caption
    assert texts["text:3"].owner_ids == ("node:1",)  # owned but unrecognized: no label impact
    assert merged.text_regions == text_layer.regions
    assert merged.text_layer is text_layer


def test_merge_text_layer_owns_only_source_confirmed_panel_header() -> None:
    image_size = ImageSize(width=400, height=300)
    container = PrimitiveContainer(
        id="container:titled",
        kind=ContainerKind.PANEL,
        bbox=BBox(20, 20, 380, 220),
        confidence=0.9,
        source="visual_geometry:titled_panel",
    )
    scene = PrimitiveScene(image_size=image_size, containers=(container,))
    slide_ir = SlideIR(image_size=image_size, primitive_scene=scene)
    text_layer = TextLayerResult(
        image_size=image_size,
        regions=(
            TextRegion(id="text:header", bbox=BBox(140, 28, 260, 52), confidence=0.9, text="Inputs"),
            TextRegion(id="text:body", bbox=BBox(140, 120, 260, 144), confidence=0.9, text="icon label"),
        ),
    )

    merged = merge_text_layer_into_slide_ir(slide_ir, text_layer)
    texts = {text.id: text for text in merged.primitive_scene.texts}

    assert texts["text:header"].owner_ids == (container.id,)
    assert texts["text:body"].owner_ids == ()


def test_write_pptx_emits_source_confirmed_panel_header_label(tmp_path) -> None:
    from dataclasses import replace
    from pptx import Presentation

    scene = _scene()
    titled_container = replace(scene.shapes[0], source="visual_geometry:titled_panel")
    header = EmitTextPrimitive(
        id="text:panel-header",
        role=TextRegionRole.LABEL,
        bbox=BBox(140, 16, 250, 34),
        confidence=0.95,
        text="Inputs",
        owner_ids=(titled_container.id,),
    )
    output = tmp_path / "panel-header.pptx"

    write_pptx(replace(scene, shapes=(titled_container, *scene.shapes[1:]), texts=(*scene.texts, header)), output)

    names = {shape.name for shape in Presentation(str(output)).slides[0].shapes}
    assert header.id in names


def test_write_pptx_selects_complete_ocr_region_over_overlapping_fragments(tmp_path) -> None:
    from dataclasses import replace
    from pptx import Presentation

    scene = _scene()
    complete = replace(scene.texts[0], text="Samples", bbox=BBox(65, 55, 135, 82))
    left_fragment = replace(scene.texts[0], id="text:left", text="Sam", bbox=BBox(35, 45, 105, 96))
    right_fragment = replace(scene.texts[0], id="text:right", text="ples", bbox=BBox(100, 45, 170, 96))
    output = tmp_path / "deduped-ocr.pptx"

    write_pptx(replace(scene, texts=(complete, left_fragment, right_fragment, *scene.texts[1:])), output)

    shapes = {shape.name: shape for shape in Presentation(str(output)).slides[0].shapes}
    assert shapes["node:1"].text == "Samples"


def test_write_pptx_reads_same_line_ocr_fragments_left_to_right(tmp_path) -> None:
    from dataclasses import replace
    from pptx import Presentation

    scene = _scene()
    number = replace(scene.texts[0], text="2.", bbox=BBox(50, 58, 68, 78))
    label = replace(scene.texts[0], id="text:label", text="Data collection", bbox=BBox(72, 56, 150, 80))
    output = tmp_path / "ocr-line-order.pptx"

    write_pptx(replace(scene, texts=(number, label, *scene.texts[1:])), output)

    shapes = {shape.name: shape for shape in Presentation(str(output)).slides[0].shapes}
    assert shapes["node:1"].text == "2. Data collection"


def test_write_pptx_prefers_tight_label_over_large_contaminated_extension(tmp_path) -> None:
    from dataclasses import replace
    from pptx import Presentation

    scene = _scene()
    contaminated = replace(scene.texts[0], text="D SVF", bbox=BBox(35, 35, 165, 98))
    tight = replace(scene.texts[0], id="text:tight", text="SVF", bbox=BBox(82, 58, 120, 80))
    output = tmp_path / "tight-ocr-label.pptx"

    write_pptx(replace(scene, texts=(contaminated, tight, *scene.texts[1:])), output)

    shapes = {shape.name: shape for shape in Presentation(str(output)).slides[0].shapes}
    assert shapes["node:1"].text == "SVF"


def test_write_pptx_omits_explicit_legend_node(tmp_path) -> None:
    from dataclasses import replace
    from pptx import Presentation

    scene = _scene()
    legend = replace(scene.texts[0], text="Legend:")
    output = tmp_path / "no-legend-node.pptx"

    write_pptx(replace(scene, texts=(legend, *scene.texts[1:])), output)

    names = {shape.name for shape in Presentation(str(output)).slides[0].shapes}
    assert "node:1" not in names


def test_ocr_annotate_fills_confident_text():
    from image_to_editable_ppt.v3.text.ocr import annotate_text_regions, ocr_available

    if not ocr_available():
        pytest.skip("no OCR backend installed")

    image = Image.new("RGB", (240, 60), "white")
    draw = ImageDraw.Draw(image)
    draw.text((12, 20), "Encoder Layer", fill="black")
    regions = (TextRegion(id="text:1", bbox=BBox(8, 14, 120, 36), confidence=0.8),)
    annotated = annotate_text_regions(np.asarray(image, dtype=np.uint8), regions)
    assert annotated[0].text is not None
    assert "encoder" in annotated[0].text.lower()
    assert any(item.startswith("ocr:") for item in annotated[0].provenance)


def test_node_bounded_ocr_recovers_inverted_label_without_inventing_geometry(monkeypatch):
    import image_to_editable_ppt.v3.text.ocr as ocr

    class FakeEngine:
        def __call__(self, crop):
            assert crop.shape[:2] == (60, 120)
            return (
                [
                    [[[52, 2], [68, 2], [68, 12], [52, 12]], "0C", 0.41],
                    [[[10, 15], [110, 15], [110, 28], [10, 28]], "Bot Orchestrator", 0.98],
                    [[[8, 34], [112, 34], [112, 48], [8, 48]], "(Main Loop Controller)", 0.94],
                ],
                None,
            )

    monkeypatch.setattr(ocr, "_load_engine", lambda: FakeEngine())
    rgb = np.zeros((120, 200, 3), dtype=np.uint8)
    layer = TextLayerResult(image_size=ImageSize(width=200, height=120))
    nodes = (DiagramNode(id="node:dark", kind=NodeKind.BOX, bbox=BBox(40, 30, 160, 90)),)

    recovered = ocr.recover_node_text_regions(rgb, layer, nodes)

    assert len(recovered.regions) == 1
    region = recovered.regions[0]
    assert region.bbox == nodes[0].bbox
    assert region.text == "Bot Orchestrator\n(Main Loop Controller)"
    assert region.source == "phase13_node_bounded_ocr"


def test_convert_cli_heuristic_smoke(tmp_path):
    from pptx import Presentation

    from image_to_editable_ppt.ml.convert_to_pptx import main

    image = Image.new("RGB", (320, 240), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((40, 60, 140, 120), outline="black", width=3)
    draw.rectangle((190, 60, 290, 120), outline="black", width=3)
    draw.line((140, 90, 190, 90), fill="black", width=3)
    input_path = tmp_path / "figure.png"
    image.save(input_path)

    output_path = tmp_path / "figure_out.pptx"
    code = main([str(input_path), "-o", str(output_path), "--no-ml", "--no-ocr", "--no-style", "--width", "0"])
    assert code == 0
    assert output_path.exists()
    presentation = Presentation(str(output_path))
    assert presentation.slide_width == 320 * EMU_PER_PIXEL


def test_convert_cli_rejects_batch_output_collisions(tmp_path, capsys):
    from image_to_editable_ppt.ml.convert_to_pptx import main

    first = tmp_path / "paper-a" / "fig1.png"
    second = tmp_path / "paper-b" / "fig1.png"
    first.parent.mkdir()
    second.parent.mkdir()
    Image.new("RGB", (20, 20), "white").save(first)
    Image.new("RGB", (20, 20), "white").save(second)
    output_dir = tmp_path / "out"

    code = main(
        [str(first), str(second), "-o", str(output_dir), "--no-ml", "--no-ocr", "--no-style", "--width", "0"]
    )

    assert code == 2
    assert "same output path" in capsys.readouterr().err
    assert not output_dir.exists()


def test_convert_cli_requires_gate_checkpoint_unless_explicitly_disabled(tmp_path):
    from image_to_editable_ppt.ml.convert_to_pptx import _build_provider, build_parser

    detector = tmp_path / "run-v8" / "checkpoints" / "last.ckpt"
    detector.parent.mkdir(parents=True)
    detector.touch()
    parser = build_parser()
    args = parser.parse_args(["figure.png", "--models-dir", str(tmp_path)])

    with pytest.raises(SystemExit, match="diagram-gate checkpoint not found"):
        _build_provider(args)

    no_gate_args = parser.parse_args(["figure.png", "--models-dir", str(tmp_path), "--no-gate"])
    provider = _build_provider(no_gate_args)
    assert provider.diagram_gate_checkpoint is None


def test_convert_cli_reports_empty_from_primitives_not_default_family(tmp_path, monkeypatch, capsys):
    import image_to_editable_ppt.ml.convert_to_pptx as cli

    input_path = tmp_path / "figure.png"
    Image.new("RGB", (20, 20), "white").save(input_path)

    def fake_convert_one(*args, **kwargs):
        return {
            "family": "orthogonal_flow",
            "nodes": 0,
            "containers": 0,
            "connectors": 0,
            "texts": 0,
            "recognized_texts": 0,
            "output": str(tmp_path / "figure.pptx"),
        }

    monkeypatch.setattr(cli, "convert_one", fake_convert_one)
    code = cli.main([str(input_path), "--no-ml", "--no-ocr"])

    assert code == 0
    output = capsys.readouterr().out
    assert output.startswith("[EMPTY]")
    assert "--no-gate" not in output


def test_editability_report_measures_native_structure_and_gt(tmp_path):
    from tools.evaluate_pptx_editability import evaluate

    output = tmp_path / "scene.pptx"
    annotation_path = tmp_path / "scene.json"
    write_pptx(_scene(), output)
    annotation_path.write_text(
        json.dumps(
            {
                "image_size": {"width": 400, "height": 300},
                "primitive_scene": {
                    "nodes": [
                        {"id": "gt-node-1", "bbox": {"x0": 40, "y0": 40, "x1": 160, "y1": 100}, "label": "Encoder"},
                        {"id": "gt-node-2", "bbox": {"x0": 200, "y0": 60, "x1": 280, "y1": 84}, "label": "NP"},
                    ],
                    "containers": [
                        {"id": "gt-container-1", "bbox": {"x0": 10, "y0": 10, "x1": 380, "y1": 280}}
                    ],
                    "connector_candidates": [
                        {
                            "start_endpoint": {"owner_id": "gt-node-1"},
                            "end_endpoint": {"owner_id": "gt-node-2"},
                            "arrowhead_start": False,
                            "arrowhead_end": True,
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )

    report = evaluate(output, annotation_path)

    assert report["endpoint_bindings"]["fully_attached"] == 1
    assert report["ground_truth"]["nodes"]["f1"] == 1.0
    assert report["ground_truth"]["containers"]["f1"] == 1.0
    assert report["ground_truth"]["connector_topology"]["f1"] == 1.0
    assert report["ground_truth"]["connector_semantics"]["f1"] == 1.0
    assert report["ground_truth"]["connector_direction_corrections"] == 0
    assert report["ground_truth"]["labels"]["exact_on_matched_node"] == 2
    assert report["ground_truth"]["edit_operations_lower_bound"] == 0
