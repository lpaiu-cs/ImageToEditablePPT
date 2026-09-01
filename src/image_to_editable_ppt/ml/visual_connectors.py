"""Conservative, source-pixel-grounded connectors for recovered rectangles.

The general morphological extractor is useful when node geometry is uncertain,
but it can turn a curved return route or a panel border into a straight edge
between nearby nodes.  Once :mod:`visual_geometry` has recovered the real node
bounds, use a stricter contract: only emit an edge when one connected stroke in
the *open gap between two facing node sides* visibly spans that gap.

This deliberately omits curved and free-routing connectors.  A missing complex
route is editable by the user; a confidently drawn but topologically false line
is more expensive to notice and repair.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import cv2
import numpy as np

from image_to_editable_ppt.ml.annotation_schema import (
    AnnotationBBox,
    AnnotationConnectorCandidate,
    AnnotationConnectorEndpoint,
    AnnotationContainer,
    AnnotationNode,
    AnnotationPoint,
    AnnotationPort,
)
from image_to_editable_ppt.v3.core.enums import ConnectorKind, PortOwnerKind, PortSide


@dataclass(slots=True, frozen=True)
class _Bridge:
    first: int
    second: int
    axis: str
    coordinate: float
    direction: int
    coverage: float


def visual_connectors(
    image: np.ndarray,
    nodes: Sequence[AnnotationNode],
    *,
    containers: Sequence[AnnotationContainer] = (),
    image_id: str,
) -> tuple[tuple[AnnotationConnectorCandidate, ...], tuple[AnnotationPort, ...]]:
    """Emit only directly observed horizontal or vertical bridges.

    ``direction`` is inferred only when the arrowhead side is visibly wider
    than the shaft side.  Otherwise the supported topology is retained as an
    undirected line instead of guessing an arrow direction.
    """
    owner_groups: tuple[
        tuple[
            list[AnnotationNode | AnnotationContainer],
            PortOwnerKind,
            bool,
            list[AnnotationNode | AnnotationContainer],
        ],
        ...,
    ] = (
        (list(nodes), PortOwnerKind.NODE, False, list(nodes)),
        # Large panels can have another panel between their broad overlapping
        # bounds while a real connector runs through the remaining open lane.
        # For these owners, block only the observed connector coordinate after
        # pixel evidence has selected it.
        (
            list(containers),
            PortOwnerKind.CONTAINER,
            True,
            [*containers, *nodes],
        ),
    )
    if all(len(owners) < 2 for owners, _, _, _ in owner_groups):
        return (), ()

    rgb = np.asarray(image, dtype=np.uint8)
    connectors: list[AnnotationConnectorCandidate] = []
    ports: list[AnnotationPort] = []
    for owner_list, owner_kind, coordinate_blocking, coordinate_blockers in owner_groups:
        bridges = _find_bridges(
            rgb,
            owner_list,
            coordinate_blocking=coordinate_blocking,
            coordinate_blockers=coordinate_blockers,
        )
        for bridge in bridges:
            index = len(connectors)
            first = owner_list[bridge.first]
            second = owner_list[bridge.second]
            if bridge.axis == "horizontal":
                first_side, second_side = PortSide.RIGHT, PortSide.LEFT
                first_point = AnnotationPoint(first.bbox.x1, bridge.coordinate)
                second_point = AnnotationPoint(second.bbox.x0, bridge.coordinate)
            else:
                first_side, second_side = PortSide.BOTTOM, PortSide.TOP
                first_point = AnnotationPoint(bridge.coordinate, first.bbox.y1)
                second_point = AnnotationPoint(bridge.coordinate, second.bbox.y0)

            directed = bridge.direction != 0
            if bridge.direction < 0:
                start_owner, end_owner = second, first
                start_side, end_side = second_side, first_side
                start_point, end_point = second_point, first_point
            else:
                start_owner, end_owner = first, second
                start_side, end_side = first_side, second_side
                start_point, end_point = first_point, second_point

            connector_id = f"connector:{image_id}:visual:{index}"
            confidence = min(1.0, 0.78 + 0.22 * bridge.coverage)
            connectors.append(
                AnnotationConnectorCandidate(
                    id=connector_id,
                    kind=ConnectorKind.ARROW if directed else ConnectorKind.LINE,
                    bbox=AnnotationBBox(
                        x0=min(start_point.x, end_point.x) - 3.0,
                        y0=min(start_point.y, end_point.y) - 3.0,
                        x1=max(start_point.x, end_point.x) + 3.0,
                        y1=max(start_point.y, end_point.y) + 3.0,
                    ),
                    confidence=confidence,
                    source_evidence_id=f"evidence:{connector_id}",
                    path_points=(start_point, end_point),
                    start_endpoint=AnnotationConnectorEndpoint(
                        point=start_point,
                        owner_id=start_owner.id,
                        owner_kind=owner_kind,
                        side=start_side,
                    ),
                    end_endpoint=AnnotationConnectorEndpoint(
                        point=end_point,
                        owner_id=end_owner.id,
                        owner_kind=owner_kind,
                        side=end_side,
                    ),
                    arrowhead_end=directed,
                    source="visual_connector",
                    provenance=(
                        "visual_connector:source_pixels",
                        f"visual_connector:direct_{bridge.axis}_gap",
                        f"visual_connector:{owner_kind.value}_owners",
                    ),
                )
            )
            ports.append(
                _port(
                    start_owner.id,
                    owner_kind,
                    image_id,
                    index,
                    "start",
                    start_side,
                    start_point,
                    confidence,
                )
            )
            ports.append(
                _port(
                    end_owner.id,
                    owner_kind,
                    image_id,
                    index,
                    "end",
                    end_side,
                    end_point,
                    confidence,
                )
            )
    return tuple(connectors), tuple(ports)


def _find_bridges(
    rgb: np.ndarray,
    owners: list[AnnotationNode | AnnotationContainer],
    *,
    coordinate_blocking: bool = False,
    coordinate_blockers: list[AnnotationNode | AnnotationContainer] | None = None,
) -> list[_Bridge]:
    blockers = coordinate_blockers if coordinate_blockers is not None else owners
    bridges: list[_Bridge] = []
    for first_index, first in enumerate(owners):
        for second_index in range(first_index + 1, len(owners)):
            second = owners[second_index]
            horizontal = _ordered_horizontal(first_index, first, second_index, second)
            if horizontal is not None:
                left_index, left, right_index, right = horizontal
                y0 = max(left.bbox.y0, right.bbox.y0)
                y1 = min(left.bbox.y1, right.bbox.y1)
                min_height = min(left.bbox.y1 - left.bbox.y0, right.bbox.y1 - right.bbox.y0)
                blocked = not coordinate_blocking and _owner_blocks_gap(
                    owners,
                    excluded=(left_index, right_index),
                    x0=left.bbox.x1,
                    y0=y0,
                    x1=right.bbox.x0,
                    y1=y1,
                )
                if y1 - y0 >= 0.25 * min_height and not blocked:
                    evidence = _gap_bridge(
                        rgb,
                        axis="horizontal",
                        axis0=left.bbox.x1,
                        axis1=right.bbox.x0,
                        cross0=y0,
                        cross1=y1,
                        # A short thick PowerPoint arrow may devote roughly half
                        # the node height to its triangular head.
                        max_cross=0.55 * min_height,
                    )
                    if evidence is not None:
                        coordinate, direction, coverage = evidence
                        if coordinate_blocking and _owner_blocks_coordinate(
                            blockers,
                            excluded_owner_ids=(left.id, right.id),
                            axis="horizontal",
                            coordinate=coordinate,
                            axis0=left.bbox.x1,
                            axis1=right.bbox.x0,
                        ):
                            continue
                        bridges.append(
                            _Bridge(left_index, right_index, "horizontal", coordinate, direction, coverage)
                        )
                continue

            vertical = _ordered_vertical(first_index, first, second_index, second)
            if vertical is None:
                continue
            top_index, top, bottom_index, bottom = vertical
            x0 = max(top.bbox.x0, bottom.bbox.x0)
            x1 = min(top.bbox.x1, bottom.bbox.x1)
            min_width = min(top.bbox.x1 - top.bbox.x0, bottom.bbox.x1 - bottom.bbox.x0)
            blocked = not coordinate_blocking and _owner_blocks_gap(
                owners,
                excluded=(top_index, bottom_index),
                x0=x0,
                y0=top.bbox.y1,
                x1=x1,
                y1=bottom.bbox.y0,
            )
            if x1 - x0 < 0.25 * min_width or blocked:
                continue
            evidence = _gap_bridge(
                rgb,
                axis="vertical",
                axis0=top.bbox.y1,
                axis1=bottom.bbox.y0,
                cross0=x0,
                cross1=x1,
                max_cross=0.55 * min_width,
            )
            if evidence is not None:
                coordinate, direction, coverage = evidence
                if coordinate_blocking and _owner_blocks_coordinate(
                    blockers,
                    excluded_owner_ids=(top.id, bottom.id),
                    axis="vertical",
                    coordinate=coordinate,
                    axis0=top.bbox.y1,
                    axis1=bottom.bbox.y0,
                ):
                    continue
                bridges.append(_Bridge(top_index, bottom_index, "vertical", coordinate, direction, coverage))
    return bridges


def _ordered_horizontal(first_index, first, second_index, second):
    if first.bbox.x1 < second.bbox.x0:
        return first_index, first, second_index, second
    if second.bbox.x1 < first.bbox.x0:
        return second_index, second, first_index, first
    return None


def _ordered_vertical(first_index, first, second_index, second):
    if first.bbox.y1 < second.bbox.y0:
        return first_index, first, second_index, second
    if second.bbox.y1 < first.bbox.y0:
        return second_index, second, first_index, first
    return None


def _owner_blocks_gap(
    owners: list[AnnotationNode | AnnotationContainer],
    *,
    excluded: tuple[int, int],
    x0: float,
    y0: float,
    x1: float,
    y1: float,
) -> bool:
    if x1 <= x0 or y1 <= y0:
        return True
    for index, owner in enumerate(owners):
        if index in excluded:
            continue
        if min(x1, owner.bbox.x1) > max(x0, owner.bbox.x0) and min(y1, owner.bbox.y1) > max(
            y0, owner.bbox.y0
        ):
            return True
    return False


def _owner_blocks_coordinate(
    owners: list[AnnotationNode | AnnotationContainer],
    *,
    excluded_owner_ids: tuple[str, str],
    axis: str,
    coordinate: float,
    axis0: float,
    axis1: float,
) -> bool:
    """Whether another owner physically crosses the observed bridge lane."""
    tolerance = 2.0
    for owner in owners:
        if owner.id in excluded_owner_ids:
            continue
        bbox = owner.bbox
        if axis == "horizontal":
            if bbox.y0 - tolerance < coordinate < bbox.y1 + tolerance and min(axis1, bbox.x1) > max(
                axis0, bbox.x0
            ):
                return True
        elif bbox.x0 - tolerance < coordinate < bbox.x1 + tolerance and min(axis1, bbox.y1) > max(
            axis0, bbox.y0
        ):
            return True
    return False


def _gap_bridge(
    rgb: np.ndarray,
    *,
    axis: str,
    axis0: float,
    axis1: float,
    cross0: float,
    cross1: float,
    max_cross: float,
) -> tuple[float, int, float] | None:
    """Return (cross coordinate, direction, axial coverage) for one gap."""
    height, width = rgb.shape[:2]
    # Leave the node outline itself outside the evidence crop.  Otherwise the
    # one-pixel border joins the connector at a right angle and turns it into a
    # full-node-width component instead of an inter-node bridge.
    # The CLI scales small figures to the detector width, so a nominal 2 px
    # source outline can become 4-5 px.  Scale the inset with the raster rather
    # than assuming source-resolution stroke width.
    edge_inset = max(2, int(round(min(height, width) * 0.012)))
    if axis == "horizontal":
        x0, x1 = max(0, int(np.ceil(axis0)) + edge_inset), min(width, int(np.floor(axis1)) - edge_inset)
        y0, y1 = max(0, int(np.floor(cross0))), min(height, int(np.ceil(cross1)))
    else:
        x0, x1 = max(0, int(np.floor(cross0))), min(width, int(np.ceil(cross1)))
        y0, y1 = max(0, int(np.ceil(axis0)) + edge_inset), min(height, int(np.floor(axis1)) - edge_inset)
    crop = rgb[y0:y1, x0:x1]
    axial_length = crop.shape[1] if axis == "horizontal" else crop.shape[0]
    if crop.size == 0 or axial_length < 4:
        return None

    foreground = _foreground_from_dominant_background(crop)
    foreground = _remove_crossing_rules(foreground, axis=axis)
    # Thick panel/return rules can erase 5-11 rows of the crossing shaft after
    # scaling.  Close only along the candidate axis and cap the repair so it
    # cannot bridge arbitrary distant marks.
    close_length = max(3, min(17, int(round(min(crop.shape[:2]) * 0.16))))
    if close_length % 2 == 0:
        close_length += 1
    kernel = (
        np.ones((1, close_length), np.uint8)
        if axis == "horizontal"
        else np.ones((close_length, 1), np.uint8)
    )
    foreground = cv2.morphologyEx(foreground, cv2.MORPH_CLOSE, kernel)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(foreground, connectivity=8)
    touch_tolerance = max(3, int(round(axial_length * 0.36)))
    best = None
    for component in range(1, count):
        bx, by, bw, bh, area = (int(value) for value in stats[component])
        axial_start, axial_span = (bx, bw) if axis == "horizontal" else (by, bh)
        cross_span = bh if axis == "horizontal" else bw
        coverage = axial_span / axial_length
        if coverage < 0.64 or axial_start > touch_tolerance:
            continue
        if axial_start + axial_span < axial_length - touch_tolerance:
            continue
        if cross_span > max(4.0, max_cross):
            continue
        component_mask = labels == component
        density = area / max(1, bw * bh)
        score = coverage + min(0.2, density * 0.2)
        if best is None or score > best[0]:
            best = (score, component_mask, coverage, axial_start, axial_span)
    if best is None:
        return None

    _, component_mask, coverage, axial_start, axial_span = best
    ys, xs = np.where(component_mask)
    cross_values = ys if axis == "horizontal" else xs
    coordinate = float(np.median(cross_values) + (y0 if axis == "horizontal" else x0))
    direction = _arrow_direction(component_mask, axis=axis)
    # A visible arrow may intentionally stop before its target box.  Permit that
    # larger slack only when the observed arrowhead points into the slack; a
    # floating undirected dash is not enough evidence to invent an attachment.
    soft_tolerance = axial_length * 0.24
    start_slack = axial_start
    end_slack = axial_length - (axial_start + axial_span)
    if start_slack > soft_tolerance and direction != -1:
        return None
    if end_slack > soft_tolerance and direction != 1:
        return None
    return coordinate, direction, float(coverage)


def _foreground_from_dominant_background(crop: np.ndarray) -> np.ndarray:
    quantized = crop // 16
    packed = (
        quantized[..., 0].astype(np.int32) * 256
        + quantized[..., 1].astype(np.int32) * 16
        + quantized[..., 2].astype(np.int32)
    )
    values, counts = np.unique(packed, return_counts=True)
    dominant = int(values[int(np.argmax(counts))])
    red, remainder = divmod(dominant, 256)
    green, blue = divmod(remainder, 16)
    background = np.array([red, green, blue], dtype=np.float32) * 16.0 + 8.0
    distance = np.linalg.norm(crop.astype(np.float32) - background, axis=2)
    return (distance >= 24.0).astype(np.uint8)


def _remove_crossing_rules(foreground: np.ndarray, *, axis: str) -> np.ndarray:
    """Remove panel rules perpendicular to the candidate connector axis.

    A vertical arrow that crosses a horizontal panel border otherwise becomes
    one full-width connected component.  Only near-complete cross-crop rules
    are removed; the short arrowhead itself cannot satisfy this test.  The
    subsequent axis-aligned close reconnects the shaft across the erased rule.
    """
    cleaned = foreground.copy()
    height, width = cleaned.shape
    if axis == "vertical":
        rule_rows = cleaned.sum(axis=1) >= max(1, int(round(width * 0.55)))
        cleaned[rule_rows, :] = 0
    else:
        rule_columns = cleaned.sum(axis=0) >= max(1, int(round(height * 0.55)))
        cleaned[:, rule_columns] = 0
    return cleaned


def _arrow_direction(component: np.ndarray, *, axis: str) -> int:
    """+1 if the positive-axis end is visibly wider, -1 for the other end."""
    ys, xs = np.where(component)
    if len(xs) == 0:
        return 0
    start, end = (int(xs.min()), int(xs.max())) if axis == "horizontal" else (int(ys.min()), int(ys.max()))
    length = end - start + 1
    if length < 6:
        return 0
    profile: list[float] = []
    for position in range(start, end + 1):
        cross = np.where(component[:, position])[0] if axis == "horizontal" else np.where(component[position, :])[0]
        profile.append(float(cross.max() - cross.min() + 1) if len(cross) else 0.0)
    # A filled arrow has a sharp shaft->head widening followed by a gradual
    # taper to its tip.  The reverse direction has the mirror image: gradual
    # widening followed by a sharp head->shaft narrowing.  This discontinuity
    # remains reliable when the tip itself is clipped by the target node.
    differences = np.diff(np.asarray(profile, dtype=np.float32))
    if differences.size:
        positive_jump = float(differences.max())
        negative_jump = float(-differences.min())
        if positive_jump >= 2.0 and positive_jump >= negative_jump * 1.25:
            return 1
        if negative_jump >= 2.0 and negative_jump >= positive_jump * 1.25:
            return -1
    band = max(2, int(round(length * 0.34)))
    trim = max(1, int(round(length * 0.05)))
    negative = np.asarray(profile[trim : min(length, trim + band)], dtype=np.float32)
    positive = np.asarray(profile[max(0, length - trim - band) : length - trim], dtype=np.float32)
    if negative.size == 0 or positive.size == 0:
        return 0
    negative_width = float(np.percentile(negative, 85))
    positive_width = float(np.percentile(positive, 85))
    if positive_width >= negative_width * 1.35 and positive_width - negative_width >= 2.0:
        return 1
    if negative_width >= positive_width * 1.35 and negative_width - positive_width >= 2.0:
        return -1
    # Filled arrowheads taper to a narrow tip.  On short gaps the wide base of
    # the head can sit in the middle band, so compare the actual end profiles as
    # a second, independent cue.
    tip_band = max(2, int(round(length * 0.16)))
    negative_tip = float(np.median(np.asarray(profile[:tip_band], dtype=np.float32)))
    positive_tip = float(np.median(np.asarray(profile[-tip_band:], dtype=np.float32)))
    if positive_tip <= negative_tip * 0.72 and negative_tip - positive_tip >= 2.0:
        return 1
    if negative_tip <= positive_tip * 0.72 and positive_tip - negative_tip >= 2.0:
        return -1
    return 0


def _port(
    owner_id: str,
    owner_kind: PortOwnerKind,
    image_id: str,
    index: int,
    role: str,
    side: PortSide,
    point: AnnotationPoint,
    confidence: float,
) -> AnnotationPort:
    return AnnotationPort(
        id=f"port:{image_id}:visual:{index}:{role}",
        owner_id=owner_id,
        owner_kind=owner_kind,
        side=side,
        point=point,
        confidence=confidence,
        source="visual_connector",
        provenance=("visual_connector:source_pixels",),
    )
