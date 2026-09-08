"""Image-coordinate geometry; no annotations or research artifacts enter runtime."""
from dataclasses import replace
import math
from image_to_editable_ppt.ml.visual_geometry import detect_visual_geometry
from image_to_editable_ppt.v3.core.enums import NodeKind, ContainerKind, PortOwnerKind
from image_to_editable_ppt.v3.core.types import BBox, ImageSize, Point
from image_to_editable_ppt.v3.emit.models import EmitScene, EmitShapePrimitive


def pixel_box(box, size):
    return tuple(round(v*size[i%2]) for i,v in enumerate(box))


def intersection(a,b):
    return max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))


def area(a):
    return max(0,a[2]-a[0])*max(0,a[3]-a[1])


def validate_roi(roi, size):
    if len(roi)!=4 or not all(math.isfinite(v) and 0<=v<=1 for v in roi) or roi[0]>=roi[2] or roi[1]>=roi[3]:
        raise ValueError('region must be normalized x0 y0 x1 y1 with 0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1')
    a,b,c,d=pixel_box(roi,size)
    if c-a<16 or d-b<16:
        raise ValueError('region must be at least 16 by 16 source pixels')
    return a,b,c,d


def detect_scene(rgb, roi):
    h,w=rgb.shape[:2]; x0,y0,x1,y1=validate_roi(roi,(w,h))
    evidence=detect_visual_geometry(rgb[y0:y1,x0:x1])
    shapes=[]
    for role,candidates in ((PortOwnerKind.NODE,evidence.nodes),(PortOwnerKind.CONTAINER,evidence.containers)):
        for i,c in enumerate(candidates):
            a,b,d,e=c.bbox
            # Tiny degenerate proposals have no editable closed interior.
            if d-a<4 or e-b<4: continue
            kind=ContainerKind.FLOW_CLUSTER if role is PortOwnerKind.CONTAINER else (
                NodeKind.ELLIPSE if c.source=='closed_ellipse' else NodeKind.ROUNDED_BOX if c.source=='uniform_fill' else NodeKind.BOX)
            shapes.append(EmitShapePrimitive(f'{role.value}:region:{i}',role,kind,BBox(a+x0,b+y0,d+x0,e+y0),
                c.confidence,source=f'visual_geometry:{c.source}',provenance=('region:source_geometry',)))
    return EmitScene(image_size=ImageSize(w,h),shapes=tuple(shapes),source='region_native_v1')


def normalize_scene(scene):
    # Fit both dimensions inside PowerPoint limits; preserve source-image coordinate frame.
    scale=768/max(scene.image_size.width,scene.image_size.height)
    def box(b): return BBox(b.x0*scale,b.y0*scale,b.x1*scale,b.y1*scale)
    return replace(scene,image_size=ImageSize(max(128,round(scene.image_size.width*scale)),max(128,round(scene.image_size.height*scale))),
        shapes=tuple(replace(s,bbox=box(s.bbox)) for s in scene.shapes),
        connectors=tuple(replace(c,path_points=tuple(Point(p.x*scale,p.y*scale) for p in c.path_points)) for c in scene.connectors)),scale
