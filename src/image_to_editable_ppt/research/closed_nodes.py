"""Closed original-ink node interiors, independent of model kind and GT."""
from dataclasses import replace
import math

import cv2
import numpy as np

from image_to_editable_ppt.region.strokes import stroke_mask
from image_to_editable_ppt.v3.core.enums import NodeKind, PortOwnerKind
from image_to_editable_ppt.v3.emit.style import ShapeVisualStyle, sample_shape_styles


def closed_interiors(rgb):
    raw = stroke_mask(rgb)
    contours, hierarchy = cv2.findContours(raw, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    holes = [] if hierarchy is None else [c for c,h in zip(contours,hierarchy[0]) if h[3] >= 0]
    return raw, holes


def observe_closed_node(rgb, bbox, *, evidence=None):
    raw, holes = closed_interiors(rgb) if evidence is None else evidence
    x0,y0,x1,y1 = bbox
    width,height = x1-x0,y1-y0
    if min(width,height) < 12:
        return None, dict(reason='small_owner')
    # Detector errors are relative to each axis. A long, shallow node must not
    # use its tiny height as the allowed horizontal uncertainty.
    tolerance = np.array([max(4.,.05*width),max(4.,.05*height)]*2)
    candidates = []
    for contour in holes:
        x,y,w,h = cv2.boundingRect(contour)
        area = cv2.contourArea(contour)
        if .45*width*height <= area <= 1.1*width*height and np.all(np.abs(np.array([x,y,x+w,y+h])-bbox) <= tolerance):
            candidates.append(contour)
    if len(candidates) != 1:
        return None, dict(reason='no_unique_closed_interior', candidates=len(candidates))
    contour = candidates[0]
    x,y,w,h = cv2.boundingRect(contour)
    points = contour[:,0,:].astype(float)
    normalized = (points - [x+(w-1)/2,y+(h-1)/2]) / [(w-1)/2,(h-1)/2]
    residual = np.abs(np.linalg.norm(normalized,axis=1)-1)
    angle = (np.arctan2(normalized[:,1],normalized[:,0])+math.pi) / (2*math.pi)
    angular_bins = len(set(np.minimum(35,(angle*36).astype(int))))
    occupancy = cv2.contourArea(contour)/((w-1)*(h-1))
    ellipse = float(np.percentile(residual,95)) <= .06 and float(residual.max()) <= .13 and angular_bins >= 32 and .70 <= occupancy <= .87
    # A closed irregular object is not automatically a box. Require the same
    # four near-axis sides for retaining the detector's rectangular primitive.
    boundary_distance = np.minimum(1-np.abs(normalized[:,0]),1-np.abs(normalized[:,1]))
    rectangle = occupancy >= .90 and float(np.percentile(boundary_distance,95)) <= .15
    audit = dict(reason='closed_supported_ellipse' if ellipse else 'closed_supported_box' if rectangle else 'unsupported_closed_geometry',
                 interior_bbox=[x,y,x+w,y+h],occupancy=occupancy,radial_p95=float(np.percentile(residual,95)),angular_bins=angular_bins)
    if not (ellipse or rectangle):
        return None, audit
    interior = np.zeros(raw.shape,np.uint8)
    cv2.drawContours(interior,[contour],-1,1,cv2.FILLED)
    inset = max(2,round(min(w,h)*.10))
    core = cv2.erode(interior,np.ones((2*inset+1,2*inset+1),np.uint8))
    if not core.any():
        return None,dict(audit,reason='empty_closed_core')
    fill = tuple(int(v) for v in np.median(rgb[core!=0],axis=0))
    # OpenCV hole contours run on the surrounding ink pixels, not purely in
    # the empty hole. Include that contour fringe; excluding it drops 1px lines.
    inner = cv2.erode(interior,np.ones((3,3),np.uint8))
    ring = cv2.dilate(interior,np.ones((7,7),np.uint8)) & (1-inner) & raw
    ink = rgb[ring!=0]
    if len(ink) < .5*cv2.arcLength(contour,True):
        return None,dict(audit,reason='insufficient_closed_border_ink')
    stroke = tuple(int(v) for v in np.median(ink,axis=0))
    if max(abs(a-b) for a,b in zip(fill,stroke)) < 24:
        return None,dict(audit,reason='indistinct_closed_border')
    # White interiors need no fill. Every nonwhite fill came from this closed
    # interior, never a panel-wide median or an open boundary.
    style = ShapeVisualStyle(fill=fill if max(255-v for v in fill)>=24 else None,stroke=stroke)
    return dict(ellipse=ellipse,style=style),dict(audit,fill=fill,stroke=stroke)


def recover_closed_nodes(scene,rgb):
    evidence = closed_interiors(rgb)
    styles = sample_shape_styles(rgb,scene)
    shapes = []
    records = []
    for shape in scene.shapes:
        if shape.owner_kind is not PortOwnerKind.NODE or shape.shape_kind not in (NodeKind.BOX,NodeKind.ROUNDED_BOX,NodeKind.ELLIPSE):
            shapes.append(shape)
            continue
        b=shape.bbox
        observed,audit = observe_closed_node(rgb,[b.x0,b.y0,b.x1,b.y1],evidence=evidence)
        if observed:
            if observed['ellipse']:
                shape=replace(shape,shape_kind=NodeKind.ELLIPSE,provenance=shape.provenance+('r10:closed_rgb_ellipse',))
            styles[shape.id]=observed['style']
        else:
            # No new fill from an unverified closed boundary.
            styles[shape.id]=replace(styles[shape.id],fill=None)
        records.append(dict(id=shape.id,**audit))
        shapes.append(shape)
    return replace(scene,shapes=tuple(shapes)),styles,dict(nodes=records)
