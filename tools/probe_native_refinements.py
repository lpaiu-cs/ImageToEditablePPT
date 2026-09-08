"""Cached fresh scene replay for B/G diagnostics; NOT a fresh detector run."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image

from run_region_rgb_baseline import ROOT,digest,save
sys.path.insert(0,str(ROOT/'src'))
from image_to_editable_ppt.research.native_emit import load_scene
from image_to_editable_ppt.research.box_centerline_b_v1 import refine_box_centerlines
from image_to_editable_ppt.research.box_terminals import recover_box_terminals
from image_to_editable_ppt.research.closed_nodes import recover_closed_nodes
from image_to_editable_ppt.research.label_anchor_native import write_label_anchor_native
from image_to_editable_ppt.region.geometry import normalize_scene
from image_to_editable_ppt.v3.emit.style import sample_shape_styles


def run(source,output,box_centerlines,closed_nodes,box_terminals=False):
    if box_terminals and not box_centerlines:raise ValueError('terminal observation requires B verification')
    previous=json.loads((source/'results.json').read_text(encoding='utf-8'))
    if digest(source/'lock.json')!=previous['lock_sha256']:raise ValueError('input lock mismatch')
    output.mkdir(parents=True,exist_ok=False)
    for name in ('rgb','pptx','scene_inputs'):(output/name).mkdir()
    paths=[Path(__file__).resolve()]
    for name in ('research','v3/emit','region'):
        paths.extend((ROOT/'src/image_to_editable_ppt'/name).glob('*.py'))
    code={str(p.relative_to(ROOT)):digest(p) for p in paths}
    save(output/'lock.json',dict(source=str(source.resolve()),source_results_sha256=digest(source/'results.json'),
        code_sha256=code,box_centerlines=box_centerlines,closed_nodes=closed_nodes,box_terminals=box_terminals,
        mode='cached image-derived scene replay; not fresh inference',population='exposed synthetic validation 15'))
    records=[]
    for old in previous['records']:
        slot=old['slot'];image=source/'rgb'/f'{slot}.png'
        if digest(image)!=old['source_sha256'] or digest(source/'pptx'/f'{slot}.region.json')!=old['report_sha256']:
            raise ValueError('source artifact changed')
        rgb=np.asarray(Image.open(image))
        with (output/'rgb'/image.name).open('xb') as stream:stream.write(image.read_bytes())
        path=output/'scene_inputs'/f'{slot}.json';save(path,old['report']['source_scene'])
        scene=load_scene(path);box_audit=None;closed_audit=None;terminal_audit=None
        if box_centerlines:scene,box_audit=refine_box_centerlines(scene,rgb)
        if box_terminals:scene,terminal_audit=recover_box_terminals(scene,rgb,box_audit)
        styles=sample_shape_styles(rgb,scene)
        if closed_nodes:scene,styles,closed_audit=recover_closed_nodes(scene,rgb)
        normalized,scale=normalize_scene(scene)
        pptx=output/'pptx'/f'{slot}.pptx'
        emitted,emission=write_label_anchor_native(normalized,pptx,styles=styles)
        report=dict(old['report'],source_scene=asdict(scene),emitted_scene=asdict(emitted),normalization_scale=scale,
            box_centerline_audit=box_audit,closed_node_audit=closed_audit,box_terminal_audit=terminal_audit,emission=emission,
            counts=dict(nodes=sum(s.owner_kind.value=='node' for s in emitted.shapes),containers=sum(s.owner_kind.value=='container' for s in emitted.shapes),
                connectors=len(emitted.connectors),labels=sum(bool(s.label) for s in emitted.shapes),omitted_connectors=len(emission['rejected_connectors'])))
        save(pptx.with_suffix('.region.json'),report)
        records.append(dict(id=old['id'],slot=slot,source_sha256=old['source_sha256'],returncode=0,report=report,
            report_sha256=digest(pptx.with_suffix('.region.json')),pptx_sha256=digest(pptx),io=dict(mode='cached scene diagnostic; no OS/read sandbox claim')))
        print(slot,report['counts'],flush=True)
    if any(digest(ROOT/p)!=sha for p,sha in code.items()):raise ValueError('runtime changed')
    save(output/'results.json',dict(mode='cached B/G refinement diagnostic',lock_sha256=digest(output/'lock.json'),records=records))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--box-centerlines',action='store_true');p.add_argument('--closed-nodes',action='store_true')
    p.add_argument('--box-terminals',action='store_true')
    a=p.parse_args();run(a.source,a.output,a.box_centerlines,a.closed_nodes,a.box_terminals)
