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
from image_to_editable_ppt.research.closed_rect_proposals import propose,propose_union,observe_text
from image_to_editable_ppt.research.closed_owner_regions import closed_regions,owner_region,place_owned_text
from image_to_editable_ppt.research.closed_content_gate import inspect_content,admitted_ids
from image_to_editable_ppt.research.source_text_rows import observe_rows
from image_to_editable_ppt.research.source_texture_guard import inspect_texture
from image_to_editable_ppt.research.owned_text_consensus import observe_owned_label
from image_to_editable_ppt.research.source_evidence_pipeline import detector_scene
from image_to_editable_ppt.research.label_anchor_native import write_label_anchor_native
from image_to_editable_ppt.region.geometry import normalize_scene
from image_to_editable_ppt.v3.text.ocr import _load_engine
from image_to_editable_ppt.v3.emit.style import ShapeVisualStyle
from dataclasses import replace


def run(image,output,trace=False,inner_boundaries=False,content_gate=False,whole_lines=False,source_rows=False,dark_boundaries=False,portrait_boxes=False,boundary_union=False,texture_guard=False,owned_text=False,nested_owners=False,pixel_agreement=False,portrait_text=False):
    if source_rows and whole_lines:raise ValueError('source-rows and whole-lines are separate experiment arms')
    if boundary_union and (inner_boundaries or dark_boundaries):raise ValueError('boundary-union fixes both component proposal contracts')
    if texture_guard and content_gate:raise ValueError('texture and flat-content gates are separate experiments')
    if owned_text and (source_rows or whole_lines):raise ValueError('owned-text fixes both OCR observation contracts')
    if portrait_text and not owned_text:raise ValueError('portrait-text requires owned-text')
    image=image.resolve();output=output.resolve();output.mkdir(parents=True,exist_ok=False)
    with Image.open(image) as im:
        if im.mode!='RGB':raise ValueError('RGB required')
        rgb=np.asarray(im)
    source=digest(image)
    files=[Path(__file__).resolve(),ROOT/'docs/r10_closed_rectangle_proposal_spec.md',
        ROOT/'docs/r10_owned_rectangle_spec.md',ROOT/'docs/r10_closed_content_gate_spec.md',ROOT/'docs/r10_source_texture_spec.md',ROOT/'docs/r10_nested_owner_spec.md',ROOT/'docs/r10_pixel_cell_boundary_spec.md',ROOT/'docs/r10_portrait_text_spec.md']
    for directory in ('research','region','v3/emit','v3/core','v3/text'):
        files.extend((ROOT/'src/image_to_editable_ppt'/directory).glob('*.py'))
    code={str(f):digest(f) for f in files}
    import rapidocr_onnxruntime
    models={str(f):digest(f) for f in (Path(rapidocr_onnxruntime.__file__).parent/'models').glob('*.onnx')}
    font=Path('C:/Windows/Fonts/arial.ttf');code[str(font)]=digest(font)
    save(output/'lock.json',dict(source_path=str(image),source_sha256=source,code_sha256=code,ocr_models_sha256=models,
        trace=trace,inner_boundaries=inner_boundaries,content_gate=content_gate,whole_lines=whole_lines,source_rows=source_rows,dark_boundaries=dark_boundaries,portrait_boxes=portrait_boxes,boundary_union=boundary_union,texture_guard=texture_guard,owned_text=owned_text,nested_owners=nested_owners,pixel_agreement=pixel_agreement,portrait_text=portrait_text,population='research RGB input; exposure status is recorded separately by the caller, not inferred by runtime',mode='RGB-only closed rectangle proposal, no detector or GT'))
    candidates,proposal_audit=propose_union(rgb,portrait_boxes=portrait_boxes,pixel_agreement=pixel_agreement) if boundary_union else propose(rgb,inner_boundaries=inner_boundaries,dark_boundaries=dark_boundaries,portrait_boxes=portrait_boxes,pixel_agreement=pixel_agreement)
    engine=_load_engine();objects=[];styles={};text_audit={};region_audit={};content_audit={}
    regions=closed_regions(rgb)
    if nested_owners:
        from image_to_editable_ppt.research.nested_owner_evidence import exclusion_regions
        regions=exclusion_regions(regions,candidates)
    for i,c in enumerate(candidates):
        identity=f'closed:{i}';box=c['bbox']
        objects.append(dict(id=identity,role='node',semantic_kind='box',bbox_xyxy=box,confidence=.9))
        own,excluded,fill,ownership=owner_region(rgb,c,regions);region_audit[identity]=ownership
        if owned_text:label,audit=observe_owned_label(rgb,c,own,excluded,engine,portrait_text=portrait_text)
        elif source_rows:label,audit=observe_rows(rgb,c,own,engine)
        else:label,audit=observe_text(rgb,box,engine,excluded=excluded,whole_lines=whole_lines)
        text_audit[identity]=dict(label=label,**audit)
        content_audit[identity]=inspect_texture(rgb,c,text_audit[identity]) if texture_guard else inspect_content(rgb,c,own,text_audit[identity])
        # White is an observed fill, not transparency: otherwise a colored
        # parent's fill leaks through the child's native PowerPoint shape.
        styles[identity]=ShapeVisualStyle(fill=fill,stroke=(71,85,105))
    scene=detector_scene(rgb,objects)
    scene=replace(scene,source='research:closed_rgb_rectangles',shapes=tuple(replace(s,label=text_audit[s.id]['label'],
        source='raw_closed_rectangle_proposal',provenance=('r10:two_source_threshold_closed_contours','r10:stable_prefix_ocr')) for s in scene.shapes))
    trace_audit=None;box_audit=None;terminal_audit=None;nested_audit=None
    if trace and nested_owners:
        from image_to_editable_ppt.research.nested_owner_evidence import trace_nested
        scene,trace_audit,box_audit,terminal_audit,nested_audit=trace_nested(scene,rgb)
    elif trace:
        from image_to_editable_ppt.research.source_centerline_v2 import trace_with_centerlines
        from image_to_editable_ppt.research.box_centerline_b_v1 import refine_box_centerlines
        from image_to_editable_ppt.research.box_terminals import recover_box_terminals
        scene,_,trace_audit=trace_with_centerlines(scene,rgb)
        scene,box_audit=refine_box_centerlines(scene,rgb)
        scene,terminal_audit=recover_box_terminals(scene,rgb,box_audit)
    proposed_scene=scene
    if content_gate or texture_guard:
        keep=admitted_ids(scene,content_audit)
        scene=replace(scene,shapes=tuple(s for s in scene.shapes if s.id in keep),
            connectors=tuple(c for c in scene.connectors if c.source_owner_id in keep and c.target_owner_id in keep))
    normalized,scale=normalize_scene(scene);pptx=output/'result.pptx'
    emitted,emission=write_label_anchor_native(normalized,pptx,styles=styles)
    if content_gate or texture_guard:
        keep=admitted_ids(emitted,content_audit)
        if keep!={s.id for s in emitted.shapes}:
            scene=replace(scene,shapes=tuple(s for s in scene.shapes if s.id in keep),
                connectors=tuple(c for c in scene.connectors if c.source_owner_id in keep and c.target_owner_id in keep))
            normalized,scale=normalize_scene(scene)
            emitted,emission=write_label_anchor_native(normalized,pptx,styles=styles)
    placement=place_owned_text(pptx,scene,text_audit,scale)
    save(output/'result.json',dict(source_sha256=source,source_scene=asdict(scene),emitted_scene=asdict(emitted),styles={k:asdict(v) for k,v in styles.items()},
        proposal_audit=proposal_audit,text_audit=text_audit,region_audit=region_audit,content_audit=content_audit,proposed_scene=asdict(proposed_scene),text_placement=placement,tracing_audit=trace_audit,box_audit=box_audit,terminal_audit=terminal_audit,nested_audit=nested_audit,
        emission=emission,pptx_sha256=digest(pptx),nodes=len(scene.shapes),labels=sum(bool(s.label) for s in scene.shapes),
        provenance='direct RGB-only research execution; no cached detector/scene/GT inputs; Python IO not sandboxed'))
    if digest(image)!=source or any(digest(p)!=sha for p,sha in code.items()):raise ValueError('source/runtime changed during execution')
    print(len(scene.shapes),'nodes',[(s.id,s.label) for s in scene.shapes],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--image',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--trace',action='store_true')
    p.add_argument('--inner-boundaries',action='store_true')
    p.add_argument('--content-gate',action='store_true')
    p.add_argument('--whole-lines',action='store_true')
    p.add_argument('--source-rows',action='store_true')
    p.add_argument('--dark-boundaries',action='store_true')
    p.add_argument('--portrait-boxes',action='store_true')
    p.add_argument('--boundary-union',action='store_true')
    p.add_argument('--texture-guard',action='store_true')
    p.add_argument('--owned-text',action='store_true')
    p.add_argument('--nested-owners',action='store_true')
    p.add_argument('--pixel-agreement',action='store_true')
    p.add_argument('--portrait-text',action='store_true')
    a=p.parse_args();run(a.image,a.output,a.trace,a.inner_boundaries,a.content_gate,a.whole_lines,a.source_rows,a.dark_boundaries,a.portrait_boxes,a.boundary_union,a.texture_guard,a.owned_text,a.nested_owners,a.pixel_agreement,a.portrait_text)
