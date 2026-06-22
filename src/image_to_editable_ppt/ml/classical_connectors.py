"""Classical connector-line detection (no learned thin-line segmenter).

Diagnosis (2026-06-22): the learned 2-channel connector segmenter is effectively
blind to real paper arrows — soft line-probability is ~0 across the whole figure
(line-mask coverage ~0.28%, barely above zero), because thin (1-2px) high-contrast
line segmentation is the wrong job for a shallow pooled U-Net and the synthetic->
real gap persists. Classical line detectors (OpenCV LSD / Hough) instead capture
*every* stroke including all connectors, with no domain gap.

So recover connector pixels classically and filter to actual connectors using node
geometry: drop segments that run along a node/container box border (those are box
outlines) or sit inside a node box (text strokes); keep the inter-node strokes.
The rasterized result is a drop-in replacement for the segmenter's line mask, so
the relation/topology model consumes it unchanged.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np

Segment = tuple[float, float, float, float]  # x1, y1, x2, y2


@dataclass(slots=True, frozen=True)
class _Box:
    x0: float
    y0: float
    x1: float
    y1: float


def _as_box(obj: object) -> _Box:
    b = getattr(obj, "bbox", obj)
    return _Box(float(b.x0), float(b.y0), float(b.x1), float(b.y1))  # type: ignore[attr-defined]


def detect_segments(gray: np.ndarray) -> list[Segment]:
    """All straight line segments in a grayscale figure (LSD, Hough fallback)."""
    import cv2

    try:
        lsd = cv2.createLineSegmentDetector()
        result = lsd.detect(gray)[0]
        if result is not None and len(result):
            return [tuple(float(v) for v in seg[0]) for seg in result]
    except Exception:
        pass
    edges = cv2.Canny(gray, 50, 150)
    lines = cv2.HoughLinesP(edges, 1, math.pi / 180, threshold=40, minLineLength=20, maxLineGap=6)
    return [] if lines is None else [tuple(float(v) for v in line[0]) for line in lines]


def _midpoint_inside(seg: Segment, box: _Box, *, pad: float = 2.0) -> bool:
    mx, my = (seg[0] + seg[2]) / 2.0, (seg[1] + seg[3]) / 2.0
    return box.x0 - pad <= mx <= box.x1 + pad and box.y0 - pad <= my <= box.y1 + pad


def _runs_along_box_edge(seg: Segment, box: _Box, *, margin: float) -> bool:
    """True if the segment hugs one of the box's four edges (i.e. a box outline)."""
    x1, y1, x2, y2 = seg
    horizontal = abs(y2 - y1) <= margin
    vertical = abs(x2 - x1) <= margin
    xlo, xhi = min(x1, x2), max(x1, x2)
    ylo, yhi = min(y1, y2), max(y1, y2)
    if horizontal:
        for edge_y in (box.y0, box.y1):
            if abs(y1 - edge_y) <= margin and abs(y2 - edge_y) <= margin:
                if xlo >= box.x0 - margin and xhi <= box.x1 + margin:
                    return True
    if vertical:
        for edge_x in (box.x0, box.x1):
            if abs(x1 - edge_x) <= margin and abs(x2 - edge_x) <= margin:
                if ylo >= box.y0 - margin and yhi <= box.y1 + margin:
                    return True
    return False


def filter_connector_segments(
    segments: Sequence[Segment],
    node_boxes: Sequence[_Box],
    container_boxes: Sequence[_Box] = (),
    *,
    margin: float = 5.0,
    min_length: float = 12.0,
) -> list[Segment]:
    """Keep only inter-node connector strokes: drop box outlines (segments along a
    node/container edge) and text strokes (segments whose midpoint is inside a node)."""
    boxes_for_edges = list(node_boxes) + list(container_boxes)
    kept: list[Segment] = []
    for seg in segments:
        if math.hypot(seg[2] - seg[0], seg[3] - seg[1]) < min_length:
            continue
        if any(_midpoint_inside(seg, box) for box in node_boxes):
            continue
        if any(_runs_along_box_edge(seg, box, margin=margin) for box in boxes_for_edges):
            continue
        kept.append(seg)
    return kept


def rasterize_segments(segments: Sequence[Segment], *, width: int, height: int, thickness: int = 2) -> np.ndarray:
    import cv2

    mask = np.zeros((height, width), dtype=np.uint8)
    for x1, y1, x2, y2 in segments:
        cv2.line(mask, (int(round(x1)), int(round(y1))), (int(round(x2)), int(round(y2))), 1, thickness)
    return mask


@dataclass(slots=True, frozen=True)
class ClassicalEdge:
    source: int  # node index
    target: int
    polyline: tuple[tuple[float, float], ...]


def _node_ink_mask(shape: tuple[int, int], nodes: Sequence[_Box], containers: Sequence[_Box], *, pad: int, border: int):
    import cv2

    mask = np.zeros(shape, dtype=np.uint8)
    for b in nodes:  # whole node box (interior text + border)
        cv2.rectangle(mask, (int(b.x0) - pad, int(b.y0) - pad), (int(b.x1) + pad, int(b.y1) + pad), 1, -1)
    for b in containers:  # only the panel border band — connectors live inside panels
        cv2.rectangle(mask, (int(b.x0) - pad, int(b.y0) - pad), (int(b.x1) + pad, int(b.y1) + pad), 1, border)
    return mask


def extract_connectors_morphological(
    image: np.ndarray,
    node_boxes: Sequence[object],
    container_boxes: Sequence[object] = (),
    *,
    ink_threshold: int = 140,
    min_area: int = 18,
    attach_frac: float = 0.05,
) -> list[ClassicalEdge]:
    """Recover connectors as connected ink components (the robust extractor).

    A connector is a stroke that lives *between* nodes. So binarise the ink, remove
    node boxes (interior text + outline) and container border bands, and take the
    connected components of what remains: each component is one whole connector —
    elbow and curved routes stay intact, unlike straight LSD segments. A component
    is attached to the (up to two) nearest node boxes; touching two distinct nodes
    makes an edge. Components are kept only if elongated (line-like), dropping stray
    text blobs floating outside nodes.
    """
    import cv2

    rgb = np.asarray(image)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY) if rgb.ndim == 3 else rgb
    h, w = gray.shape[:2]
    nodes = [_as_box(b) for b in node_boxes]
    containers = [_as_box(b) for b in container_boxes]
    if not nodes:
        return []
    ink = (gray < ink_threshold).astype(np.uint8)
    connector_ink = ink & (1 - _node_ink_mask((h, w), nodes, containers, pad=4, border=6))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(connector_ink, connectivity=8)
    attach_dist = attach_frac * math.hypot(w, h)
    edges: dict[tuple[int, int], ClassicalEdge] = {}
    for ci in range(1, count):
        x, y, bw, bh, area = stats[ci]
        if area < min_area:
            continue
        if max(bw, bh) / max(1, min(bw, bh)) < 2.5 and area / max(1, bw * bh) > 0.5:
            continue  # blobby (text), not a line-like connector
        ys, xs = np.where(labels[y : y + bh, x : x + bw] == ci)
        ys = ys.astype(np.float64) + y
        xs = xs.astype(np.float64) + x
        # The connector's two *ends* are the extreme pixels along the component's
        # principal axis (PCA). Attach each end to the node nearest *that end* — not
        # to any node near the middle — so an elbow routed past a third node does
        # not spuriously link to it.
        pts = np.column_stack([xs, ys])
        centred = pts - pts.mean(axis=0)
        axis = np.linalg.eigh(centred.T @ centred)[1][:, -1]
        proj = centred @ axis
        end_a, end_b = pts[int(proj.argmin())], pts[int(proj.argmax())]
        ni = _nearest_node_to_point(end_a, nodes, max_dist=attach_dist)
        nj = _nearest_node_to_point(end_b, nodes, max_dist=attach_dist)
        if ni is None or nj is None or ni == nj:
            continue
        key = (min(ni, nj), max(ni, nj))
        if key not in edges:
            edges[key] = ClassicalEdge(
                source=ni, target=nj,
                polyline=((float(end_a[0]), float(end_a[1])), (float(end_b[0]), float(end_b[1]))),
            )
    return list(edges.values())


def _nearest_node_to_point(point: np.ndarray, nodes: Sequence[_Box], *, max_dist: float) -> int | None:
    best, best_d = None, max_dist
    for idx, b in enumerate(nodes):
        dx = max(b.x0 - point[0], 0.0, point[0] - b.x1)
        dy = max(b.y0 - point[1], 0.0, point[1] - b.y1)
        d = math.hypot(dx, dy)
        if d <= best_d:
            best, best_d = idx, d
    return best


def classical_connector_masks(
    image: np.ndarray,
    node_boxes: Sequence[object],
    container_boxes: Sequence[object] = (),
    *,
    margin: float = 5.0,
) -> tuple[np.ndarray, np.ndarray]:
    """(line_mask, arrow_mask): classical replacement for the learned segmenter's
    masks. arrow_mask is currently empty (direction recovery is a follow-up); the
    line mask is the connectivity signal the relation/topology model needs."""
    import cv2

    rgb = np.asarray(image)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY) if rgb.ndim == 3 else rgb
    height, width = gray.shape[:2]
    nodes = [_as_box(b) for b in node_boxes]
    containers = [_as_box(b) for b in container_boxes]
    kept = filter_connector_segments(detect_segments(gray), nodes, containers, margin=margin)
    line_mask = rasterize_segments(kept, width=width, height=height)
    arrow_mask = np.zeros((height, width), dtype=np.uint8)
    return line_mask, arrow_mask
