from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from image_to_editable_ppt.v3.app.config import V3Config
from image_to_editable_ppt.v3.core.enums import ContainerKind, DiagramFamily, NodeKind
from image_to_editable_ppt.v3.core.types import BBox
from image_to_editable_ppt.v3.ir.models import DiagramContainer, DiagramInstance, DiagramNode, FamilyProposal, RasterLayerResult, ResidualStructuralCanvas, TextLayerResult, TextRegion


@dataclass(slots=True, frozen=True)
class OrthogonalFlowDetector:
    family: DiagramFamily = DiagramFamily.ORTHOGONAL_FLOW

    def detect(
        self,
        canvas: ResidualStructuralCanvas,
        *,
        text_layer: TextLayerResult,
        raster_layer: RasterLayerResult,
        config: V3Config,
    ) -> tuple[FamilyProposal, ...]:
        del raster_layer, config
        ink_mask = _ink_mask(canvas.image)
        component_boxes = _component_boxes(ink_mask)
        if not component_boxes:
            return ()

        proposals: list[FamilyProposal] = []
        slide_area = float(max(1, canvas.image.shape[0] * canvas.image.shape[1]))
        expansion = max(6.0, min(canvas.image.shape[:2]) / 32.0)
        for proposal_index, component_bbox in enumerate(
            sorted(component_boxes, key=lambda item: (item.y0, item.x0)),
            start=1,
        ):
            nearby_text_regions = tuple(
                region
                for region in text_layer.regions
                if component_bbox.expand(expansion).overlaps(region.bbox)
                or component_bbox.expand(expansion).contains_point(region.bbox.center)
            )
            focus_sources = [component_bbox.expand(expansion), *(region.bbox for region in nearby_text_regions)]
            focus_bbox = _clip_bbox(
                _merge_bboxes(focus_sources),
                width=canvas.image.shape[1],
                height=canvas.image.shape[0],
            )
            ink_ratio = component_bbox.area / slide_area
            confidence = min(0.92, 0.38 + min(0.30, ink_ratio * 6.0) + min(0.16, 0.06 * len(nearby_text_regions)))
            proposals.append(
                FamilyProposal(
                    id=f"family:orthogonal_flow:{proposal_index}",
                    family=self.family,
                    confidence=confidence,
                    evidence=(
                        f"component_bbox={component_bbox.to_dict()}",
                        f"nearby_text_region_count={len(nearby_text_regions)}",
                        f"component_area_ratio={ink_ratio:.4f}",
                    ),
                    provenance=("branch:structural_canvas", "detector:connected_component_clusters"),
                    focus_bbox=focus_bbox,
                )
            )
        return tuple(proposals)


@dataclass(slots=True, frozen=True)
class OrthogonalFlowParser:
    family: DiagramFamily = DiagramFamily.ORTHOGONAL_FLOW

    def parse(
        self,
        canvas: ResidualStructuralCanvas,
        *,
        proposals: tuple[FamilyProposal, ...],
        text_layer: TextLayerResult,
        raster_layer: RasterLayerResult,
        config: V3Config,
    ) -> tuple[DiagramInstance, ...]:
        del raster_layer, config
        instances: list[DiagramInstance] = []
        accepted_nodes: list[DiagramNode] = []

        for proposal in proposals:
            if proposal.focus_bbox is None:
                continue
            instance_id = f"diagram:{proposal.family.value}:{len(instances) + 1}"
            member_regions = tuple(
                region
                for region in text_layer.regions
                if proposal.focus_bbox.overlaps(region.bbox) or proposal.focus_bbox.contains_point(region.bbox.center)
            )
            node_boxes = _find_node_boxes(canvas.image, proposal.focus_bbox)
            nodes = _build_nodes(instance_id=instance_id, proposal=proposal, node_boxes=node_boxes, member_regions=member_regions)
            if not nodes:
                continue
            if all(any(node.bbox.iou(existing.bbox) >= 0.85 for existing in accepted_nodes) for node in nodes):
                continue
            containers = _build_containers(instance_id=instance_id, proposal=proposal, nodes=tuple(nodes))
            instance_bbox = _merge_bboxes(
                [*(container.bbox for container in containers), *(node.bbox for node in nodes)]
            )
            instances.append(
                DiagramInstance(
                    id=instance_id,
                    family=proposal.family,
                    confidence=max(0.0, min(1.0, proposal.confidence - 0.02)),
                    bbox=instance_bbox,
                    containers=tuple(containers),
                    nodes=tuple(nodes),
                    text_region_ids=tuple(dict.fromkeys(region.id for region in member_regions)),
                    source_proposal_ids=(proposal.id,),
                    provenance=("family:orthogonal_flow", "parser:node_container_split"),
                )
            )
            accepted_nodes.extend(nodes)
        return tuple(instances)


def _ink_mask(image: np.ndarray) -> np.ndarray:
    _, threshold = cv2.threshold(image, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    return threshold


def _component_boxes(mask: np.ndarray) -> tuple[BBox, ...]:
    component_count, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    height, width = mask.shape
    image_area = height * width
    min_component_area = max(18, image_area // 500)
    boxes: list[BBox] = []
    for component_index in range(1, component_count):
        x, y, w, h, area = stats[component_index]
        if area < min_component_area or w < 6 or h < 6:
            continue
        boxes.append(BBox(float(x), float(y), float(x + w), float(y + h)))
    return tuple(boxes)


def _find_node_boxes(image: np.ndarray, focus_bbox: BBox) -> tuple[BBox, ...]:
    x0, y0, x1, y1 = (int(round(value)) for value in (focus_bbox.x0, focus_bbox.y0, focus_bbox.x1, focus_bbox.y1))
    crop = image[y0:y1, x0:x1]
    if crop.size == 0:
        return ()
    _, binary = cv2.threshold(crop, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    contours, hierarchy = cv2.findContours(binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is None:
        return ()

    min_box_area = max(120.0, focus_bbox.area * 0.035)
    candidates: list[BBox] = []
    for contour_index, contour in enumerate(contours):
        rect_x, rect_y, rect_w, rect_h = cv2.boundingRect(contour)
        if rect_w < 18 or rect_h < 16:
            continue
        contour_area = cv2.contourArea(contour)
        if contour_area < min_box_area:
            continue
        perimeter = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.03 * perimeter, True)
        if len(approx) < 4 or len(approx) > 8:
            continue
        rectangularity = contour_area / float(max(1, rect_w * rect_h))
        if rectangularity < 0.5:
            continue
        parent_index = hierarchy[0][contour_index][3]
        candidate = BBox(float(x0 + rect_x), float(y0 + rect_y), float(x0 + rect_x + rect_w), float(y0 + rect_y + rect_h))
        if parent_index < 0 and candidate.area >= focus_bbox.area * 0.85:
            continue
        if candidate.area >= focus_bbox.area * 0.96:
            continue
        candidates.append(candidate)
    return _dedupe_bboxes(candidates)


def _build_nodes(
    *,
    instance_id: str,
    proposal: FamilyProposal,
    node_boxes: tuple[BBox, ...],
    member_regions: tuple[TextRegion, ...],
) -> list[DiagramNode]:
    del proposal
    nodes: list[DiagramNode] = []
    if node_boxes:
        for node_index, node_bbox in enumerate(sorted(node_boxes, key=lambda item: (item.y0, item.x0)), start=1):
            attached_regions = tuple(
                region
                for region in member_regions
                if node_bbox.contains_point(region.bbox.center)
            )
            label = "\n".join(region.text for region in attached_regions if region.text) or None
            nodes.append(
                DiagramNode(
                    id=f"{instance_id}:node:{node_index}",
                    kind=NodeKind.BOX,
                    bbox=node_bbox,
                    confidence=0.82 if attached_regions else 0.58,
                    label=label,
                    text_region_ids=tuple(region.id for region in attached_regions),
                    source="phase4_parser:rectangular_contour",
                    provenance=("family:orthogonal_flow", "signal:rectangular_contour"),
                )
            )
    # Text alone is not geometric evidence for a box. Returning no node is the
    # conservative result; the text branch may still preserve a trusted title.
    return nodes


def _build_containers(
    *,
    instance_id: str,
    proposal: FamilyProposal,
    nodes: tuple[DiagramNode, ...],
) -> list[DiagramContainer]:
    if not nodes:
        return []
    if len(nodes) < 2:
        return []
    return [
        DiagramContainer(
            id=f"{instance_id}:container:1",
            kind=ContainerKind.FLOW_CLUSTER,
            bbox=proposal.focus_bbox,
            confidence=min(0.76, 0.5 + 0.08 * len(nodes)),
            member_node_ids=tuple(node.id for node in nodes),
            source="phase4_parser:proposal_envelope",
            provenance=("family:orthogonal_flow", "signal:proposal_envelope"),
        )
    ]


def _merge_bboxes(boxes: tuple[BBox, ...] | list[BBox]) -> BBox:
    ordered = list(boxes)
    if not ordered:
        raise ValueError("cannot merge an empty bbox collection")
    return BBox(
        min(box.x0 for box in ordered),
        min(box.y0 for box in ordered),
        max(box.x1 for box in ordered),
        max(box.y1 for box in ordered),
    )


def _clip_bbox(bbox: BBox, *, width: int, height: int) -> BBox:
    return BBox(
        max(0.0, min(float(width), bbox.x0)),
        max(0.0, min(float(height), bbox.y0)),
        max(0.0, min(float(width), bbox.x1)),
        max(0.0, min(float(height), bbox.y1)),
    )


def _dedupe_bboxes(boxes: list[BBox]) -> tuple[BBox, ...]:
    deduped: list[BBox] = []
    for candidate in sorted(boxes, key=lambda item: item.area, reverse=True):
        if any(candidate.iou(existing) >= 0.82 for existing in deduped):
            continue
        deduped.append(candidate)
    filtered: list[BBox] = []
    for candidate in deduped:
        contained_children = [
            other
            for other in deduped
            if other is not candidate and candidate.contains_point(other.center) and candidate.area > other.area * 1.4
        ]
        intersecting_children = [
            other
            for other in deduped
            if other is not candidate
            and candidate.area > other.area * 1.4
            and _intersection_fraction(other, candidate) >= 0.18
        ]
        # Connector strokes can close a large rectangular contour across four
        # neighbouring boxes without containing any box centre. It is not a new
        # node; keeping it makes text ownership and connector attachment collapse.
        if len(contained_children) >= 2 or len(intersecting_children) >= 3:
            continue
        filtered.append(candidate)
    return tuple(sorted(filtered, key=lambda item: (item.y0, item.x0)))


def _intersection_fraction(subject: BBox, other: BBox) -> float:
    x0 = max(subject.x0, other.x0)
    y0 = max(subject.y0, other.y0)
    x1 = min(subject.x1, other.x1)
    y1 = min(subject.y1, other.y1)
    if x1 <= x0 or y1 <= y0 or subject.area <= 0.0:
        return 0.0
    return ((x1 - x0) * (y1 - y0)) / subject.area
