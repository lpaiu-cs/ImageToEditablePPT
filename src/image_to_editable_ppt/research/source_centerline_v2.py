"""R9-C v2: physical pixel-cell support; frozen v1 remains unchanged."""
from collections import Counter
from dataclasses import replace
import math

import cv2
import numpy as np

from image_to_editable_ppt.region.strokes import stroke_mask
from image_to_editable_ppt.region.tracing import trace_scene
from image_to_editable_ppt.v3.core.enums import NodeKind, PortOwnerKind
from image_to_editable_ppt.v3.core.types import Point


def line_box_hits(origin, direction, box):
    hits = []
    for axis in (0, 1):
        if abs(direction[axis]) < 1e-10:
            continue
        for boundary in (box[axis], box[axis+2]):
            p = origin + direction * ((boundary-origin[axis])/direction[axis])
            k = 1-axis
            if box[k]-1e-6 <= p[k] <= box[k+2]+1e-6:
                hits.append(p)
    return hits


def segment_hits_box(a, b, box):
    lo, hi = 0., 1.
    for axis in (0, 1):
        delta = b[axis]-a[axis]
        if abs(delta) < 1e-10:
            if not box[axis] <= a[axis] <= box[axis+2]:
                return False
        else:
            bounds = sorted([(box[axis]-a[axis])/delta, (box[axis+2]-a[axis])/delta])
            lo, hi = max(lo, bounds[0]), min(hi, bounds[1])
            if lo > hi:
                return False
    return True


def pixel_cell_support(along, direction):
    """Union length of physical pixel-cell projections, not occupied point bins."""
    half = .5*float(np.abs(direction).sum())
    intervals = sorted((float(t)-half, float(t)+half) for t in along)
    left, right = intervals[0]
    first = left
    covered, gap = 0., 0.
    for a, b in intervals[1:]:
        if a <= right+1e-9:
            right = max(right, b)
        else:
            covered += right-left
            gap = max(gap, a-right)
            left, right = a, b
    covered += right-left
    return covered/(right-first), gap


def fit_observed_line(pixels, boxes, endpoints, *, scale, other_boxes=()):
    """Return two observed owner intersections or None, plus fixed-rule evidence."""
    pixels = np.asarray(pixels, dtype=float).reshape(-1, 2)
    record = dict(raw_ink_pixels=len(pixels), scale=scale)
    def reject(reason):
        return None, dict(record, decision='unchanged', reason=reason)
    if not math.isfinite(scale) or scale <= 0 or not np.isfinite(pixels).all():
        raise ValueError('invalid source observation')
    if len(pixels) < 12:
        return reject('insufficient_ink')
    origin = pixels.mean(axis=0)
    covariance = np.cov(pixels-origin, rowvar=False)
    values, vectors = np.linalg.eigh(covariance)
    if values[-1] <= 4*max(values[0], 1e-12):
        return reject('ambiguous_principal_axis')
    direction = vectors[:, -1]
    along = (pixels-origin) @ direction
    residual = np.abs((pixels-origin) @ np.array([-direction[1], direction[0]]))
    span = float(np.ptp(along))
    record.update(span=span, p95=float(np.percentile(residual, 95)), maximum=float(residual.max()))
    if span < 24*scale:
        return reject('short_span')
    if record['p95'] > 2*scale or record['maximum'] > 3*scale:
        return reject('not_single_straight_stroke')
    coverage, gap = pixel_cell_support(along, direction)
    record.update(occupied_fraction=coverage, max_empty_gap=gap,
                  support_measure='projected_physical_pixel_cells')
    if coverage < .90 or gap > 2*scale:
        return reject('discontinuous_source_support')
    result, movements, extensions = [], [], []
    for box, old in zip(boxes, endpoints, strict=True):
        hits = line_box_hits(origin, direction, box)
        if not hits:
            return reject('line_misses_owner')
        point = min(hits, key=lambda p: float(np.linalg.norm(p-old)))
        movement = float(np.linalg.norm(point-old))
        projection = float((point-origin) @ direction)
        extension = max(0., float(along.min())-projection, projection-float(along.max()))
        result.append(point)
        movements.append(movement)
        extensions.append(extension)
    record.update(endpoint_movements=movements, endpoint_extensions=extensions)
    if max(movements) > 6*scale:
        return reject('large_endpoint_change')
    if max(extensions) > 8*scale:
        return reject('unsupported_endpoint_extension')
    if np.linalg.norm(result[1]-result[0]) < 1e-6:
        return reject('degenerate_route')
    if any(segment_hits_box(result[0], result[1], b) for b in other_boxes):
        return reject('third_owner_intersection')
    return tuple(Point(float(p[0]), float(p[1])) for p in result), dict(record, decision='refined', reason='supported_raw_centerline')


def trace_with_centerlines(scene, rgb):
    traced, original_audit, mask = trace_scene(scene, rgb, (0, 0, 1, 1), transparent_gaps=True)
    _, labels = cv2.connectedComponents(mask, connectivity=8)
    raw = stroke_mask(rgb)
    owners = {s.id: s for s in scene.shapes}
    records = {r['connector_id']: r for r in original_audit['components'] if 'connector_id' in r}
    multiplicity = Counter(r['component'] for r in records.values())
    connectors, evidence = [], {}
    def bounds(s):
        b = s.bbox
        return [b.x0, b.y0, b.x1, b.y1]
    for connector in traced.connectors:
        r = records[connector.id]
        pair = [owners[connector.source_owner_id], owners[connector.target_owner_id]]
        if (len(r['owners']) != 2 or multiplicity[r['component']] != 1
                or connector.arrowhead_start or connector.arrowhead_end
                or connector.source != 'r3_stroke_trace'
                or any(s.shape_kind is not NodeKind.LABEL_ANCHOR for s in pair)):
            connectors.append(connector)
            evidence[connector.id] = dict(decision='unchanged', reason='outside_frozen_scope')
            continue
        yy, xx = np.where((labels == r['component']) & (raw > 0))
        points, audit = fit_observed_line(np.column_stack([xx, yy]), [bounds(s) for s in pair],
            [np.array([p.x, p.y]) for p in (connector.path_points[0], connector.path_points[-1])],
            scale=rgb.shape[0]/360, other_boxes=[bounds(s) for s in scene.shapes
                if s.owner_kind is PortOwnerKind.NODE and s.id not in {a.id for a in pair}])
        evidence[connector.id] = dict(audit, previous_path=[[p.x, p.y] for p in connector.path_points],
                                     new_path=[[p.x, p.y] for p in points] if points else None)
        connectors.append(replace(connector, path_points=points) if points else connector)
    return replace(traced, connectors=tuple(connectors)), traced, dict(original_trace=original_audit, centerlines=evidence)
