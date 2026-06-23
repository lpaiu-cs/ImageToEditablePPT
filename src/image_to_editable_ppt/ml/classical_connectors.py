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
    # Geometry the learned judge consumes as features (never hand-thresholded here):
    gap: float = 0.0  # px from the looser endpoint to its node border (attachment slack)
    ortho: float = 1.0  # fraction of route length on axis-aligned segments (0..1)
    excursion: float = 0.0  # max route stray outside the two nodes' union bbox, / image diag
    edge_off: float = 0.0  # looser end's offset from its node-edge midpoint (0 central .. 0.5 corner)


def detect_box_outlines(gray: np.ndarray, *, ink_threshold: int = 160, min_frac: float = 0.001, max_frac: float = 0.4) -> list[_Box]:
    """Detect drawn rectangular box outlines (closed 4-corner convex contours).

    The learned detector's node bboxes are often a few px off, so a box's real
    outline leaks into the connector ink and is mistaken for a connector. Classical
    rectangle detection finds the *actual* outlines precisely (no domain gap), so
    they can be masked out exactly regardless of detector precision.
    """
    import cv2

    binary = ((gray < ink_threshold).astype(np.uint8)) * 255
    contours, _ = cv2.findContours(binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    img_area = float(gray.size)
    rects: list[_Box] = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < min_frac * img_area or area > max_frac * img_area:
            continue
        approx = cv2.approxPolyDP(contour, 0.04 * cv2.arcLength(contour, True), True)
        if len(approx) != 4 or not cv2.isContourConvex(approx):
            continue
        x, y, bw, bh = cv2.boundingRect(approx)
        if area / max(1, bw * bh) > 0.8 and 0.15 < bw / max(1, bh) < 8:
            rects.append(_Box(float(x), float(y), float(x + bw), float(y + bh)))
    return rects


def _box_area(b: _Box) -> float:
    return max(1.0, (b.x1 - b.x0) * (b.y1 - b.y0))


def _intersection_area(a: _Box, b: _Box) -> float:
    ix = max(0.0, min(a.x1, b.x1) - max(a.x0, b.x0))
    iy = max(0.0, min(a.y1, b.y1) - max(a.y0, b.y0))
    return ix * iy


def _leaf_outlines(outlines: Sequence[_Box], *, contain_frac: float = 0.8) -> list[_Box]:
    """Drawn rectangles that enclose no smaller rectangle — i.e. true node boxes.

    A panel is, by its drawn structure, a rectangle around *other* boxes; a node box
    contains only text. So a panel is identified by the honest fact that it encloses
    another rectangle, not by any size threshold. Leaves are the boxes a node may snap
    to; panels are deliberately excluded (snapping a node to a panel would fill the
    panel and erase the connectors inside it).
    """
    leaves: list[_Box] = []
    for i, r in enumerate(outlines):
        r_area = _box_area(r)
        encloses_other = any(
            j != i and _box_area(o) < r_area and _intersection_area(o, r) >= contain_frac * _box_area(o)
            for j, o in enumerate(outlines)
        )
        if not encloses_other:
            leaves.append(r)
    return leaves


def _snap_nodes_to_outlines(
    nodes: Sequence[_Box], outlines: Sequence[_Box], *, contain_frac: float = 0.8
) -> list[_Box]:
    """Replace each detector node box with the exact drawn rectangle it lives in.

    The detector decides *that a node is here* (semantics); the classical rectangle
    gives *exactly where its border is* (geometry). Snapping a node to the smallest
    leaf rectangle that contains it fuses the two with no node-vs-panel gate: the
    node's own box wins over an enclosing panel because the panel is not a leaf, and a
    shape with no drawn rectangle (an ellipse, or a box only the detector saw) simply
    keeps its detector box. This also fixes the interior-text leak — the detector box
    hugs the text and can miss part of it, but the drawn rectangle covers all of it.
    """
    leaves = _leaf_outlines(outlines)
    snapped: list[_Box] = []
    for n in nodes:
        threshold = contain_frac * _box_area(n)
        best, best_area = None, None
        for r in leaves:
            if _intersection_area(n, r) >= threshold:
                area = _box_area(r)
                if best_area is None or area < best_area:
                    best, best_area = r, area
        snapped.append(best if best is not None else n)
    return snapped


def _node_ink_mask(
    shape: tuple[int, int],
    nodes: Sequence[_Box],
    containers: Sequence[_Box],
    *,
    pad: int,
    border: int,
):
    import cv2

    mask = np.zeros(shape, dtype=np.uint8)
    for b in nodes:  # whole node box (interior text + border)
        cv2.rectangle(mask, (int(b.x0) - pad, int(b.y0) - pad), (int(b.x1) + pad, int(b.y1) + pad), 1, -1)
    # Only the border band for panels — keep interiors (connectors live inside panels).
    for b in containers:
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

    A connector is a stroke that lives *between* nodes. So binarise the ink, remove the
    nodes, and take the connected components of what remains: each component is one
    whole connector — elbow and curved routes stay intact, unlike straight LSD
    segments. A component is attached to the (up to two) nearest node boxes; touching
    two distinct nodes makes an edge. Components are kept only if elongated (line-like),
    dropping stray text blobs floating outside nodes.

    Removing the nodes relies on a clean division of labour: the detector owns
    *semantics* (a node/container is here) and the classical rectangles own *geometry*
    (the exact border). Each node is snapped to its drawn rectangle so its whole
    interior — including text the text-tight detector box missed — is erased, and the
    thin border of every drawn rectangle is wiped (a box outline is never a connector).
    There is deliberately no node-vs-panel classification: a panel is simply a
    rectangle that no node snaps to, left open so the connectors inside it survive.
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
    # Snap nodes to their exact drawn rectangles (precise geometry, kills interior
    # text), then fill those and erase the border of every drawn rectangle. Panels are
    # the rectangles no node snapped to: their border is wiped but their interior is
    # kept, so connectors routed inside them survive.
    outlines = detect_box_outlines(gray)
    nodes = _snap_nodes_to_outlines(nodes, outlines)
    mask = _node_ink_mask((h, w), nodes, list(containers) + list(outlines), pad=4, border=6)
    connector_ink = ink & (1 - mask)
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
        if nodes[ni] == nodes[nj]:  # two detector boxes snapped to the same drawn rectangle
            continue
        key = (min(ni, nj), max(ni, nj))
        if key in edges:
            continue
        # Trace the connector's *actual* route through the component (a shortest
        # path on the component pixels) instead of a straight end-to-end line. The
        # box regions are holes in connector_ink, so the route necessarily follows
        # the orthogonal ink and bends around nodes — no diagonals, no box crossings.
        sub = (labels[y : y + bh, x : x + bw] == ci)
        route = _route_through_component(
            sub, (int(round(end_a[1])) - y, int(round(end_a[0])) - x),
            (int(round(end_b[1])) - y, int(round(end_b[0])) - x),
        )
        if route is None:
            polyline = ((float(end_a[0]), float(end_a[1])), (float(end_b[0]), float(end_b[1])))
        else:
            polyline = tuple((float(c + x), float(r + y)) for r, c in _simplify_route(route))
        gap = max(_point_to_box(end_a, nodes[ni]), _point_to_box(end_b, nodes[nj]))
        ortho, excursion, edge_off = _route_geometry(polyline, nodes[ni], nodes[nj], diag=math.hypot(w, h))
        edges[key] = ClassicalEdge(
            source=ni, target=nj, polyline=polyline, gap=gap, ortho=ortho, excursion=excursion, edge_off=edge_off
        )
    return list(edges.values())


def _route_through_component(sub: np.ndarray, start: tuple[int, int], goal: tuple[int, int]):
    """Shortest 8-connected path between two pixels within a component mask (BFS)."""
    from collections import deque

    h, w = sub.shape
    if not (0 <= start[0] < h and 0 <= start[1] < w and 0 <= goal[0] < h and 0 <= goal[1] < w):
        return None
    if not sub[start] or not sub[goal]:
        return None
    parent: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    queue = deque([start])
    while queue:
        cur = queue.popleft()
        if cur == goal:
            path = [cur]
            while parent[path[-1]] is not None:
                path.append(parent[path[-1]])  # type: ignore[arg-type]
            return list(reversed(path))
        r, c = cur
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                nb = (r + dr, c + dc)
                if 0 <= nb[0] < h and 0 <= nb[1] < w and sub[nb] and nb not in parent:
                    parent[nb] = cur
                    queue.append(nb)
    return None


def _simplify_route(route: list[tuple[int, int]], *, epsilon: float = 4.0) -> list[tuple[int, int]]:
    import cv2

    pts = np.array([[c, r] for r, c in route], dtype=np.int32).reshape(-1, 1, 2)
    approx = cv2.approxPolyDP(pts, epsilon, False)
    return [(int(p[0][1]), int(p[0][0])) for p in approx]


def _point_to_box(point: np.ndarray, b: _Box) -> float:
    dx = max(b.x0 - point[0], 0.0, point[0] - b.x1)
    dy = max(b.y0 - point[1], 0.0, point[1] - b.y1)
    return math.hypot(dx, dy)


def _edge_offset(point: tuple[float, float], b: _Box) -> float:
    """How far the attachment lands from the nearest node-edge midpoint.

    0.0 = dead centre of an edge face (where real connectors attach), → 0.5 = at a
    corner (where a brace/decoration tip tends to touch). A learned feature, not a gate.
    """
    px, py = float(point[0]), float(point[1])
    ax, ay = min(max(px, b.x0), b.x1), min(max(py, b.y0), b.y1)
    if min(abs(py - b.y0), abs(py - b.y1)) <= min(abs(px - b.x0), abs(px - b.x1)):
        return abs((ax - b.x0) / max(1.0, b.x1 - b.x0) - 0.5)  # nearest is a horizontal edge
    return abs((ay - b.y0) / max(1.0, b.y1 - b.y0) - 0.5)  # nearest is a vertical edge


def _route_geometry(
    polyline: tuple[tuple[float, float], ...], box_i: _Box, box_j: _Box, *, diag: float
) -> tuple[float, float, float]:
    """(ortho, excursion, edge_off) for a candidate route — see ClassicalEdge fields."""
    pts = [(float(px), float(py)) for px, py in polyline]
    route_len = ortho_len = 0.0
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        ddx, ddy = abs(bx - ax), abs(by - ay)
        seg = math.hypot(ddx, ddy)
        route_len += seg
        if min(ddx, ddy) <= 0.36 * max(ddx, ddy, 1e-6):  # within ~20 deg of an axis
            ortho_len += seg
    ortho = ortho_len / route_len if route_len else 1.0
    ux0, uy0 = min(box_i.x0, box_j.x0), min(box_i.y0, box_j.y0)
    ux1, uy1 = max(box_i.x1, box_j.x1), max(box_i.y1, box_j.y1)
    excursion = max(max(ux0 - px, 0.0, px - ux1) + max(uy0 - py, 0.0, py - uy1) for px, py in pts) / max(1.0, diag)
    edge_off = max(_edge_offset(pts[0], box_i), _edge_offset(pts[-1], box_j))
    return ortho, excursion, edge_off


def _nearest_node_to_point(point: np.ndarray, nodes: Sequence[_Box], *, max_dist: float) -> int | None:
    best, best_d = None, max_dist
    for idx, b in enumerate(nodes):
        d = _point_to_box(point, b)
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
