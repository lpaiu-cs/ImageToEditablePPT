"""Reusable research native pipeline; only RGB and fresh detector objects enter."""
from dataclasses import asdict
import math
import numpy as np

from image_to_editable_ppt.v3.core.enums import ContainerKind,NodeKind,PortOwnerKind
from image_to_editable_ppt.v3.core.types import BBox,ImageSize
from image_to_editable_ppt.v3.emit.models import EmitScene,EmitShapePrimitive
from image_to_editable_ppt.v3.emit import sample_shape_styles
from image_to_editable_ppt.v3.text.ocr import _load_engine
from image_to_editable_ppt.region.geometry import normalize_scene
from image_to_editable_ppt.region.text import recover_labels
from image_to_editable_ppt.research.text_only_ocr import recover_text_only
from image_to_editable_ppt.research.spatial_ocr_observation import observe
from image_to_editable_ppt.research.spatial_ocr_owners import apply_observations
from image_to_editable_ppt.research.source_centerline_v2 import trace_with_centerlines
from image_to_editable_ppt.research.source_rays import add_source_rays
from image_to_editable_ppt.research.spatial_text import recover_spatial_text
from image_to_editable_ppt.research.label_anchor_native import write_label_anchor_native


def detector_scene(rgb,objects):
    if not isinstance(rgb,np.ndarray) or rgb.dtype!=np.uint8 or rgb.ndim!=3 or rgb.shape[2]!=3:
        raise ValueError('uint8 RGB required')
    h,w=rgb.shape[:2];shapes=[];seen=set()
    for obj in objects:
        if set(obj)!={'id','role','semantic_kind','bbox_xyxy','confidence'}:
            raise ValueError('detector-only fields required; labels and relations are forbidden')
        if not isinstance(obj['id'],str) or not obj['id'] or obj['id'] in seen:
            raise ValueError('unique nonempty detector ID required')
        seen.add(obj['id']);role=PortOwnerKind(obj['role'])
        kind=(NodeKind if role is PortOwnerKind.NODE else ContainerKind)(obj['semantic_kind'])
        b=obj['bbox_xyxy'];confidence=obj['confidence']
        if len(b)!=4 or not all(math.isfinite(v) for v in b) or not (0<=b[0]<b[2]<=w and 0<=b[1]<b[3]<=h):
            raise ValueError('positive bbox within original RGB required')
        if not math.isfinite(confidence) or not 0<=confidence<=1:
            raise ValueError('bounded detector confidence required')
        shapes.append(EmitShapePrimitive(obj['id'],role,kind,BBox(*b),confidence,
            source='rgb_detector_prediction',provenance=('research:detector_input','geometry:unchanged')))
    return EmitScene(ImageSize(w,h),shapes=tuple(shapes),source='research:rgb_source_evidence')


def reconstruct(rgb,objects,output,*,engine=None):
    """Create editable native PPT, returning full image-derived stage evidence.

    The caller runs the detector and supplies bound objects; this function never
    loads saved scene predictions, annotations, ground-truth text, or a source PPT.
    """
    prediction=detector_scene(rgb,objects)
    engine=_load_engine() if engine is None else engine
    labeled,initial_text=recover_labels(prediction,rgb,engine=engine)
    labeled,anchor_text=recover_text_only(labeled,rgb,engine)
    owners=[dict(id=s.id,bbox=[s.bbox.x0,s.bbox.y0,s.bbox.x1,s.bbox.y1]) for s in labeled.shapes if s.shape_kind is NodeKind.LABEL_ANCHOR]
    observations=observe(rgb,owners,engine)
    selected,owner_audit=apply_observations(labeled,rgb,observations)
    scene,_,trace=trace_with_centerlines(selected,rgb)
    scene,rays=add_source_rays(scene,rgb)
    scene,text=recover_spatial_text(scene,rgb,engine)
    normalized,scale=normalize_scene(scene)
    emitted,emission=write_label_anchor_native(normalized,output,styles=sample_shape_styles(rgb,scene))
    return dict(schema='research_source_evidence_pipeline_v1',source_size=[rgb.shape[1],rgb.shape[0]],
        source_scene=asdict(scene),prediction_scene=asdict(prediction),emitted_scene=asdict(emitted),normalization_scale=scale,
        initial_text_audit=initial_text,anchor_text_audit=anchor_text,spatial_ocr=observations,
        owner_audit=owner_audit,tracing_audit=trace,source_ray_audit=rays,spatial_text_audit=text,emission=emission,
        counts=dict(nodes=sum(s.owner_kind is PortOwnerKind.NODE for s in emitted.shapes),
            containers=sum(s.owner_kind is PortOwnerKind.CONTAINER for s in emitted.shapes),connectors=len(emitted.connectors),
            labels=sum(bool(s.label) for s in emitted.shapes),omitted_connectors=len(emission['rejected_connectors'])))
