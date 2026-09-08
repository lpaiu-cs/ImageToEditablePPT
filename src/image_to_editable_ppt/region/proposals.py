"""Region-only proposals: verify fill boundaries before suppressing outlines.

The legacy ML detector remains unchanged. Uniform connected components are not
necessarily objects: opening can carve a panel background into rectangular-ish
pieces. Every accepted fill must have independent contrast on all four sides.
"""
import numpy as np
from image_to_editable_ppt.ml.visual_geometry import (
    VisualGeometry, _filled_candidates, _outline_candidates, _dedupe,
    _merge_titled_panels, _panel_node_candidates, _ellipse_candidates,
    _intersection_over_smaller, _has_nested_structure, _has_header_divider,
    _is_header_partition,
)


def fill_boundary_support(rgb, candidate):
    """Fraction of each central side with an observed inside/outside transition.

    Sample actual pixels on both sides, excluding rounded corners. A clipped
    side is not closure evidence. Median bands resist isolated crossing strokes;
    no label, position prior, or image identity participates in this test.
    """
    x0, y0, x1, y1 = candidate.bbox
    h, w = rgb.shape[:2]
    band = max(2, min(12, round(min(x1-x0, y1-y0)*.06)))
    if x0 < band or y0 < band or x1+band > w or y1+band > h:
        return (0., 0., 0., 0.)
    mx, my = max(1, round((x1-x0)*.15)), max(1, round((y1-y0)*.15))
    support=[0.,0.,0.,0.]
    # Quantization/opening may inset a proposal from its low-contrast border.
    # Search one coherent parallel band per side, never a different offset per
    # pixel. The 12px cap bounds the observed border/shadow neighborhood.
    for offset in range(13):
        pairs = [
            (rgb[y0:y0+band, x0+mx:x1-mx], rgb[max(0,y0-band-offset):max(0,y0-offset), x0+mx:x1-mx], 0),
            (rgb[y1-band:y1, x0+mx:x1-mx], rgb[y1+offset:min(h,y1+band+offset), x0+mx:x1-mx], 0),
            (rgb[y0+my:y1-my, x0:x0+band], rgb[y0+my:y1-my, max(0,x0-band-offset):max(0,x0-offset)], 1),
            (rgb[y0+my:y1-my, x1-band:x1], rgb[y0+my:y1-my, x1+offset:min(w,x1+band+offset)], 1),
        ]
        for side,(a,b,axis) in enumerate(pairs):
            if b.shape[axis]!=band: continue
            difference=np.max(np.abs(np.median(a,axis=axis)-np.median(b,axis=axis)),axis=1)
            support[side]=max(support[side],float((difference>=18).mean()))
    return tuple(support)


def detect_region_geometry(rgb):
    array = np.asarray(rgb, dtype=np.uint8)
    fills = [c for c in _filled_candidates(array) if min(fill_boundary_support(array,c)) >= .70]
    # The unchanged area floor already excludes glyphs. Narrow vertical nodes
    # should not be rejected solely because the selected ROI is very wide.
    raw = _outline_candidates(array, minimum_width_fraction=.025)
    # A fill enclosing multiple independent outlines is a possible panel, not
    # an OCR-owning node. Leave fill-only panels blank in this conservative
    # path; independently outlined containers are handled below.
    fills = [f for f in fills if not _has_nested_structure(f,raw)]
    # Prefer an independently observed square outline over its interior fill.
    # High side coverage and near-identical bounds exclude genuinely rounded
    # silhouettes and parent/child containment from this tie break.
    fills = [f for f in fills if not any(c.confidence>=.98
        and min(c.area,f.area)/max(c.area,f.area)>.85
        and _intersection_over_smaller(c,f)>.95 for c in raw)]
    outlines = _dedupe([*raw, *_merge_titled_panels(raw,image_shape=array.shape[:2])])
    panel_nodes = _panel_node_candidates(array,[c for c in outlines if c.source=='titled_panel'])
    candidates = _dedupe([*fills, *(c for c in outlines
        if not any(_intersection_over_smaller(c,f)>.70
            and min(c.area,f.area)/max(c.area,f.area)>.70 for f in fills)),
        *panel_nodes, *_ellipse_candidates(array)])
    detected = tuple(c for c in outlines if c.source=='titled_panel'
        or _has_nested_structure(c,candidates) or _has_header_divider(array,c))
    containers = tuple(c for c in detected if c.source=='titled_panel' or not _is_header_partition(c,detected))
    nodes = tuple(c for c in candidates if c not in containers and not _is_header_partition(c,containers))
    return VisualGeometry(nodes=nodes,containers=containers)
