"""Source-only P arm: closed box proposals and spatially consistent OCR."""
import argparse
from dataclasses import asdict
from pathlib import Path
import sys

import cv2
import numpy as np
from PIL import Image

from run_region_rgb_baseline import ROOT,digest,save
sys.path.insert(0,str(ROOT/'src'))
from image_to_editable_ppt.research.closed_rect_proposals import propose,observe_text
from image_to_editable_ppt.research.closed_owner_regions import closed_regions,owner_region,place_owned_text
from image_to_editable_ppt.research.source_evidence_pipeline import detector_scene
from image_to_editable_ppt.research.label_anchor_native import write_label_anchor_native
from image_to_editable_ppt.region.geometry import normalize_scene
from image_to_editable_ppt.v3.text.ocr import _load_engine
from image_to_editable_ppt.v3.emit.style import ShapeVisualStyle
from dataclasses import replace


def run(image,output,trace=False,inner_boundaries=False):
    image=image.resolve();output=output.resolve();output.mkdir(parents=True,exist_ok=False)
    with Image.open(image) as im:
        if im.mode!='RGB':raise ValueError('RGB required')
        rgb=np.asarray(im)
    source=digest(image)
    files=[Path(__file__).resolve(),ROOT/'docs/r10_closed_rectangle_proposal_spec.md']
    for directory in ('research','region','v3/emit','v3/core','v3/text'):
        files.extend((ROOT/'src/image_to_editable_ppt'/directory).glob('*.py'))
    code={str(f):digest(f) for f in files}
    import rapidocr_onnxruntime
    models={str(f):digest(f) for f in (Path(rapidocr_onnxruntime.__file__).parent/'models').glob('*.onnx')}
    save(output/'lock.json',dict(source_path=str(image),source_sha256=source,code_sha256=code,ocr_models_sha256=models,
        trace=trace,inner_boundaries=inner_boundaries,population='previously exposed original complex development image; not unseen acceptance',mode='RGB-only closed rectangle proposal, no detector or GT'))
    candidates,proposal_audit=propose(rgb,inner_boundaries=inner_boundaries);engine=_load_engine();objects=[];styles={};text_audit={};region_audit={}
    regions=closed_regions(rgb)
    for i,c in enumerate(candidates):
        identity=f'closed:{i}';box=c['bbox']
        objects.append(dict(id=identity,role='node',semantic_kind='box',bbox_xyxy=box,confidence=.9))
        own,excluded,fill,ownership=owner_region(rgb,c,regions);region_audit[identity]=ownership
        label,audit=observe_text(rgb,box,engine,excluded=excluded);text_audit[identity]=dict(label=label,**audit)
        # White is an observed fill, not transparency: otherwise a colored
        # parent's fill leaks through the child's native PowerPoint shape.
        styles[identity]=ShapeVisualStyle(fill=fill,stroke=(71,85,105))
    scene=detector_scene(rgb,objects)
    scene=replace(scene,source='research:closed_rgb_rectangles',shapes=tuple(replace(s,label=text_audit[s.id]['label'],
        source='raw_closed_rectangle_proposal',provenance=('r10:two_canny_closed_contours','r10:stable_prefix_ocr')) for s in scene.shapes))
    trace_audit=None;box_audit=None;terminal_audit=None
    if trace:
        from image_to_editable_ppt.research.source_centerline_v2 import trace_with_centerlines
        from image_to_editable_ppt.research.box_centerline_b_v1 import refine_box_centerlines
        from image_to_editable_ppt.research.box_terminals import recover_box_terminals
        scene,_,trace_audit=trace_with_centerlines(scene,rgb)
        scene,box_audit=refine_box_centerlines(scene,rgb)
        scene,terminal_audit=recover_box_terminals(scene,rgb,box_audit)
    normalized,scale=normalize_scene(scene);pptx=output/'result.pptx'
    emitted,emission=write_label_anchor_native(normalized,pptx,styles=styles)
    placement=place_owned_text(pptx,scene,text_audit,scale)
    save(output/'result.json',dict(source_sha256=source,source_scene=asdict(scene),emitted_scene=asdict(emitted),styles={k:asdict(v) for k,v in styles.items()},
        proposal_audit=proposal_audit,text_audit=text_audit,region_audit=region_audit,text_placement=placement,tracing_audit=trace_audit,box_audit=box_audit,terminal_audit=terminal_audit,
        emission=emission,pptx_sha256=digest(pptx),nodes=len(scene.shapes),labels=sum(bool(s.label) for s in scene.shapes),
        provenance='direct RGB-only research execution; no cached detector/scene/GT inputs; Python IO not sandboxed'))
    if digest(image)!=source or any(digest(p)!=sha for p,sha in code.items()):raise ValueError('source/runtime changed during execution')
    print(len(scene.shapes),'nodes',[(s.id,s.label) for s in scene.shapes],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--image',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--trace',action='store_true')
    p.add_argument('--inner-boundaries',action='store_true')
    a=p.parse_args();run(a.image,a.output,a.trace,a.inner_boundaries)
