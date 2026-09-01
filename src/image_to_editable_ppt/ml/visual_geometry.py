"""Visually grounded rectangle recovery for real diagram figures.

The synthetic detector is useful as a diagram-level prior, but its bounding
boxes can be badly displaced on real figures.  This module only accepts
geometry that the source pixels directly support: four observed dark sides, or
a sufficiently large uniform fill that remains after thin connector strokes
are removed.  When a coherent set is present it replaces ML-only boxes rather
than adding more uncertain objects.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import cv2
import numpy as np

from image_to_editable_ppt.ml.annotation_schema import AnnotationBBox, AnnotationContainer, AnnotationNode
from image_to_editable_ppt.v3.core.enums import ContainerKind, NodeKind


@dataclass(slots=True, frozen=True)
class GeometryCandidate:
    bbox: tuple[int, int, int, int]
    source: str
    confidence: float
    header_bottom: int | None = None

    @property
    def area(self) -> int:
        x0, y0, x1, y1 = self.bbox
        return max(0, x1 - x0) * max(0, y1 - y0)

    @property
    def center(self) -> tuple[float, float]:
        x0, y0, x1, y1 = self.bbox
        return ((x0 + x1) / 2.0, (y0 + y1) / 2.0)


@dataclass(slots=True, frozen=True)
class VisualGeometry:
    nodes: tuple[GeometryCandidate, ...]
    containers: tuple[GeometryCandidate, ...]


def detect_visual_geometry(rgb: np.ndarray) -> VisualGeometry:
    """Return large, directly observed rectangular structure.

    The global 0.6% area floor is intentional.  Smaller closed glyphs frequently
    are document/icons rather than editable diagram nodes.  A narrower exception
    exists inside an already confirmed titled panel: three or more repeated,
    wide, source-supported boxes may be recovered as a coherent local pattern.
    An isolated small outline is still omitted.
    """
    array = np.asarray(rgb, dtype=np.uint8)
    fills = _filled_candidates(array)
    large_outlines = _outline_candidates(array)
    outlines = _dedupe(
        [*large_outlines, *_merge_titled_panels(large_outlines, image_shape=array.shape[:2])]
    )
    panel_nodes = _panel_node_candidates(
        array,
        [candidate for candidate in outlines if candidate.source == "titled_panel"],
    )
    ellipses = _ellipse_candidates(array)
    node_candidates = _dedupe(
        [
            *fills,
            *(
                outline
                for outline in outlines
                if not any(_intersection_over_smaller(outline, fill) > 0.70 for fill in fills)
            ),
            *panel_nodes,
            *ellipses,
        ]
    )
    detected_containers = tuple(
        outline
        for outline in outlines
        if outline.source == "titled_panel"
        or _has_nested_structure(outline, node_candidates)
        or _has_header_divider(array, outline)
    )
    containers = tuple(
        candidate
        for candidate in detected_containers
        if candidate.source == "titled_panel" or not _is_header_partition(candidate, detected_containers)
    )
    nodes = tuple(
        candidate
        for candidate in node_candidates
        if candidate not in containers and not _is_header_partition(candidate, containers)
    )
    return VisualGeometry(nodes=nodes, containers=containers)


def reconcile_with_visual_geometry(
    rgb: np.ndarray,
    nodes: Iterable[AnnotationNode],
    containers: Iterable[AnnotationContainer],
    *,
    image_id: str,
) -> tuple[tuple[AnnotationNode, ...], tuple[AnnotationContainer, ...], bool]:
    """Replace approximate ML boxes with pixel-confirmed geometry when coherent.

    One isolated rectangle is not enough to redefine a whole scene.  Two or
    more supported structural objects (nodes or titled/grouping panels) form
    the minimum coherent set; otherwise the original detector predictions are
    preserved.
    """
    original_nodes = tuple(nodes)
    original_containers = tuple(containers)
    geometry = detect_visual_geometry(rgb)
    if len(geometry.nodes) + len(geometry.containers) < 2:
        return original_nodes, original_containers, False

    recovered_nodes: list[AnnotationNode] = []
    for index, candidate in enumerate(geometry.nodes):
        matched = _best_node_match(candidate, original_nodes)
        if candidate.source == "closed_ellipse":
            kind = NodeKind.ELLIPSE
        else:
            default_kind = NodeKind.ROUNDED_BOX if candidate.source == "uniform_fill" else NodeKind.BOX
            kind = matched.kind if matched is not None and matched.kind is not NodeKind.LABEL_ANCHOR else default_kind
        confidence = max(candidate.confidence, matched.confidence if matched is not None else 0.0)
        recovered_nodes.append(
            AnnotationNode(
                id=f"node:{image_id}:visual:{index}",
                kind=kind,
                bbox=_annotation_bbox(candidate),
                confidence=min(1.0, confidence),
                source=f"visual_geometry:{candidate.source}",
                provenance=("visual_geometry:source_pixels", f"visual_geometry:{candidate.source}"),
            )
        )

    recovered_containers: list[AnnotationContainer] = []
    for index, candidate in enumerate(geometry.containers):
        member_ids = tuple(
            node.id
            for node in recovered_nodes
            if _contains_point(candidate, _bbox_center(node.bbox))
        )
        recovered_containers.append(
            AnnotationContainer(
                id=f"container:{image_id}:visual:{index}",
                kind=ContainerKind.FLOW_CLUSTER,
                bbox=_annotation_bbox(candidate),
                confidence=min(1.0, candidate.confidence),
                member_node_ids=member_ids,
                source=f"visual_geometry:{candidate.source}",
                provenance=(
                    "visual_geometry:source_pixels",
                    f"visual_geometry:{candidate.source}",
                    *(
                        (f"visual_geometry:header_bottom={candidate.header_bottom}",)
                        if candidate.header_bottom is not None
                        else ()
                    ),
                ),
            )
        )
    return tuple(recovered_nodes), tuple(recovered_containers), True


def _outline_candidates(
    rgb: np.ndarray,
    *,
    minimum_area_fraction: float = 0.006,
    minimum_width_fraction: float = 0.035,
    minimum_height_fraction: float = 0.035,
    include_shallow_headers: bool = True,
) -> list[GeometryCandidate]:
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    height, width = gray.shape
    dark = (gray < 170).astype(np.uint8) * 255
    contours, _ = cv2.findContours(dark, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    minimum_area = max(100, int(width * height * minimum_area_fraction))
    band = max(2, round(min(width, height) * 0.004))
    found: list[GeometryCandidate] = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        standard_size = w >= max(18, width * minimum_width_fraction) and h >= max(
            14, height * minimum_height_fraction
        )
        shallow_header_size = (
            include_shallow_headers and w >= width * 0.18 and h >= max(12, height * 0.018)
        )
        if not (standard_size or shallow_header_size) or w * h < minimum_area:
            continue
        if w > width * 0.99 and h > height * 0.99:
            continue
        x1, y1 = x + w, y + h
        top_trace = dark[y : min(y1, y + band), x:x1].max(axis=0) > 0
        bottom_trace = dark[max(y, y1 - band) : y1, x:x1].max(axis=0) > 0
        left_trace = dark[y:y1, x : min(x1, x + band)].max(axis=1) > 0
        right_trace = dark[y:y1, max(x, x1 - band) : x1].max(axis=1) > 0
        top, bottom = float(top_trace.mean()), float(bottom_trace.mean())
        left, right = float(left_trace.mean()), float(right_trace.mean())
        support = float(min(top, bottom, left, right))
        continuous_support = min(
            _longest_true_fraction(top_trace),
            _longest_true_fraction(bottom_trace),
            _longest_true_fraction(left_trace),
            _longest_true_fraction(right_trace),
        )
        if support < 0.58 or continuous_support < 0.52:
            continue
        found.append(GeometryCandidate((x, y, x1, y1), "closed_outline", support))
    return _dedupe(found)


def _panel_node_candidates(
    rgb: np.ndarray,
    titled_panels: list[GeometryCandidate],
) -> list[GeometryCandidate]:
    """Recover a repeated row/graph of small wide boxes inside a known panel.

    This is deliberately contextual.  At this scale a single rectangle may be
    an icon, glyph, or legend sample.  Requiring at least three similarly tall
    wide boxes below the observed title divider provides direct geometric
    evidence for a local editable node vocabulary without lowering the global
    false-positive boundary.
    """
    if not titled_panels:
        return []
    small_outlines = _dedupe_panel_strokes(
        _outline_candidates(
            rgb,
            minimum_area_fraction=0.0025,
            minimum_width_fraction=0.07,
            minimum_height_fraction=0.025,
            include_shallow_headers=False,
        )
    )
    recovered: list[GeometryCandidate] = []
    for panel in titled_panels:
        px0, py0, px1, py1 = panel.bbox
        body_top = panel.header_bottom if panel.header_bottom is not None else py0
        body_height = max(1, py1 - body_top)
        body_margin = max(4, int(round(body_height * 0.05)))
        candidates: list[GeometryCandidate] = []
        for candidate in small_outlines:
            x0, y0, x1, y1 = candidate.bbox
            width, height = x1 - x0, y1 - y0
            aspect = width / max(1, height)
            if not 1.5 <= aspect <= 6.5:
                continue
            if candidate.area >= panel.area * 0.12 or height > body_height * 0.30:
                continue
            if x0 <= px0 or x1 >= px1 or y0 < body_top + body_margin or y1 >= py1:
                continue
            candidates.append(candidate)
        if len(candidates) < 3:
            continue
        median_height = float(np.median([candidate.bbox[3] - candidate.bbox[1] for candidate in candidates]))
        coherent = [
            candidate
            for candidate in candidates
            if 0.68 * median_height <= candidate.bbox[3] - candidate.bbox[1] <= 1.48 * median_height
        ]
        if len(coherent) < 3:
            continue
        recovered.extend(
            GeometryCandidate(
                candidate.bbox,
                "panel_closed_outline",
                candidate.confidence,
            )
            for candidate in coherent
        )
    return _dedupe(recovered)


def _dedupe_panel_strokes(candidates: list[GeometryCandidate]) -> list[GeometryCandidate]:
    """Collapse the inner and outer contour of one small rectangular stroke.

    The global de-duplicator intentionally preserves nested structures.  Here
    all candidates are already scoped to the repeated-small-box exception, so
    near-concentric outlines are the two sides of one border rather than a
    parent/child diagram relationship.
    """
    kept: list[GeometryCandidate] = []
    for candidate in sorted(candidates, key=lambda item: (item.confidence, item.area), reverse=True):
        if any(
            _intersection_over_smaller(candidate, other) >= 0.88
            and min(candidate.area, other.area) / max(1, max(candidate.area, other.area)) >= 0.60
            and _near_same_bounds(candidate, other, tolerance=0.09)
            for other in kept
        ):
            continue
        kept.append(candidate)
    return sorted(kept, key=lambda item: (item.bbox[1], item.bbox[0]))


def _merge_titled_panels(
    outlines: list[GeometryCandidate],
    *,
    image_shape: tuple[int, int],
) -> list[GeometryCandidate]:
    """Join a shallow header cell and its immediately adjacent body cell."""
    height, width = image_shape
    max_gap = max(4, int(round(height * 0.012)))
    panels: list[GeometryCandidate] = []
    for first_index, first in enumerate(outlines):
        for second in outlines[first_index + 1 :]:
            top, bottom = (first, second) if first.bbox[1] <= second.bbox[1] else (second, first)
            tx0, ty0, tx1, ty1 = top.bbox
            bx0, by0, bx1, by1 = bottom.bbox
            top_width, bottom_width = tx1 - tx0, bx1 - bx0
            union_width = max(tx1, bx1) - min(tx0, bx0)
            union_height = max(ty1, by1) - min(ty0, by0)
            gap = by0 - ty1
            if union_width < width * 0.18 or union_height <= 0 or not 0 <= gap <= max_gap:
                continue
            if min(top_width, bottom_width) / max(1, max(top_width, bottom_width)) < 0.95:
                continue
            if abs(tx0 - bx0) > 0.025 * union_width or abs(tx1 - bx1) > 0.025 * union_width:
                continue
            if (ty1 - ty0) > 0.40 * union_height or (by1 - by0) <= (ty1 - ty0):
                continue
            panels.append(
                GeometryCandidate(
                    (min(tx0, bx0), min(ty0, by0), max(tx1, bx1), max(ty1, by1)),
                    "titled_panel",
                    min(top.confidence, bottom.confidence),
                    header_bottom=int(round((ty1 + by0) / 2.0)),
                )
            )
    return _dedupe(panels)


def _longest_true_fraction(trace: np.ndarray) -> float:
    longest = current = 0
    for value in trace.tolist():
        if value:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest / max(1, len(trace))


def _filled_candidates(rgb: np.ndarray) -> list[GeometryCandidate]:
    height, width = rgb.shape[:2]
    image_area = width * height
    quantized = (rgb // 16).astype(np.int16)
    packed = quantized[..., 0] * 256 + quantized[..., 1] * 16 + quantized[..., 2]
    values, counts = np.unique(packed, return_counts=True)
    kernel_size = max(3, min(15, round(min(width, height) * 0.014)))
    if kernel_size % 2 == 0:
        kernel_size += 1
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
    found: list[GeometryCandidate] = []
    for value, count in zip(values, counts):
        if count < image_area * 0.003:
            continue
        red, remainder = divmod(int(value), 256)
        green, blue = divmod(remainder, 16)
        color_center = np.array([red, green, blue]) * 16 + 8
        if color_center.min() >= 248 or color_center.max() <= 40:
            continue
        mask = (packed == value).astype(np.uint8) * 255
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        component_count, _, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
        for x, y, w, h, component_area in stats[1:component_count]:
            bbox_area = int(w * h)
            if component_area < image_area * 0.004 or bbox_area <= 0:
                continue
            if w < width * 0.04 or h < height * 0.04:
                continue
            if w > width * 0.97 and h > height * 0.97:
                continue
            fill_ratio = float(component_area / bbox_area)
            if fill_ratio < 0.42:
                continue
            found.append(
                GeometryCandidate(
                    (int(x), int(y), int(x + w), int(y + h)),
                    "uniform_fill",
                    fill_ratio,
                )
            )
    return _dedupe(found)


def _ellipse_candidates(rgb: np.ndarray) -> list[GeometryCandidate]:
    """Large closed ellipses whose contour agrees with an ellipse fit.

    The area floor shared with rectangles keeps small circular icons out.  A
    fit residual check rejects cylinders, braces, D-shapes, and curved arrows;
    those are not silently approximated as editable ellipses.
    """
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    height, width = gray.shape
    dark = (gray < 170).astype(np.uint8) * 255
    contours, _ = cv2.findContours(dark, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    minimum_area = max(100, int(width * height * 0.006))
    found: list[GeometryCandidate] = []
    for contour in contours:
        if len(contour) < 20:
            continue
        x, y, w, h = cv2.boundingRect(contour)
        bbox_area = w * h
        if bbox_area < minimum_area or w < width * 0.035 or h < height * 0.035:
            continue
        if w > width * 0.97 and h > height * 0.97:
            continue
        contour_area = float(cv2.contourArea(contour))
        extent = contour_area / max(1.0, float(bbox_area))
        if not 0.56 <= extent <= 0.86:
            continue
        (cx, cy), (axis_a, axis_b), angle = cv2.fitEllipse(contour)
        if axis_a <= 0 or axis_b <= 0:
            continue
        if abs(cx - (x + w / 2.0)) > 0.08 * w or abs(cy - (y + h / 2.0)) > 0.08 * h:
            continue
        fitted_area = np.pi * axis_a * axis_b / 4.0
        if not 0.82 <= contour_area / max(1.0, fitted_area) <= 1.18:
            continue
        points = contour[:, 0, :].astype(np.float64)
        radians = np.deg2rad(angle)
        cos_angle, sin_angle = np.cos(radians), np.sin(radians)
        dx, dy = points[:, 0] - cx, points[:, 1] - cy
        rotated_x = cos_angle * dx + sin_angle * dy
        rotated_y = -sin_angle * dx + cos_angle * dy
        radial = np.sqrt((rotated_x / (axis_a / 2.0)) ** 2 + (rotated_y / (axis_b / 2.0)) ** 2)
        residual = np.abs(radial - 1.0)
        if float(np.median(residual)) > 0.08 or float(np.percentile(residual, 90)) > 0.20:
            continue
        confidence = max(0.72, 1.0 - float(np.percentile(residual, 90)))
        found.append(GeometryCandidate((x, y, x + w, y + h), "closed_ellipse", confidence))
    return _dedupe(found)


def _has_nested_structure(container: GeometryCandidate, candidates: list[GeometryCandidate]) -> bool:
    for candidate in candidates:
        if candidate == container or candidate.area >= container.area * 0.82:
            continue
        if _contains_point(container, candidate.center):
            return True
    return False


def _has_header_divider(rgb: np.ndarray, candidate: GeometryCandidate) -> bool:
    """A long line in the upper third is direct evidence of a titled panel."""
    x0, y0, x1, y1 = candidate.bbox
    width, height = x1 - x0, y1 - y0
    if width < 20 or height < 20:
        return False
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    inset_x = max(2, int(round(width * 0.03)))
    scan_y0 = y0 + max(3, int(round(height * 0.06)))
    scan_y1 = y0 + max(4, int(round(height * 0.35)))
    crop = gray[scan_y0:min(y1, scan_y1), x0 + inset_x : x1 - inset_x]
    if crop.size == 0:
        return False
    dark = crop < 170
    return bool(np.any(dark.mean(axis=1) >= 0.68))


def _is_header_partition(candidate: GeometryCandidate, containers: tuple[GeometryCandidate, ...]) -> bool:
    """Drop interior contour cells created by a panel's title divider."""
    for container in containers:
        if container.source != "titled_panel":
            continue
        if candidate.area >= container.area or not _contains_point(container, candidate.center):
            continue
        cx0, _, cx1, _ = container.bbox
        x0, _, x1, _ = candidate.bbox
        container_width = max(1, cx1 - cx0)
        if (x1 - x0) / container_width < 0.85:
            continue
        if abs(x0 - cx0) <= 0.05 * container_width and abs(x1 - cx1) <= 0.05 * container_width:
            return True
    return False


def _best_node_match(candidate: GeometryCandidate, nodes: tuple[AnnotationNode, ...]) -> AnnotationNode | None:
    scored = [
        (_candidate_annotation_overlap(candidate, node.bbox), node)
        for node in nodes
    ]
    if not scored:
        return None
    overlap, node = max(scored, key=lambda item: item[0])
    return node if overlap >= 0.45 else None


def _candidate_annotation_overlap(candidate: GeometryCandidate, bbox: AnnotationBBox) -> float:
    other = GeometryCandidate(
        (int(round(bbox.x0)), int(round(bbox.y0)), int(round(bbox.x1)), int(round(bbox.y1))),
        "ml",
        0.0,
    )
    return _intersection_over_smaller(candidate, other)


def _annotation_bbox(candidate: GeometryCandidate) -> AnnotationBBox:
    x0, y0, x1, y1 = candidate.bbox
    return AnnotationBBox(float(x0), float(y0), float(x1), float(y1))


def _bbox_center(bbox: AnnotationBBox) -> tuple[float, float]:
    return ((bbox.x0 + bbox.x1) / 2.0, (bbox.y0 + bbox.y1) / 2.0)


def _contains_point(candidate: GeometryCandidate, point: tuple[float, float]) -> bool:
    x0, y0, x1, y1 = candidate.bbox
    return x0 < point[0] < x1 and y0 < point[1] < y1


def _intersection_over_smaller(first: GeometryCandidate, second: GeometryCandidate) -> float:
    ax0, ay0, ax1, ay1 = first.bbox
    bx0, by0, bx1, by1 = second.bbox
    intersection = max(0, min(ax1, bx1) - max(ax0, bx0)) * max(0, min(ay1, by1) - max(ay0, by0))
    smaller = min(first.area, second.area)
    return intersection / smaller if smaller > 0 else 0.0


def _dedupe(candidates: list[GeometryCandidate]) -> list[GeometryCandidate]:
    kept: list[GeometryCandidate] = []
    for candidate in sorted(candidates, key=lambda item: (item.confidence, item.area), reverse=True):
        if any(
            _intersection_over_smaller(candidate, other) >= 0.88
            and min(candidate.area, other.area) / max(1, max(candidate.area, other.area)) >= 0.85
            and (
                (candidate.source != "titled_panel" and other.source != "titled_panel")
                or _same_bounds(candidate, other)
            )
            for other in kept
        ):
            continue
        kept.append(candidate)
    return sorted(kept, key=lambda item: (item.bbox[1], item.bbox[0]))


def _same_bounds(first: GeometryCandidate, second: GeometryCandidate) -> bool:
    return _near_same_bounds(first, second, tolerance=0.03)


def _near_same_bounds(
    first: GeometryCandidate,
    second: GeometryCandidate,
    *,
    tolerance: float,
) -> bool:
    ax0, ay0, ax1, ay1 = first.bbox
    bx0, by0, bx1, by1 = second.bbox
    width = max(1, ax1 - ax0, bx1 - bx0)
    height = max(1, ay1 - ay0, by1 - by0)
    return (
        abs(ax0 - bx0) <= tolerance * width
        and abs(ax1 - bx1) <= tolerance * width
        and abs(ay0 - by0) <= tolerance * height
        and abs(ay1 - by1) <= tolerance * height
    )
