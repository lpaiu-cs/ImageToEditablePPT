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

import math
import random
import zlib
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

# Container visual style for the PIL rasterizer. Containers are drawn with a
# visible, *varied* style picked per-sample (see _pick_container_style) so the
# detector learns container presence from a realistic range of boundaries rather
# than one fixed look. These module constants are the fallback used when a spec
# carries no explicit style; they are deliberately visible (a saturated outline),
# unlike the original near-invisible faint-gray rendering which made the
# container signal unlearnable.
CONTAINER_FILL = (248, 250, 252)
CONTAINER_OUTLINE = (71, 85, 105)
CONTAINER_OUTLINE_WIDTH = 3

# Palettes for per-sample container styling. Every outline is saturated/dark
# enough to be clearly visible against the white background and the light fills.
_CONTAINER_OUTLINE_PALETTE = (
    (71, 85, 105),    # slate
    (37, 99, 235),    # blue
    (190, 18, 60),    # rose
    (15, 118, 110),   # teal
    (180, 83, 9),     # amber
    (109, 40, 217),   # violet
)
_CONTAINER_FILL_PALETTE = (
    (255, 255, 255),  # white (border-only container)
    (248, 250, 252),  # slate-50
    (241, 245, 249),  # slate-100
    (239, 246, 255),  # blue-50
    (240, 253, 244),  # green-50
    (254, 249, 235),  # amber-50
)
_CONTAINER_OUTLINE_WIDTHS = (2, 3, 4)

SUPPORTED_FAMILIES = (
    DiagramFamily.ORTHOGONAL_FLOW,
    DiagramFamily.CYCLE,
    DiagramFamily.TABLE_MATRIX,
    DiagramFamily.BLOCK_FLOW,
)

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
class SyntheticContainerStyle:
    fill: tuple[int, int, int]
    outline: tuple[int, int, int]
    outline_width: int


def _pick_container_style(sample_id: str) -> SyntheticContainerStyle:
    """Pick a visible, varied container style deterministically from the sample id.

    Uses a dedicated RNG seeded from the id (not the main generation stream) so
    container styling does not perturb node/connector content — a dataset
    regenerated after this change keeps byte-identical ground truth and only the
    container's rendered appearance varies.
    """
    style_rng = random.Random(zlib.crc32(sample_id.encode("utf-8")))
    return SyntheticContainerStyle(
        fill=_CONTAINER_FILL_PALETTE[style_rng.randrange(len(_CONTAINER_FILL_PALETTE))],
        outline=_CONTAINER_OUTLINE_PALETTE[style_rng.randrange(len(_CONTAINER_OUTLINE_PALETTE))],
        outline_width=_CONTAINER_OUTLINE_WIDTHS[style_rng.randrange(len(_CONTAINER_OUTLINE_WIDTHS))],
    )


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
    container_style: SyntheticContainerStyle | None = None

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
    if family is DiagramFamily.CYCLE:
        return _generate_cycle_spec(rng, sample_id=sample_id, image_size=size)
    if family is DiagramFamily.TABLE_MATRIX:
        return _generate_table_matrix_spec(rng, sample_id=sample_id, image_size=size)
    if family is DiagramFamily.BLOCK_FLOW:
        return _generate_block_flow_spec(rng, sample_id=sample_id, image_size=size)
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
    container_style: SyntheticContainerStyle | None = None
    if rng.random() < 0.5:
        container_style = _pick_container_style(sample_id)
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
        container_style=container_style,
    )


def _generate_cycle_spec(
    rng: random.Random,
    *,
    sample_id: str,
    image_size: AnnotationImageSize,
) -> SyntheticSlideSpec:
    """Nodes evenly placed on a ring, linked into a closed directed loop."""
    node_count = rng.randint(3, 6)
    node_kind = NodeKind.ROUNDED_BOX if rng.random() < 0.5 else NodeKind.BOX
    palette_index = rng.randrange(len(_FILL_PALETTE))
    style = SyntheticNodeStyle(fill=_FILL_PALETTE[palette_index], stroke=_STROKE_PALETTE[palette_index])

    width, height = float(image_size.width), float(image_size.height)
    center_x, center_y = width / 2.0, height / 2.0
    radius_x = width * rng.uniform(0.27, 0.33)
    radius_y = height * rng.uniform(0.27, 0.33)
    node_half_w = width * rng.uniform(0.07, 0.09)
    node_half_h = height * rng.uniform(0.06, 0.08)
    start_angle = -math.pi / 2.0 + rng.uniform(-0.15, 0.15)

    label_font_size = max(14, int(node_half_h * 2.0 * 0.3))
    font = ImageFont.load_default(size=label_font_size)
    labels = rng.sample(_LABEL_VOCAB, node_count)

    nodes: list[AnnotationNode] = []
    text_regions: list[AnnotationTextRegion] = []
    node_styles: dict[str, SyntheticNodeStyle] = {}
    centers: list[AnnotationPoint] = []
    for index in range(node_count):
        angle = start_angle + 2.0 * math.pi * index / node_count
        cx = center_x + radius_x * math.cos(angle)
        cy = center_y + radius_y * math.sin(angle)
        centers.append(AnnotationPoint(cx, cy))
        bbox = AnnotationBBox(
            x0=cx - node_half_w,
            y0=cy - node_half_h,
            x1=cx + node_half_w,
            y1=cy + node_half_h,
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
    for index in range(node_count):
        start_node = nodes[index]
        end_node = nodes[(index + 1) % node_count]
        start_point, start_side = _edge_point_toward(start_node.bbox, centers[(index + 1) % node_count])
        end_point, end_side = _edge_point_toward(end_node.bbox, centers[index])
        connector_id = f"connector:{sample_id}:{index}"
        path = (start_point, end_point)
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
    container_style: SyntheticContainerStyle | None = None
    if rng.random() < 0.5:
        container_style = _pick_container_style(sample_id)
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
        family=DiagramFamily.CYCLE,
        confidence=1.0,
        focus_bbox=focus,
        evidence=(f"{GENERATOR_NAME}:layout",),
        provenance=(f"{GENERATOR_NAME}:family_proposal",),
    )

    return SyntheticSlideSpec(
        sample_id=sample_id,
        family=DiagramFamily.CYCLE,
        image_size=image_size,
        nodes=tuple(nodes),
        node_styles=node_styles,
        text_regions=tuple(text_regions),
        container=container,
        connectors=tuple(connectors),
        family_proposal=proposal,
        label_font_size=label_font_size,
        container_style=container_style,
    )


def _generate_table_matrix_spec(
    rng: random.Random,
    *,
    sample_id: str,
    image_size: AnnotationImageSize,
) -> SyntheticSlideSpec:
    """A regular grid of cell nodes — no connectors, no container."""
    rows = rng.randint(2, 3)
    cols = rng.randint(2, 4)
    node_kind = NodeKind.BOX if rng.random() < 0.6 else NodeKind.ROUNDED_BOX
    palette_index = rng.randrange(len(_FILL_PALETTE))
    style = SyntheticNodeStyle(fill=_FILL_PALETTE[palette_index], stroke=_STROKE_PALETTE[palette_index])

    width, height = float(image_size.width), float(image_size.height)
    margin_x, margin_y = width * 0.1, height * 0.12
    cell_w = (width - 2 * margin_x) / cols
    cell_h = (height - 2 * margin_y) / rows
    gap_x = cell_w * rng.uniform(0.12, 0.22)
    gap_y = cell_h * rng.uniform(0.18, 0.28)
    label_font_size = max(14, int((cell_h - gap_y) * 0.28))
    font = ImageFont.load_default(size=label_font_size)
    labels = rng.sample(_LABEL_VOCAB, rows * cols)

    nodes: list[AnnotationNode] = []
    text_regions: list[AnnotationTextRegion] = []
    node_styles: dict[str, SyntheticNodeStyle] = {}
    index = 0
    for row in range(rows):
        for col in range(cols):
            x0 = margin_x + col * cell_w + gap_x / 2.0
            y0 = margin_y + row * cell_h + gap_y / 2.0
            bbox = AnnotationBBox(x0=x0, y0=y0, x1=x0 + cell_w - gap_x, y1=y0 + cell_h - gap_y)
            node_id = f"node:{sample_id}:{index}"
            text_id = f"text:{sample_id}:{index}"
            label = labels[index]
            nodes.append(
                AnnotationNode(
                    id=node_id, kind=node_kind, bbox=bbox, confidence=1.0, label=label,
                    text_region_ids=(text_id,), source="synthetic_gt", provenance=(f"{GENERATOR_NAME}:node",),
                )
            )
            node_styles[node_id] = style
            text_regions.append(
                AnnotationTextRegion(
                    id=text_id, bbox=_label_bbox(label, font=font, node_bbox=bbox), confidence=1.0,
                    role=TextRegionRole.LABEL, text=label, source="synthetic_gt",
                    provenance=(f"{GENERATOR_NAME}:text",),
                )
            )
            index += 1

    focus = _union_bbox([node.bbox for node in nodes])
    proposal = AnnotationFamilyProposal(
        id=f"family:{sample_id}:0", family=DiagramFamily.TABLE_MATRIX, confidence=1.0, focus_bbox=focus,
        evidence=(f"{GENERATOR_NAME}:layout",), provenance=(f"{GENERATOR_NAME}:family_proposal",),
    )
    return SyntheticSlideSpec(
        sample_id=sample_id, family=DiagramFamily.TABLE_MATRIX, image_size=image_size, nodes=tuple(nodes),
        node_styles=node_styles, text_regions=tuple(text_regions), container=None, connectors=(),
        family_proposal=proposal, label_font_size=label_font_size, container_style=None,
    )


def _generate_block_flow_spec(
    rng: random.Random,
    *,
    sample_id: str,
    image_size: AnnotationImageSize,
) -> SyntheticSlideSpec:
    """A shallow tree: a root branches to children (and optionally grandchildren)."""
    node_kind = NodeKind.ROUNDED_BOX if rng.random() < 0.5 else NodeKind.BOX
    palette_index = rng.randrange(len(_FILL_PALETTE))
    style = SyntheticNodeStyle(fill=_FILL_PALETTE[palette_index], stroke=_STROKE_PALETTE[palette_index])

    width, height = float(image_size.width), float(image_size.height)
    child_count = rng.randint(2, 3)
    grand_count = rng.randint(0, 2)
    levels = 3 if grand_count > 0 else 2
    node_w, node_h = width * 0.16, height * 0.16
    margin_y = height * 0.1
    level_gap = (height - 2 * margin_y - node_h) / (levels - 1)
    label_font_size = max(14, int(node_h * 0.28))
    font = ImageFont.load_default(size=label_font_size)
    labels = rng.sample(_LABEL_VOCAB, 1 + child_count + grand_count)

    nodes: list[AnnotationNode] = []
    node_styles: dict[str, SyntheticNodeStyle] = {}
    text_regions: list[AnnotationTextRegion] = []

    def add_node(index: int, center_x: float, center_y: float) -> AnnotationNode:
        bbox = AnnotationBBox(
            x0=center_x - node_w / 2.0, y0=center_y - node_h / 2.0,
            x1=center_x + node_w / 2.0, y1=center_y + node_h / 2.0,
        )
        node_id = f"node:{sample_id}:{index}"
        text_id = f"text:{sample_id}:{index}"
        label = labels[index]
        node = AnnotationNode(
            id=node_id, kind=node_kind, bbox=bbox, confidence=1.0, label=label,
            text_region_ids=(text_id,), source="synthetic_gt", provenance=(f"{GENERATOR_NAME}:node",),
        )
        nodes.append(node)
        node_styles[node_id] = style
        text_regions.append(
            AnnotationTextRegion(
                id=text_id, bbox=_label_bbox(label, font=font, node_bbox=bbox), confidence=1.0,
                role=TextRegionRole.LABEL, text=label, source="synthetic_gt",
                provenance=(f"{GENERATOR_NAME}:text",),
            )
        )
        return node

    root = add_node(0, width / 2.0, margin_y + node_h / 2.0)
    child_y = margin_y + node_h / 2.0 + level_gap
    children = [add_node(1 + i, width * (i + 1) / (child_count + 1), child_y) for i in range(child_count)]
    grandchildren: list[AnnotationNode] = []
    if grand_count > 0:
        base_cx = (children[0].bbox.x0 + children[0].bbox.x1) / 2.0
        grand_y = margin_y + node_h / 2.0 + 2 * level_gap
        for j in range(grand_count):
            gx = base_cx + (j - (grand_count - 1) / 2.0) * node_w * 1.3
            grandchildren.append(add_node(1 + child_count + j, gx, grand_y))

    edges = [(root, child) for child in children] + [(children[0], g) for g in grandchildren]
    connectors: list[SyntheticConnector] = []
    for index, (parent, child) in enumerate(edges):
        parent_center = AnnotationPoint((parent.bbox.x0 + parent.bbox.x1) / 2.0, (parent.bbox.y0 + parent.bbox.y1) / 2.0)
        child_center = AnnotationPoint((child.bbox.x0 + child.bbox.x1) / 2.0, (child.bbox.y0 + child.bbox.y1) / 2.0)
        start_point, start_side = _edge_point_toward(parent.bbox, child_center)
        end_point, end_side = _edge_point_toward(child.bbox, parent_center)
        connector_id = f"connector:{sample_id}:{index}"
        path = (start_point, end_point)
        connectors.append(
            SyntheticConnector(
                candidate=AnnotationConnectorCandidate(
                    id=connector_id, kind=ConnectorKind.ARROW, bbox=_path_bbox(path), confidence=1.0,
                    source_evidence_id=f"evidence:{connector_id}", path_points=path,
                    start_endpoint=AnnotationConnectorEndpoint(
                        point=start_point, owner_id=parent.id, owner_kind=PortOwnerKind.NODE, side=start_side),
                    end_endpoint=AnnotationConnectorEndpoint(
                        point=end_point, owner_id=child.id, owner_kind=PortOwnerKind.NODE, side=end_side),
                    arrowhead_end=True, source="synthetic_gt", provenance=(f"{GENERATOR_NAME}:connector",),
                ),
                start_port=_port_for(parent.id, sample_id, index, "start", side=start_side, point=start_point),
                end_port=_port_for(child.id, sample_id, index, "end", side=end_side, point=end_point),
                stroke=style.stroke,
            )
        )

    container: AnnotationContainer | None = None
    container_style: SyntheticContainerStyle | None = None
    if rng.random() < 0.4:
        container_style = _pick_container_style(sample_id)
        pad = min(width, height) * 0.04
        union = _union_bbox([node.bbox for node in nodes])
        container = AnnotationContainer(
            id=f"container:{sample_id}:0", kind=ContainerKind.FLOW_CLUSTER,
            bbox=AnnotationBBox(
                x0=max(2.0, union.x0 - pad), y0=max(2.0, union.y0 - pad),
                x1=min(width - 2.0, union.x1 + pad), y1=min(height - 2.0, union.y1 + pad)),
            confidence=1.0, member_node_ids=tuple(node.id for node in nodes), source="synthetic_gt",
            provenance=(f"{GENERATOR_NAME}:container",),
        )

    focus = container.bbox if container is not None else _union_bbox(
        [node.bbox for node in nodes] + [connector.candidate.bbox for connector in connectors]
    )
    proposal = AnnotationFamilyProposal(
        id=f"family:{sample_id}:0", family=DiagramFamily.BLOCK_FLOW, confidence=1.0, focus_bbox=focus,
        evidence=(f"{GENERATOR_NAME}:layout",), provenance=(f"{GENERATOR_NAME}:family_proposal",),
    )
    return SyntheticSlideSpec(
        sample_id=sample_id, family=DiagramFamily.BLOCK_FLOW, image_size=image_size, nodes=tuple(nodes),
        node_styles=node_styles, text_regions=tuple(text_regions), container=container, connectors=tuple(connectors),
        family_proposal=proposal, label_font_size=label_font_size, container_style=container_style,
    )


def _edge_point_toward(bbox: AnnotationBBox, target: AnnotationPoint) -> tuple[AnnotationPoint, PortSide]:
    """Point on ``bbox``'s edge along the ray toward ``target``, and that edge's side."""
    center_x = (bbox.x0 + bbox.x1) / 2.0
    center_y = (bbox.y0 + bbox.y1) / 2.0
    half_w = (bbox.x1 - bbox.x0) / 2.0
    half_h = (bbox.y1 - bbox.y0) / 2.0
    dx = target.x - center_x
    dy = target.y - center_y
    scale_x = half_w / abs(dx) if abs(dx) > 1e-9 else math.inf
    scale_y = half_h / abs(dy) if abs(dy) > 1e-9 else math.inf
    scale = min(scale_x, scale_y)
    point = AnnotationPoint(center_x + dx * scale, center_y + dy * scale)
    if scale_x <= scale_y:
        side = PortSide.RIGHT if dx >= 0 else PortSide.LEFT
    else:
        side = PortSide.BOTTOM if dy >= 0 else PortSide.TOP
    return point, side


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
        style = spec.container_style
        draw.rounded_rectangle(
            (box.x0, box.y0, box.x1, box.y1),
            radius=10,
            fill=style.fill if style is not None else CONTAINER_FILL,
            outline=style.outline if style is not None else CONTAINER_OUTLINE,
            width=style.outline_width if style is not None else CONTAINER_OUTLINE_WIDTH,
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
    from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
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
        shape.shadow.inherit = False
        shape.fill.solid()
        shape.fill.fore_color.rgb = RGBColor(248, 250, 252)
        shape.line.color.rgb = RGBColor(148, 163, 184)
        shape.line.width = Pt(1.0)

    for node in spec.nodes:
        style = spec.node_styles[node.id]
        mso_shape = MSO_SHAPE.ROUNDED_RECTANGLE if node.kind is NodeKind.ROUNDED_BOX else MSO_SHAPE.RECTANGLE
        shape = slide.shapes.add_shape(mso_shape, *emu_box(node.bbox))
        shape.name = node.id
        shape.shadow.inherit = False
        shape.fill.solid()
        shape.fill.fore_color.rgb = RGBColor(*style.fill)
        shape.line.color.rgb = RGBColor(*style.stroke)
        shape.line.width = Pt(1.5)
        if node.label:
            text_frame = shape.text_frame
            text_frame.text = node.label
            text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE
            paragraph = text_frame.paragraphs[0]
            paragraph.alignment = PP_ALIGN.CENTER
            run = paragraph.runs[0]
            # 1 pt = 4/3 px at 96 dpi; keep the pptx text height aligned
            # with the rendered label so GT bboxes stay meaningful.
            run.font.size = Pt(max(8, round(spec.label_font_size * 0.75)))
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


def find_soffice() -> str | None:
    """Locate a LibreOffice binary for pptx -> png rendering, if installed."""
    import shutil

    binary = shutil.which("soffice")
    if binary:
        return binary
    mac_path = Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")
    if mac_path.exists():
        return str(mac_path)
    return None


def render_pptx_batch_via_soffice(
    pptx_paths: list[Path],
    *,
    output_dir: Path,
    image_size: AnnotationImageSize,
    soffice_binary: str | None = None,
) -> None:
    """Convert pptx files to png in one soffice invocation (per-call startup is slow).

    LibreOffice exports at 96 dpi, which matches the 1 px = 9525 EMU slide
    contract, so output size normally equals ``image_size`` already; resize
    only as a safety net.
    """
    import subprocess

    binary = soffice_binary or find_soffice()
    if binary is None:
        raise RuntimeError("LibreOffice (soffice) not found; install it or use the pil renderer")
    if not pptx_paths:
        return
    output_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [binary, "--headless", "--convert-to", "png", "--outdir", str(output_dir), *map(str, pptx_paths)],
        check=True,
        capture_output=True,
        timeout=120 + 10 * len(pptx_paths),
    )
    expected = (image_size.width, image_size.height)
    for pptx_path in pptx_paths:
        png_path = output_dir / f"{pptx_path.stem}.png"
        if not png_path.exists():
            raise RuntimeError(f"soffice did not produce {png_path}")
        with Image.open(png_path) as image:
            if image.size != expected:
                image.convert("RGB").resize(expected, Image.LANCZOS).save(png_path)


def validate_spec_contract(spec: SyntheticSlideSpec) -> None:
    """Guarantee generated ground truth satisfies the v3 SlideIR contract."""
    document = spec.to_annotation_document()
    slide_ir = _GT_ADAPTER.to_slide_ir(document)
    validate_slide_ir(slide_ir)
