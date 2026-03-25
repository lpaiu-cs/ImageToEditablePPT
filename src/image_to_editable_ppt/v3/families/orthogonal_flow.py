from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from image_to_editable_ppt.v3.app.config import V3Config
from image_to_editable_ppt.v3.core.enums import DiagramFamily, NodeKind
from image_to_editable_ppt.v3.core.types import BBox
from image_to_editable_ppt.v3.ir.models import DiagramInstance, DiagramNode, FamilyProposal, RasterLayerResult, ResidualStructuralCanvas, TextLayerResult


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
        dark_pixel_count = int(np.count_nonzero(ink_mask))
        min_dark_pixels = max(24, (canvas.image.shape[0] * canvas.image.shape[1]) // 180)
        if dark_pixel_count < min_dark_pixels:
            return ()

        component_boxes = _component_boxes(ink_mask)
        if not component_boxes:
            return ()

        focus_sources = [*component_boxes, *(region.bbox for region in text_layer.regions)]
        focus_bbox = _clip_bbox(
            _merge_bboxes(focus_sources).expand(
                max(6.0, min(canvas.image.shape[:2]) / 32.0)
            ),
            width=canvas.image.shape[1],
            height=canvas.image.shape[0],
        )
        ink_ratio = dark_pixel_count / float(max(1, canvas.image.shape[0] * canvas.image.shape[1]))
        confidence = min(0.9, 0.42 + 0.06 * len(text_layer.regions) + min(0.22, ink_ratio * 4.0))
        return (
            FamilyProposal(
                id="family:orthogonal_flow:1",
                family=self.family,
                confidence=confidence,
                evidence=(
                    f"text_region_count={len(text_layer.regions)}",
                    f"residual_dark_pixel_count={dark_pixel_count}",
                    f"component_count={len(component_boxes)}",
                ),
                provenance=("branch:structural_canvas", "detector:orthogonal_flow_skeleton"),
                focus_bbox=focus_bbox,
            ),
        )


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
        height, width = canvas.image.shape[:2]
        node_padding = max(8.0, min(height, width) / 26.0)

        for proposal in proposals:
            if proposal.focus_bbox is None:
                continue
            member_regions = tuple(
                region
                for region in text_layer.regions
                if proposal.focus_bbox.overlaps(region.bbox) or proposal.focus_bbox.contains_point(region.bbox.center)
            )
            nodes: list[DiagramNode] = []
            if member_regions:
                for node_index, region in enumerate(sorted(member_regions, key=lambda item: (item.bbox.y0, item.bbox.x0)), start=1):
                    node_bbox = _clip_bbox(region.bbox.expand(node_padding), width=width, height=height)
                    nodes.append(
                        DiagramNode(
                            id=f"{proposal.id}:node:{node_index}",
                            kind=NodeKind.BOX,
                            bbox=node_bbox,
                            label=region.text,
                            text_region_ids=(region.id,),
                        )
                    )
            else:
                nodes.append(
                    DiagramNode(
                        id=f"{proposal.id}:node:1",
                        kind=NodeKind.BOX,
                        bbox=proposal.focus_bbox,
                    )
                )

            instance_bbox = _merge_bboxes(tuple(node.bbox for node in nodes))
            instances.append(
                DiagramInstance(
                    id=f"diagram:{proposal.family.value}:{len(instances) + 1}",
                    family=proposal.family,
                    confidence=max(0.0, min(1.0, proposal.confidence - 0.03)),
                    bbox=instance_bbox,
                    nodes=tuple(nodes),
                    text_region_ids=tuple(region.id for region in member_regions),
                    source_proposal_ids=(proposal.id,),
                )
            )
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
