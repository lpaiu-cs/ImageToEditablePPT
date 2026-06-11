"""Synthetic dataset generation for the Phase 7 ML track.

Strategy (see plan.md, Phase 7 / Task 2): instead of hand-labelling real
slides, programmatically compose random diagram structures, write them both
as an editable .pptx and as a rendered .png, and emit the ground-truth
``DetectorAnnotationDocument`` from the same spec. The spec is the single
source of truth, so image, pptx, and annotation geometry always agree.

Rendering uses a deterministic PIL rasterizer rather than a PowerPoint
renderer so dataset generation does not depend on LibreOffice/Office being
installed; the .pptx sidecar preserves the img - ppt mapping pair.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from image_to_editable_ppt.ml.adapter import AnnotationMLAdapter, DetectorModelOutput
from image_to_editable_ppt.ml.annotation_schema import (
    AnnotationBBox,
    AnnotationConnectorCandidate,
    AnnotationConnectorEndpoint,
    AnnotationContainer,
    AnnotationFamilyProposal,
    AnnotationImageSize,
    AnnotationNode,
    AnnotationPoint,
    AnnotationPort,
    AnnotationTextRegion,
    DetectorAnnotationDocument,
)
from image_to_editable_ppt.v3.core.enums import (
    ConnectorKind,
    ContainerKind,
    DiagramFamily,
    NodeKind,
    PortOwnerKind,
    PortSide,
    TextRegionRole,
)
from image_to_editable_ppt.v3.ir.validate import validate_slide_ir

GENERATOR_NAME = "synthetic_ppt_render_v1"
RENDERER_NAME = "pil_raster_v1"
EMU_PER_PIXEL = 9525  # 1 px at 96 dpi

SUPPORTED_FAMILIES = (DiagramFamily.ORTHOGONAL_FLOW,)

_LABEL_VOCAB = (
    "Plan",
    "Input",
    "Parse",
    "Review",
    "Build",
    "Test",
    "Deploy",
    "Verify",
    "Ship",
    "Audit",
    "Merge",
    "Release",
)

_FILL_PALETTE = (
    (219, 234, 254),
    (220, 252, 231),
    (254, 243, 199),
    (252, 231, 243),
    (237, 233, 254),
    (226, 232, 240),
)

_STROKE_PALETTE = (
    (30, 64, 175),
    (22, 101, 52),
    (146, 64, 14),
    (157, 23, 77),
    (91, 33, 182),
    (51, 65, 85),
)


@dataclass(slots=True, frozen=True)
class SyntheticNodeStyle:
    fill: tuple[int, int, int]
    stroke: tuple[int, int, int]


@dataclass(slots=True, frozen=True)
class SyntheticConnector:
    candidate: AnnotationConnectorCandidate
    start_port: AnnotationPort
    end_port: AnnotationPort
    stroke: tuple[int, int, int]


@dataclass(slots=True, frozen=True)
class SyntheticSlideSpec:
    sample_id: str
    family: DiagramFamily
    image_size: AnnotationImageSize
    nodes: tuple[AnnotationNode, ...]
    node_styles: dict[str, SyntheticNodeStyle]
    text_regions: tuple[AnnotationTextRegion, ...]
    container: AnnotationContainer | None
    connectors: tuple[SyntheticConnector, ...]
    family_proposal: AnnotationFamilyProposal
    label_font_size: int

    def to_annotation_document(self, *, split: str | None = None, metadata: dict[str, object] | None = None) -> DetectorAnnotationDocument:
        output = DetectorModelOutput(
            image_id=self.sample_id,
            image_size=self.image_size,
            family_predictions=(self.family_proposal,),
            node_predictions=self.nodes,
            container_predictions=() if self.container is None else (self.container,),
            text_predictions=self.text_regions,
            port_predictions=tuple(
                port for connector in self.connectors for port in (connector.start_port, connector.end_port)
            ),
            connector_predictions=tuple(connector.candidate for connector in self.connectors),
            metadata={
                "generator": GENERATOR_NAME,
                "renderer": RENDERER_NAME,
                "synthetic_ground_truth": True,
                **(metadata or {}),
            },
        )
        document = _GT_ADAPTER.from_model_output(output)
        if split is None:
            return document
        return DetectorAnnotationDocument(
            image_id=document.image_id,
            image_size=document.image_size,
            schema_version=document.schema_version,
            image_path=document.image_path,
            split=split,
            family_proposals=document.family_proposals,
            text_regions=document.text_regions,
            diagram_instances=document.diagram_instances,
            primitive_scene=document.primitive_scene,
            metadata=document.metadata,
        )


_GT_ADAPTER = AnnotationMLAdapter(default_source="synthetic_gt", default_provenance_prefix="synthetic_gt")


def generate_slide_spec(
    rng: random.Random,
    *,
    sample_id: str,
    family: DiagramFamily = DiagramFamily.ORTHOGONAL_FLOW,
    image_size: AnnotationImageSize | None = None,
) -> SyntheticSlideSpec:
    if family not in SUPPORTED_FAMILIES:
        raise ValueError(f"unsupported synthetic family: {family.value} (supported: {[f.value for f in SUPPORTED_FAMILIES]})")
    size = image_size or AnnotationImageSize(width=1280, height=720)
    return _generate_orthogonal_flow_spec(rng, sample_id=sample_id, image_size=size)


def _generate_orthogonal_flow_spec(
    rng: random.Random,
    *,
    sample_id: str,
    image_size: AnnotationImageSize,
) -> SyntheticSlideSpec:
    horizontal = rng.random() < 0.7
    node_count = rng.randint(3, 6)
    node_kind = NodeKind.ROUNDED_BOX if rng.random() < 0.5 else NodeKind.BOX
    palette_index = rng.randrange(len(_FILL_PALETTE))
    style = SyntheticNodeStyle(fill=_FILL_PALETTE[palette_index], stroke=_STROKE_PALETTE[palette_index])

    width, height = float(image_size.width), float(image_size.height)
    margin_x, margin_y = width * 0.08, height * 0.12
    lane_extent = (width if horizontal else height) - 2 * (margin_x if horizontal else margin_y)
    slot = lane_extent / node_count
    gap = slot * rng.uniform(0.25, 0.4)
    node_extent = slot - gap
    cross_extent = (height if horizontal else width) * rng.uniform(0.14, 0.22)
    cross_center = (height if horizontal else width) * rng.uniform(0.35, 0.65)

    label_font_size = max(14, int(cross_extent * 0.3))
    font = ImageFont.load_default(size=label_font_size)
    labels = rng.sample(_LABEL_VOCAB, node_count)

    nodes: list[AnnotationNode] = []
    text_regions: list[AnnotationTextRegion] = []
    node_styles: dict[str, SyntheticNodeStyle] = {}
    for index in range(node_count):
        lane_start = (margin_x if horizontal else margin_y) + slot * index + gap / 2.0
        jitter = rng.uniform(-gap * 0.15, gap * 0.15)
        if horizontal:
            bbox = AnnotationBBox(
                x0=lane_start,
                y0=cross_center - cross_extent / 2.0 + jitter,
                x1=lane_start + node_extent,
                y1=cross_center + cross_extent / 2.0 + jitter,
            )
        else:
            bbox = AnnotationBBox(
                x0=cross_center - cross_extent / 2.0 + jitter,
                y0=lane_start,
                x1=cross_center + cross_extent / 2.0 + jitter,
                y1=lane_start + node_extent,
            )
        node_id = f"node:{sample_id}:{index}"
        label = labels[index]
        text_id = f"text:{sample_id}:{index}"
        nodes.append(
            AnnotationNode(
                id=node_id,
                kind=node_kind,
                bbox=bbox,
                confidence=1.0,
                label=label,
                text_region_ids=(text_id,),
                source="synthetic_gt",
                provenance=(f"{GENERATOR_NAME}:node",),
            )
        )
        node_styles[node_id] = style
        text_regions.append(
            AnnotationTextRegion(
                id=text_id,
                bbox=_label_bbox(label, font=font, node_bbox=bbox),
                confidence=1.0,
                role=TextRegionRole.LABEL,
                text=label,
                source="synthetic_gt",
                provenance=(f"{GENERATOR_NAME}:text",),
            )
        )

    connectors: list[SyntheticConnector] = []
    for index in range(node_count - 1):
        start_node, end_node = nodes[index], nodes[index + 1]
        if horizontal:
            start_side, end_side = PortSide.RIGHT, PortSide.LEFT
            start_point = AnnotationPoint(start_node.bbox.x1, (start_node.bbox.y0 + start_node.bbox.y1) / 2.0)
            end_point = AnnotationPoint(end_node.bbox.x0, (end_node.bbox.y0 + end_node.bbox.y1) / 2.0)
        else:
            start_side, end_side = PortSide.BOTTOM, PortSide.TOP
            start_point = AnnotationPoint((start_node.bbox.x0 + start_node.bbox.x1) / 2.0, start_node.bbox.y1)
            end_point = AnnotationPoint((end_node.bbox.x0 + end_node.bbox.x1) / 2.0, end_node.bbox.y0)
        connector_id = f"connector:{sample_id}:{index}"
        path = _orthogonal_path(start_point, end_point, horizontal=horizontal)
        connectors.append(
            SyntheticConnector(
                candidate=AnnotationConnectorCandidate(
                    id=connector_id,
                    kind=ConnectorKind.ARROW,
                    bbox=_path_bbox(path),
                    confidence=1.0,
                    source_evidence_id=f"evidence:{connector_id}",
                    path_points=path,
                    start_endpoint=AnnotationConnectorEndpoint(
                        point=start_point,
                        owner_id=start_node.id,
                        owner_kind=PortOwnerKind.NODE,
                        side=start_side,
                    ),
                    end_endpoint=AnnotationConnectorEndpoint(
                        point=end_point,
                        owner_id=end_node.id,
                        owner_kind=PortOwnerKind.NODE,
                        side=end_side,
                    ),
                    arrowhead_end=True,
                    source="synthetic_gt",
                    provenance=(f"{GENERATOR_NAME}:connector",),
                ),
                start_port=_port_for(start_node.id, sample_id, index, "start", side=start_side, point=start_point),
                end_port=_port_for(end_node.id, sample_id, index, "end", side=end_side, point=end_point),
                stroke=style.stroke,
            )
        )

    container: AnnotationContainer | None = None
    if rng.random() < 0.5:
        pad = min(width, height) * 0.04
        union = _union_bbox([node.bbox for node in nodes])
        container = AnnotationContainer(
            id=f"container:{sample_id}:0",
            kind=ContainerKind.FLOW_CLUSTER,
            bbox=AnnotationBBox(
                x0=max(2.0, union.x0 - pad),
                y0=max(2.0, union.y0 - pad),
                x1=min(width - 2.0, union.x1 + pad),
                y1=min(height - 2.0, union.y1 + pad),
            ),
            confidence=1.0,
            member_node_ids=tuple(node.id for node in nodes),
            source="synthetic_gt",
            provenance=(f"{GENERATOR_NAME}:container",),
        )

    focus = container.bbox if container is not None else _union_bbox(
        [node.bbox for node in nodes] + [connector.candidate.bbox for connector in connectors]
    )
    proposal = AnnotationFamilyProposal(
        id=f"family:{sample_id}:0",
        family=DiagramFamily.ORTHOGONAL_FLOW,
        confidence=1.0,
        focus_bbox=focus,
        evidence=(f"{GENERATOR_NAME}:layout",),
        provenance=(f"{GENERATOR_NAME}:family_proposal",),
    )

    return SyntheticSlideSpec(
        sample_id=sample_id,
        family=DiagramFamily.ORTHOGONAL_FLOW,
        image_size=image_size,
        nodes=tuple(nodes),
        node_styles=node_styles,
        text_regions=tuple(text_regions),
        container=container,
        connectors=tuple(connectors),
        family_proposal=proposal,
        label_font_size=label_font_size,
    )


def _port_for(owner_id: str, sample_id: str, index: int, role: str, *, side: PortSide, point: AnnotationPoint) -> AnnotationPort:
    return AnnotationPort(
        id=f"port:{sample_id}:{index}:{role}",
        owner_id=owner_id,
        owner_kind=PortOwnerKind.NODE,
        side=side,
        point=point,
        confidence=1.0,
        source="synthetic_gt",
        provenance=(f"{GENERATOR_NAME}:port",),
    )


def _orthogonal_path(start: AnnotationPoint, end: AnnotationPoint, *, horizontal: bool) -> tuple[AnnotationPoint, ...]:
    if horizontal and abs(start.y - end.y) > 0.5:
        mid_x = (start.x + end.x) / 2.0
        return (start, AnnotationPoint(mid_x, start.y), AnnotationPoint(mid_x, end.y), end)
    if not horizontal and abs(start.x - end.x) > 0.5:
        mid_y = (start.y + end.y) / 2.0
        return (start, AnnotationPoint(start.x, mid_y), AnnotationPoint(end.x, mid_y), end)
    return (start, end)


def _path_bbox(path: tuple[AnnotationPoint, ...], *, pad: float = 3.0) -> AnnotationBBox:
    xs = [point.x for point in path]
    ys = [point.y for point in path]
    return AnnotationBBox(x0=min(xs) - pad, y0=min(ys) - pad, x1=max(xs) + pad, y1=max(ys) + pad)


def _union_bbox(boxes: list[AnnotationBBox]) -> AnnotationBBox:
    return AnnotationBBox(
        x0=min(box.x0 for box in boxes),
        y0=min(box.y0 for box in boxes),
        x1=max(box.x1 for box in boxes),
        y1=max(box.y1 for box in boxes),
    )


def _label_bbox(label: str, *, font: ImageFont.ImageFont | ImageFont.FreeTypeFont, node_bbox: AnnotationBBox) -> AnnotationBBox:
    left, top, right, bottom = font.getbbox(label)
    text_width, text_height = float(right - left), float(bottom - top)
    center_x = (node_bbox.x0 + node_bbox.x1) / 2.0
    center_y = (node_bbox.y0 + node_bbox.y1) / 2.0
    return AnnotationBBox(
        x0=center_x - text_width / 2.0,
        y0=center_y - text_height / 2.0,
        x1=center_x + text_width / 2.0,
        y1=center_y + text_height / 2.0,
    )


def render_spec_image(spec: SyntheticSlideSpec) -> Image.Image:
    image = Image.new("RGB", (spec.image_size.width, spec.image_size.height), (255, 255, 255))
    draw = ImageDraw.Draw(image)

    if spec.container is not None:
        box = spec.container.bbox
        draw.rounded_rectangle(
            (box.x0, box.y0, box.x1, box.y1),
            radius=10,
            fill=(248, 250, 252),
            outline=(148, 163, 184),
            width=2,
        )

    for connector in spec.connectors:
        points = [(point.x, point.y) for point in connector.candidate.path_points]
        draw.line(points, fill=connector.stroke, width=3)
        if connector.candidate.arrowhead_end:
            _draw_arrowhead(draw, points[-2], points[-1], color=connector.stroke)

    for node in spec.nodes:
        style = spec.node_styles[node.id]
        box = (node.bbox.x0, node.bbox.y0, node.bbox.x1, node.bbox.y1)
        if node.kind is NodeKind.ROUNDED_BOX:
            draw.rounded_rectangle(box, radius=int(node.bbox.height * 0.2), fill=style.fill, outline=style.stroke, width=3)
        else:
            draw.rectangle(box, fill=style.fill, outline=style.stroke, width=3)

    font = ImageFont.load_default(size=spec.label_font_size)
    for text_region in spec.text_regions:
        if text_region.text is None:
            continue
        left, top, _, _ = font.getbbox(text_region.text)
        draw.text(
            (text_region.bbox.x0 - left, text_region.bbox.y0 - top),
            text_region.text,
            fill=(15, 23, 42),
            font=font,
        )

    return image


def _draw_arrowhead(
    draw: ImageDraw.ImageDraw,
    tail: tuple[float, float],
    tip: tuple[float, float],
    *,
    color: tuple[int, int, int],
    size: float = 10.0,
) -> None:
    dx, dy = tip[0] - tail[0], tip[1] - tail[1]
    length = max((dx * dx + dy * dy) ** 0.5, 1e-6)
    ux, uy = dx / length, dy / length
    px, py = -uy, ux
    base_x, base_y = tip[0] - ux * size, tip[1] - uy * size
    half = size * 0.5
    draw.polygon(
        [tip, (base_x + px * half, base_y + py * half), (base_x - px * half, base_y - py * half)],
        fill=color,
    )


def write_spec_pptx(spec: SyntheticSlideSpec, path: Path) -> None:
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
    from pptx.oxml.ns import qn
    from pptx.util import Emu, Pt

    presentation = Presentation()
    presentation.slide_width = Emu(spec.image_size.width * EMU_PER_PIXEL)
    presentation.slide_height = Emu(spec.image_size.height * EMU_PER_PIXEL)
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])

    def emu_box(bbox: AnnotationBBox) -> tuple[Emu, Emu, Emu, Emu]:
        return (
            Emu(int(bbox.x0 * EMU_PER_PIXEL)),
            Emu(int(bbox.y0 * EMU_PER_PIXEL)),
            Emu(int(bbox.width * EMU_PER_PIXEL)),
            Emu(int(bbox.height * EMU_PER_PIXEL)),
        )

    if spec.container is not None:
        shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, *emu_box(spec.container.bbox))
        shape.name = spec.container.id
        shape.fill.solid()
        shape.fill.fore_color.rgb = RGBColor(248, 250, 252)
        shape.line.color.rgb = RGBColor(148, 163, 184)
        shape.line.width = Pt(1.0)

    for node in spec.nodes:
        style = spec.node_styles[node.id]
        mso_shape = MSO_SHAPE.ROUNDED_RECTANGLE if node.kind is NodeKind.ROUNDED_BOX else MSO_SHAPE.RECTANGLE
        shape = slide.shapes.add_shape(mso_shape, *emu_box(node.bbox))
        shape.name = node.id
        shape.fill.solid()
        shape.fill.fore_color.rgb = RGBColor(*style.fill)
        shape.line.color.rgb = RGBColor(*style.stroke)
        shape.line.width = Pt(1.5)
        if node.label:
            shape.text_frame.text = node.label
            run = shape.text_frame.paragraphs[0].runs[0]
            run.font.size = Pt(14)
            run.font.color.rgb = RGBColor(15, 23, 42)

    for connector in spec.connectors:
        points = connector.candidate.effective_path_points()
        for start, end in zip(points, points[1:]):
            shape = slide.shapes.add_connector(
                MSO_CONNECTOR.STRAIGHT,
                Emu(int(start.x * EMU_PER_PIXEL)),
                Emu(int(start.y * EMU_PER_PIXEL)),
                Emu(int(end.x * EMU_PER_PIXEL)),
                Emu(int(end.y * EMU_PER_PIXEL)),
            )
            shape.name = connector.candidate.id
            shape.line.color.rgb = RGBColor(*connector.stroke)
            shape.line.width = Pt(2.0)
            if connector.candidate.arrowhead_end and end is points[-1]:
                line_element = shape.line._get_or_add_ln()
                tail = line_element.makeelement(qn("a:tailEnd"), {"type": "triangle"})
                line_element.append(tail)

    path.parent.mkdir(parents=True, exist_ok=True)
    presentation.save(path)


def validate_spec_contract(spec: SyntheticSlideSpec) -> None:
    """Guarantee generated ground truth satisfies the v3 SlideIR contract."""
    document = spec.to_annotation_document()
    slide_ir = _GT_ADAPTER.to_slide_ir(document)
    validate_slide_ir(slide_ir)
