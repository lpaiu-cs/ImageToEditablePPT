"""Visual annotation assistance built from the frozen Phase 15 detectors.

The output of this module is never ground truth by itself.  It only creates a
numbered overlay and a reviewable draft that must receive two manual passes
before the Phase 16 validator will consider it frozen.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Any, Iterable

import cv2
import numpy as np

from image_to_editable_ppt.ml.annotation_schema import (
    AnnotationBBox,
    AnnotationContainer,
    AnnotationNode,
)
from image_to_editable_ppt.ml.visual_connectors import visual_connectors
from image_to_editable_ppt.ml.visual_geometry import GeometryCandidate, detect_visual_geometry
from image_to_editable_ppt.v3.core.enums import ContainerKind, NodeKind


@dataclass(slots=True, frozen=True)
class DraftCandidate:
    bbox: tuple[float, float, float, float]
    role: str
    shape_kind: str
    scales: tuple[int, ...]
    sources: tuple[str, ...]

    @property
    def area(self) -> float:
        x0, y0, x1, y1 = self.bbox
        return max(0.0, x1 - x0) * max(0.0, y1 - y0)


def _iou(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> float:
    ax0, ay0, ax1, ay1 = first
    bx0, by0, bx1, by1 = second
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    intersection = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    area_a = max(0.0, ax1 - ax0) * max(0.0, ay1 - ay0)
    area_b = max(0.0, bx1 - bx0) * max(0.0, by1 - by0)
    union = area_a + area_b - intersection
    return intersection / union if union > 0.0 else 0.0


def _candidate_from_geometry(
    candidate: GeometryCandidate,
    *,
    role: str,
    level_width: int,
    scale_to_original: float,
) -> DraftCandidate:
    x0, y0, x1, y1 = candidate.bbox
    shape_kind = "ellipse" if candidate.source == "closed_ellipse" else (
        "rounded_rectangle" if candidate.source == "uniform_fill" else "rectangle"
    )
    return DraftCandidate(
        bbox=(
            x0 * scale_to_original,
            y0 * scale_to_original,
            x1 * scale_to_original,
            y1 * scale_to_original,
        ),
        role=role,
        shape_kind=shape_kind,
        scales=(level_width,),
        sources=(candidate.source,),
    )


def fuse_draft_candidates(candidates: Iterable[DraftCandidate]) -> tuple[DraftCandidate, ...]:
    clusters: list[list[DraftCandidate]] = []
    for candidate in sorted(candidates, key=lambda item: item.area, reverse=True):
        match: list[DraftCandidate] | None = None
        for cluster in clusters:
            representative = cluster[0]
            if _iou(candidate.bbox, representative.bbox) >= 0.58:
                match = cluster
                break
            ax0, ay0, ax1, ay1 = candidate.bbox
            bx0, by0, bx1, by1 = representative.bbox
            scale = max(8.0, min(ax1 - ax0, ay1 - ay0, bx1 - bx0, by1 - by0))
            edge_error = max(abs(ax0 - bx0), abs(ay0 - by0), abs(ax1 - bx1), abs(ay1 - by1))
            if edge_error <= 0.08 * scale:
                match = cluster
                break
        if match is None:
            clusters.append([candidate])
        else:
            match.append(candidate)

    fused: list[DraftCandidate] = []
    for cluster in clusters:
        bbox = tuple(median(item.bbox[index] for item in cluster) for index in range(4))
        role_votes = {role: sum(item.role == role for item in cluster) for role in ("node", "container")}
        shape_votes = {
            shape: sum(item.shape_kind == shape for item in cluster)
            for shape in ("rectangle", "rounded_rectangle", "ellipse")
        }
        fused.append(
            DraftCandidate(
                bbox=bbox,
                role=max(role_votes, key=role_votes.get),
                shape_kind=max(shape_votes, key=shape_votes.get),
                scales=tuple(sorted({scale for item in cluster for scale in item.scales})),
                sources=tuple(sorted({source for item in cluster for source in item.sources})),
            )
        )
    return tuple(
        sorted(
            fused,
            key=lambda item: (item.bbox[1], item.bbox[0], item.bbox[3], item.bbox[2]),
        )
    )


def draft_structural_annotation(rgb: np.ndarray, *, image_id: str) -> dict[str, Any]:
    image = np.asarray(rgb, dtype=np.uint8)
    original_height, original_width = image.shape[:2]
    raw: list[DraftCandidate] = []
    seen_level_widths: set[int] = set()
    for target_width in (768, 1280, 2048):
        level_width = min(original_width, target_width)
        if level_width in seen_level_widths:
            continue
        seen_level_widths.add(level_width)
        if level_width == original_width:
            level = image
        else:
            level_height = max(1, round(original_height * level_width / original_width))
            level = cv2.resize(image, (level_width, level_height), interpolation=cv2.INTER_AREA)
        geometry = detect_visual_geometry(level)
        scale_to_original = original_width / float(level_width)
        raw.extend(
            _candidate_from_geometry(
                item,
                role="node",
                level_width=level_width,
                scale_to_original=scale_to_original,
            )
            for item in geometry.nodes
        )
        raw.extend(
            _candidate_from_geometry(
                item,
                role="container",
                level_width=level_width,
                scale_to_original=scale_to_original,
            )
            for item in geometry.containers
        )
    fused = list(fuse_draft_candidates(raw))
    image_area = original_width * original_height
    fused = [
        item
        for item in fused
        if item.area < image_area * 0.96
        and item.bbox[2] - item.bbox[0] >= max(12.0, original_width * 0.015)
        and item.bbox[3] - item.bbox[1] >= max(10.0, original_height * 0.015)
    ]

    objects: list[dict[str, Any]] = []
    for index, candidate in enumerate(fused, start=1):
        objects.append(
            {
                "id": f"object:auto:{index:03d}",
                "role": candidate.role,
                "shape_kind": candidate.shape_kind,
                "bbox": {
                    "x0": round(candidate.bbox[0], 2),
                    "y0": round(candidate.bbox[1], 2),
                    "x1": round(candidate.bbox[2], 2),
                    "y1": round(candidate.bbox[3], 2),
                },
                "parent_id": None,
                "importance": "secondary",
                "label": None,
                "ambiguity_note": (
                    "Frozen Phase 15 annotation assist; manual acceptance required. "
                    f"scales={candidate.scales}; sources={candidate.sources}"
                ),
            }
        )

    by_id = {item["id"]: item for item in objects}
    containers = [item for item in objects if item["role"] == "container"]
    for item in objects:
        if item["role"] == "container":
            continue
        bbox = item["bbox"]
        containing: list[tuple[float, dict[str, Any]]] = []
        for container in containers:
            cb = container["bbox"]
            if (
                bbox["x0"] >= cb["x0"] - 2
                and bbox["y0"] >= cb["y0"] - 2
                and bbox["x1"] <= cb["x1"] + 2
                and bbox["y1"] <= cb["y1"] + 2
            ):
                area = (cb["x1"] - cb["x0"]) * (cb["y1"] - cb["y0"])
                containing.append((area, container))
        if containing:
            item["parent_id"] = min(containing, key=lambda pair: pair[0])[1]["id"]

    nodes_for_connectors: list[AnnotationNode] = []
    containers_for_connectors: list[AnnotationContainer] = []
    for item in objects:
        bbox = item["bbox"]
        annotation_bbox = AnnotationBBox(
            x0=float(bbox["x0"]),
            y0=float(bbox["y0"]),
            x1=float(bbox["x1"]),
            y1=float(bbox["y1"]),
        )
        if item["role"] == "container":
            members = tuple(
                child_id
                for child_id, child in by_id.items()
                if child.get("parent_id") == item["id"]
            )
            containers_for_connectors.append(
                AnnotationContainer(
                    id=str(item["id"]),
                    kind=ContainerKind.FLOW_CLUSTER,
                    bbox=annotation_bbox,
                    confidence=0.8,
                    member_node_ids=members,
                    source="phase16_annotation_assist",
                    provenance=("phase16_annotation_assist:frozen_phase15",),
                )
            )
        else:
            kind = NodeKind.ELLIPSE if item["shape_kind"] == "ellipse" else (
                NodeKind.ROUNDED_BOX
                if item["shape_kind"] == "rounded_rectangle"
                else NodeKind.BOX
            )
            nodes_for_connectors.append(
                AnnotationNode(
                    id=str(item["id"]),
                    kind=kind,
                    bbox=annotation_bbox,
                    confidence=0.8,
                    source="phase16_annotation_assist",
                    provenance=("phase16_annotation_assist:frozen_phase15",),
                )
            )
    connector_candidates, _ = visual_connectors(
        image,
        nodes_for_connectors,
        containers=containers_for_connectors,
        image_id=image_id,
    )
    connectors: list[dict[str, Any]] = []
    for index, connector in enumerate(connector_candidates, start=1):
        if connector.start_endpoint is None or connector.end_endpoint is None:
            continue
        connectors.append(
            {
                "id": f"connector:auto:{index:03d}",
                "source_id": connector.start_endpoint.owner_id,
                "target_id": connector.end_endpoint.owner_id,
                "direction": "directed" if connector.arrowhead_end else "undirected",
                "path_class": "direct_orthogonal",
                "importance": "secondary",
                "path_points": [
                    {"x": round(point.x, 2), "y": round(point.y, 2)}
                    for point in connector.path_points
                ],
                "ambiguity_note": "Frozen Phase 15 direct-gap assist; manual endpoint review required.",
            }
        )
    return {
        "objects": objects,
        "connectors": connectors,
        "raw_candidate_count": len(raw),
        "fused_candidate_count": len(fused),
    }
