"""R7b oracle-dependent diagnostic guards; not production recognition."""
from dataclasses import replace
import cv2
import numpy as np

from image_to_editable_ppt.research.accepted_owners import AcceptedScene, SUPPORTED, targets, observe_accepted
from image_to_editable_ppt.region.tracing import trace_scene
from image_to_editable_ppt.region.text import recover_labels
from image_to_editable_ppt.v3.emit.style import ShapeVisualStyle, sample_shape_styles


def neutralize_boxes(rgb, boxes):
    clean = rgb.copy()
    h, w = rgb.shape[:2]
    for a, b, c, d in boxes:
        a, b, c, d = max(0, round(a)), max(0, round(b)), min(w, round(c)), min(h, round(d))
        left, top, right, bottom = max(0, a-3), max(0, b-3), min(w, c+3), min(h, d+3)
        patch = rgb[top:bottom, left:right]
        ring = np.ones(patch.shape[:2], bool)
        ring[b-top:d-top, a-left:c-left] = False
        clean[b:d, a:c] = np.median(patch[ring], axis=0) if ring.any() else [255, 255, 255]
    return clean


def reject_boundary_components(scene, audit, mask):
    """Unresolved external source ownership is not evidence for a local edge."""
    _, components = cv2.connectedComponents(mask, connectivity=8)
    border = np.zeros(mask.shape, bool)
    border[:2] = True
    border[-2:] = True
    border[:, :2] = True
    border[:, -2:] = True
    boundary = set(np.unique(components[border])) - {0}
    rejected = {r['connector_id']: 'component_touches_scope_boundary'
                for r in audit['components'] if r['component'] in boundary and 'connector_id' in r}
    return replace(scene, connectors=tuple(c for c in scene.connectors if c.id not in rejected)), rejected


def observe_guarded(accepted, rgb, scope, annotation, *, ocr=True):
    if not isinstance(accepted, AcceptedScene):
        raise TypeError('AcceptedScene required')
    h, w = rgb.shape[:2]
    blockers = [tuple(v + (-3 if i < 2 else 3) for i, v in enumerate(o['bbox']))
                for o in targets(annotation) if o['geometry'] not in SUPPORTED]
    clean = neutralize_boxes(rgb, [*accepted.exclusions, *blockers])
    roi = tuple(v / (w, h)[i % 2] for i, v in enumerate(scope))
    blocked, audit, mask = trace_scene(accepted.scene, clean, roi)
    final, rejected = reject_boundary_components(blocked, audit, mask)
    # Keep the R7 OCR input unchanged so this arm isolates topology and style.
    ocr_scene, text = recover_labels(accepted.scene, neutralize_boxes(rgb, accepted.exclusions), enabled=ocr)
    final = replace(final, shapes=ocr_scene.shapes)
    return final, dict(tracing=audit, text=text, blockers=blockers, rejected_boundary=rejected), blocked


def owned_styles(accepted, rgb):
    if not isinstance(accepted, AcceptedScene):
        raise TypeError('AcceptedScene required')
    baseline = sample_shape_styles(rgb, accepted.scene)
    parents = dict(accepted.parents)
    shapes = {s.id: s for s in accepted.scene.shapes}
    styles, audit = {}, {}
    for sid, s in shapes.items():
        a, b, c, d = map(round, (s.bbox.x0, s.bbox.y0, s.bbox.x1, s.bbox.y1))
        inset = max(3, min(12, round(min(c-a, d-b)*.06)))
        a, b, c, d = a+inset, b+inset, c-inset, d-inset
        if c <= a or d <= b:
            styles[sid] = ShapeVisualStyle(stroke=(71, 85, 105))
            audit[sid] = dict(reason='too_small', fill=None)
            continue
        keep = np.ones((d-b, c-a), bool)
        exclusions = list(accepted.exclusions)
        for child_id, child in shapes.items():
            p = parents[child_id]
            while p is not None:
                if p == sid:
                    cb = child.bbox
                    exclusions.append((cb.x0-2, cb.y0-2, cb.x1+2, cb.y1+2))
                    break
                p = parents[p]
        for box in exclusions:
            x0, y0, x1, y1 = map(round, box)
            x0, y0, x1, y1 = max(a, x0), max(b, y0), min(c, x1), min(d, y1)
            if x1 > x0 and y1 > y0:
                keep[y0-b:y1-b, x0-a:x1-a] = False
        pixels = rgb[b:d, a:c][keep]
        fill = None
        support = 0.
        if len(pixels) >= 64:
            quantized = pixels.astype(np.int32)//16
            keys = quantized[:, 0]*256 + quantized[:, 1]*16 + quantized[:, 2]
            values, counts = np.unique(keys, return_counts=True)
            winner = values[np.argmax(counts)]
            support = float(counts.max()/len(pixels))
            if support >= .60:
                fill = tuple(map(int, np.median(pixels[keys == winner], axis=0)))
        stroke = baseline[sid].stroke
        if stroke is None or (fill is not None and max(abs(x-y) for x, y in zip(stroke, fill)) < 24):
            stroke = (71, 85, 105)
        styles[sid] = ShapeVisualStyle(fill=fill, stroke=stroke)
        audit[sid] = dict(owned_pixels=len(pixels), modal_support=support, fill=fill,
                          reason='owned_interior' if fill is not None else 'uncertain_fill_abstention')
    return styles, audit
