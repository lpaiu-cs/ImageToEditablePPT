"""Region-only proposals: verify fill boundaries before suppressing outlines.

The legacy ML detector remains unchanged. Uniform connected components are not
necessarily objects: opening can carve a panel background into rectangular-ish
pieces. Every accepted fill must have independent contrast on all four sides.
"""
import numpy as np
import cv2
from image_to_editable_ppt.ml.visual_geometry import (
    VisualGeometry, GeometryCandidate, _filled_candidates, _outline_candidates, _dedupe,
    _merge_titled_panels, _panel_node_candidates, _ellipse_candidates,
    _intersection_over_smaller, _longest_true_fraction,
    _is_header_partition,
)


def nested(container,candidates):
    x0,y0,x1,y1=container.bbox
    return any(c!=container and c.area<container.area*.82
        and c.bbox[0]>=x0 and c.bbox[1]>=y0 and c.bbox[2]<=x1 and c.bbox[3]<=y1 for c in candidates)


def header_divider(edges,candidate):
    x0,y0,x1,y1=candidate.bbox; w,h=x1-x0,y1-y0
    if w<20 or h<20: return False
    inset=max(2,round(w*.03))
    crop=edges[y0+max(3,round(h*.06)):y0+max(4,round(h*.35)),x0+inset:x1-inset]
    return any(float(row.mean())>=.68 and _longest_true_fraction(row)>=.52 for row in crop>0)


def colored_boundary(rgb,candidate):
    x0,y0,x1,y1=candidate.bbox; h,w=rgb.shape[:2]
    band=3; mx=max(1,round((x1-x0)*.15)); my=max(1,round((y1-y0)*.15))
    chroma=rgb.max(axis=2).astype(np.int16)-rgb.min(axis=2)
    regions=[(chroma[max(0,y0-band):min(h,y0+band+1),x0+mx:x1-mx],0),
        (chroma[max(0,y1-band):min(h,y1+band+1),x0+mx:x1-mx],0),
        (chroma[y0+my:y1-my,max(0,x0-band):min(w,x0+band+1)],1),
        (chroma[y0+my:y1-my,max(0,x1-band):min(w,x1+band+1)],1)]
    return all(a.size and float((a.max(axis=axis)>=25).mean())>=.70 for a,axis in regions)


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
    gray=cv2.cvtColor(array,cv2.COLOR_RGB2GRAY)
    dark_field=(float(np.median(gray))<110 and all(float(np.median(side))<60
        for side in (gray[0,:],gray[-1,:],gray[:,0],gray[:,-1])))
    outline_rgb=255-array if dark_field else array
    raw = _outline_candidates(outline_rgb, minimum_width_fraction=.025)
    edges=np.maximum.reduce([cv2.Canny(array[:,:,i],20,60) for i in range(3)])
    edge_rgb=np.repeat((255-edges)[:,:,None],3,axis=2)
    extra=[c for c in _outline_candidates(edge_rgb,minimum_width_fraction=.025)
        if colored_boundary(array,c) and not any(_intersection_over_smaller(c,r)>.88
            and min(c.area,r.area)/max(c.area,r.area)>.85 for r in raw)]
    raw=_dedupe([*raw,*(GeometryCandidate(c.bbox,'contrast_outline',c.confidence) for c in extra)])
    # A fill enclosing multiple independent outlines is a possible panel, not
    # an OCR-owning node. Leave fill-only panels blank in this conservative
    # path; independently outlined containers are handled below.
    fills = [f for f in fills if not nested(f,raw)]
    # Prefer an independently observed square outline over its interior fill.
    # High side coverage and near-identical bounds exclude genuinely rounded
    # silhouettes and parent/child containment from this tie break.
    fills = [f for f in fills if not any(c.confidence>=.98
        and min(c.area,f.area)/max(c.area,f.area)>.85
        and _intersection_over_smaller(c,f)>.95 for c in raw)]
    outlines = _dedupe([*raw, *_merge_titled_panels(raw,image_shape=array.shape[:2])])
    panel_nodes = _panel_node_candidates(outline_rgb,[c for c in outlines if c.source=='titled_panel'])
    candidates = _dedupe([*fills, *(c for c in outlines
        if not any(_intersection_over_smaller(c,f)>.70
            and min(c.area,f.area)/max(c.area,f.area)>.70 for f in fills)),
        *panel_nodes, *_ellipse_candidates(outline_rgb)])
    detected = tuple(c for c in outlines if c.source=='titled_panel'
        or nested(c,candidates) or header_divider(edges,c))
    containers = tuple(c for c in detected if c.source=='titled_panel' or not _is_header_partition(c,detected))
    nodes = tuple(c for c in candidates if c not in containers and not _is_header_partition(c,containers))
    return VisualGeometry(nodes=nodes,containers=containers)
