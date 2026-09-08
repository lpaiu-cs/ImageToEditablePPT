"""Research original-ink straight arrows; no OCR, ground truth or file IO."""
from dataclasses import replace
from itertools import combinations
import math

import cv2
import numpy as np

from image_to_editable_ppt.region.strokes import stroke_mask
from image_to_editable_ppt.research.source_centerline_v2 import line_box_hits, pixel_cell_support, segment_hits_box
from image_to_editable_ppt.v3.core.enums import ConnectorKind, NodeKind, PortOwnerKind
from image_to_editable_ppt.v3.core.types import Point
from image_to_editable_ppt.v3.emit.models import EmitConnectorPrimitive


def _axis(points, forward):
    center = points.mean(axis=0)
    _, vectors = np.linalg.eigh(np.cov(points-center, rowvar=False))
    axis = vectors[:, -1]
    if axis @ forward < 0:
        axis = -axis
    return center, axis


def _head(along, across, length, shaft_width, scale, cell_extent, reverse=False):
    t = length-along if reverse else along
    # Integer cells projected on the actual axis, no dilated mask widths.
    end = float(t.max())
    step = max(.75, scale)
    left = end-16*scale
    profile = []
    for start in np.arange(left, end, step):
        values = across[(t+cell_extent/2 > start) & (t-cell_extent/2 < start+step)]
        profile.append(float(np.ptp(values)+cell_extent) if len(values) else 0.)
    widths = np.asarray(profile)
    peak = int(np.argmax(widths))
    taper = widths[peak:]
    record = dict(profile=profile, peak=peak, shaft_width=shaft_width)
    if len(taper) < 3 or len(taper) > 12 or widths[peak] < max(1.6*shaft_width, shaft_width+2*scale):
        return False, dict(record, reason='no_terminal_widening')
    if taper[-1] > .75*taper[0] or taper[-1] > shaft_width+cell_extent:
        return False, dict(record, reason='no_tip_taper')
    correlation = float(np.corrcoef(np.arange(len(taper)), taper)[0, 1])
    record['taper_correlation'] = correlation
    if not math.isfinite(correlation) or correlation > -.8:
        return False, dict(record, reason='irregular_tip')
    # A head has a broad base, not a gradual blob centered on the shaft.
    if peak < 2 or min(widths[peak-2:peak]) > .85*widths[peak]:
        return False, dict(record, reason='no_head_base')
    wide = across[(t+cell_extent/2 > left+peak*step) & (t-cell_extent/2 < left+(peak+1)*step)]
    if min(float(wide.max()), -float(wide.min())) < .2*widths[peak]:
        return False, dict(record, reason='asymmetric_terminal')
    return True, dict(record, reason='observed_head_base_and_taper')


def _terminal_escape(pixels, along, across, length, scale, at_start):
    """Inspect source connectivity before clipping the transverse corridor."""
    distance = along if at_start else length-along
    selected = (distance >= 0) & (distance <= 16*scale)
    p = pixels[selected].astype(int)
    if not len(p):
        return False
    offsets = p.min(axis=0)
    q = p-offsets
    mask = np.zeros((q[:,1].max()+1,q[:,0].max()+1),np.uint8)
    mask[q[:,1],q[:,0]] = 1
    _, labels = cv2.connectedComponents(mask,connectivity=8)
    ids = labels[q[:,1],q[:,0]]
    v = np.abs(across[selected])
    inside = set(ids[v <= 8*scale])
    outside = set(ids[v > 8*scale])
    return bool(inside & outside)


def observe_pair(pixels, boxes, *, scale, other_boxes=()):
    """Propose a directed line only from source support between the given boxes."""
    pixels = np.asarray(pixels, dtype=float).reshape(-1, 2)
    boxes = np.asarray(boxes, dtype=float)
    if not np.isfinite(pixels).all() or not np.isfinite(boxes).all() or scale <= 0:
        raise ValueError('finite source geometry required')
    audit = {}
    def reject(reason):
        return None, dict(audit, reason=reason)
    centers = (boxes[:, :2]+boxes[:, 2:])/2
    delta = centers[1]-centers[0]
    length = float(np.linalg.norm(delta))
    if length < 24*scale:
        return reject('short_pair')
    axis = delta/length
    t = (pixels-centers[0]) @ axis
    normal = np.array([-axis[1], axis[0]])
    v = (pixels-centers[0]) @ normal
    shaft = pixels[(t > .2*length) & (t < .8*length) & (np.abs(v) <= 8*scale)]
    if len(shaft) < 12:
        return reject('insufficient_shaft')
    center, axis = _axis(shaft, axis)
    normal = np.array([-axis[1], axis[0]])
    residual = np.abs((shaft-center) @ normal)
    audit.update(p95=float(np.percentile(residual, 95)), maximum=float(residual.max()))
    if audit['p95'] > 3*scale or audit['maximum'] > 3*scale:
        return reject('nonlinear_or_competing_shaft')
    hits = [line_box_hits(center, axis, b) for b in boxes]
    if not all(hits):
        return reject('axis_misses_owner')
    a = max(hits[0], key=lambda p: float(p @ axis))
    b = min(hits[1], key=lambda p: float(p @ axis))
    length = float((b-a) @ axis)
    if length < 24*scale:
        return reject('short_exterior_span')
    if any(segment_hits_box(a, b, box) for box in other_boxes):
        return reject('third_owner_intersection')
    all_t = (pixels-a) @ axis
    all_v = (pixels-a) @ normal
    t,v = all_t,all_v
    inside = (t >= 0) & (t <= length) & (np.abs(v) <= 8*scale)
    t, v = t[inside], v[inside]
    if len(t) < 12:
        return reject('empty_exterior')
    # Interior support must be close to the fitted shaft, not a parallel offset.
    central = (t >= 16*scale) & (t <= length-16*scale)
    if not central.any() or np.abs(v[central]).max() > 3*scale:
        return reject('competing_interior_ink')
    coverage, gap = pixel_cell_support(t, axis)
    audit.update(coverage=coverage, max_gap=gap, extensions=[float(t.min()), length-float(t.max())])
    if coverage < .95 or gap > 2*scale or max(audit['extensions']) > 8*scale:
        return reject('unsupported_continuity_or_extension')
    # Pixel area / projected span estimates perpendicular shaft width consistently.
    shaft_width = float(central.sum()/max(1, length-32*scale))
    cell_extent = float(np.abs(axis).sum())
    end_head, end_audit = _head(t, v, length, shaft_width, scale, cell_extent)
    start_head, start_audit = _head(t, -v, length, shaft_width, scale, cell_extent, reverse=True)
    audit.update(start_head=start_audit, end_head=end_audit)
    if end_head == start_head:
        return reject('no_unique_arrowhead')
    opposite = end_audit if start_head else start_audit
    if max(opposite['profile']) >= max(1.6*shaft_width,shaft_width+2*scale):
        return reject('opposite_terminal_unresolved')
    if _terminal_escape(pixels,all_t,all_v,length,scale,start_head):
        return reject('terminal_source_contact_outside_corridor')
    points = (b, a) if start_head else (a, b)
    return tuple(Point(float(p[0]), float(p[1])) for p in points), dict(audit, reason='supported_source_arrow', reversed=start_head)


def add_source_rays(scene, rgb):
    """Keep owners and unsupported old paths; replace a pair only with new evidence."""
    anchors = [s for s in scene.shapes if s.shape_kind is NodeKind.LABEL_ANCHOR]
    raw = stroke_mask(rgb).copy()
    def box(s):
        return [s.bbox.x0, s.bbox.y0, s.bbox.x1, s.bbox.y1]
    for s in scene.shapes:
        if s.owner_kind is PortOwnerKind.NODE:
            x0,y0,x1,y1 = box(s)
            raw[max(0,math.floor(y0)):math.ceil(y1)+1,max(0,math.floor(x0)):math.ceil(x1)+1] = 0
    yy, xx = np.where(raw)
    pixels = np.column_stack([xx, yy])
    edges = list(scene.connectors)
    records = []
    for a,b in combinations(anchors, 2):
        pair = {a.id,b.id}
        if max(a.bbox.x0,b.bbox.x0) < min(a.bbox.x1,b.bbox.x1) and max(a.bbox.y0,b.bbox.y0) < min(a.bbox.y1,b.bbox.y1):
            continue
        x0=max(0,math.floor(min(a.bbox.x0,b.bbox.x0)))
        y0=max(0,math.floor(min(a.bbox.y0,b.bbox.y0)))
        x1=min(rgb.shape[1],math.ceil(max(a.bbox.x1,b.bbox.x1)))
        y1=min(rgb.shape[0],math.ceil(max(a.bbox.y1,b.bbox.y1)))
        region=rgb[y0:y1,x0:x1]
        if not region.size or float(np.median(region.reshape(-1,3),axis=0).min()) < 225:
            records.append(dict(owners=[a.id,b.id],reason='outside_bright_background_scope'))
            continue
        points, audit = observe_pair(pixels, [box(a),box(b)], scale=rgb.shape[0]/360,
            other_boxes=[box(s) for s in scene.shapes if s.owner_kind is PortOwnerKind.NODE and s.id not in pair])
        records.append(dict(owners=[a.id,b.id], **audit))
        if points is None:
            continue
        source,target = (b,a) if audit['reversed'] else (a,b)
        old = [e for e in edges if {e.source_owner_id,e.target_owner_id} == pair]
        # A contradictory direction is evidence of uncertainty, not permission to overwrite.
        if any(e.arrowhead_start or (e.arrowhead_end and e.source_owner_id != source.id) for e in old):
            records[-1]['reason'] = 'conflicting_existing_direction'
            continue
        edges = [e for e in edges if e not in old]
        cid = f'connector:r10-source:{len(records)}'
        edges.append(EmitConnectorPrimitive(cid,ConnectorKind.ARROW,.8,source.id,source.owner_kind,
            target.id,target.owner_kind,cid+':start',cid+':end',path_points=points,arrowhead_end=True,
            source='r10_original_ink_ray',provenance=('r10:raw_shaft','r10:terminal_base_and_taper')))
    return replace(scene,connectors=tuple(edges)), dict(pairs=records)
