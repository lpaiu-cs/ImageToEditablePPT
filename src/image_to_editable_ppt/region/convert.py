"""Production-facing region API. Explicit scope, safe outputs and observable abstention."""
from dataclasses import asdict
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import numpy as np
from PIL import Image
from image_to_editable_ppt.region.geometry import detect_scene,normalize_scene,validate_roi
from image_to_editable_ppt.region._selection_local import select_local
from image_to_editable_ppt.region.tracing import trace_scene
from image_to_editable_ppt.region.identity import filter_identity
from image_to_editable_ppt.region.text import recover_labels
from image_to_editable_ppt.region.emitter import write_native
from image_to_editable_ppt.v3.core.enums import PortOwnerKind
from image_to_editable_ppt.v3.emit import sample_shape_styles

LIMITATIONS=[
    'User-selected ROI; not automatic diagram-region recognition.',
    'Partial reconstruction; blank labels/omitted structures may require manual edits.',
    'OCR scale agreement is not proof of correctness.',
    'Explicit PowerPoint reroute can change attachment sites; movement does not prevent overlap.',
    'No independently validated human-time savings or general product-quality acceptance.'
]


def convert_region(input_path,output_path,*,region,recover_text=True,sample_style=True):
    """Write a new PPTX and <stem>.region.json; never overwrite either existing file.

    Regions are normalized to source pixels. Analysis is bounded to 4MP per ROI and
    16MP per source, and does not silently resize recognition. Output normalizes its
    longest side to 768 image units; coordinates/scale are recorded in the sidecar.
    No target annotation, training model or network access is required.
    """
    source=Path(input_path); output=Path(output_path)
    if output.suffix.lower()!='.pptx': raise ValueError('output must end with .pptx')
    report_path=output.with_suffix('.region.json')
    if output.exists() or report_path.exists(): raise FileExistsError('output or diagnostics already exists; choose a new output path')
    # Bind the evidence hash to the exact bytes decoded, even if input changes during OCR.
    with source.open('rb') as handle:
        source_bytes=handle.read(64*1024*1024+1)
    if len(source_bytes)>64*1024*1024: raise ValueError('input file exceeds 64 MiB')
    with Image.open(io.BytesIO(source_bytes)) as original:
        if original.width*original.height>16_000_000: raise ValueError('source exceeds 16 megapixels; crop or reduce it first')
        scope=validate_roi(region,original.size)
        if (scope[2]-scope[0])*(scope[3]-scope[1])>4_000_000: raise ValueError('region exceeds 4 megapixels; select a smaller region')
        if original.mode=='RGBA' or 'transparency' in original.info:
            rgba=original.convert('RGBA'); image=Image.new('RGBA',original.size,'white')
            image.alpha_composite(rgba); image=image.convert('RGB')
        else: image=original.convert('RGB')
    rgb=np.asarray(image)
    scene=detect_scene(rgb,region)
    if len(scene.shapes)>300: raise ValueError('region exceeds 300 geometry candidates; select a smaller region')
    selected,selection=select_local(scene,rgb,region,'combined')
    traced,trace,_=trace_scene(selected,rgb,region,transparent_gaps=True)
    labeled,text=recover_labels(traced,rgb,enabled=recover_text)
    final,identity=filter_identity(labeled,rgb,region)
    normalized,scale=normalize_scene(final)
    styles=sample_shape_styles(rgb,final) if sample_style else None
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.region-',dir=output.parent) as directory:
        temp=Path(directory)/'output.pptx'
        emitted,emission=write_native(normalized,temp,styles=styles)
        report=dict(schema='region_native_v1',mode='user_scoped_region',source_sha256=hashlib.sha256(source_bytes).hexdigest(),
            source_size=list(image.size),region=list(region),normalization_scale=scale,
            output_sha256=hashlib.sha256(temp.read_bytes()).hexdigest(),limitations=LIMITATIONS,
            source_scene=asdict(final),emitted_scene=asdict(emitted),
            selection=selection,tracing=trace,identity=identity,text=text,emission=emission)
        report['counts']=dict(nodes=sum(s.owner_kind is PortOwnerKind.NODE for s in emitted.shapes),
            containers=sum(s.owner_kind is PortOwnerKind.CONTAINER for s in emitted.shapes),
            connectors=len(emitted.connectors),labels=sum(bool(s.label) for s in emitted.shapes),
            omitted_connectors=len(emission['rejected_connectors']))
        report['status']='partial' if emitted.shapes else 'empty'
        report_temp=Path(directory)/'diagnostics.json'
        report_temp.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
        # Hard-link creation publishes fully written files and atomically refuses overwrite.
        # Keep both staged files until publication finishes; rollback only our own link.
        os.link(report_temp,report_path)
        try: os.link(temp,output)
        except Exception:
            if report_path.exists() and os.path.samefile(report_temp,report_path): report_path.unlink()
            raise
    return dict(family='user_scoped_region',**report['counts'],texts=report['counts']['nodes'],
        recognized_texts=report['counts']['labels'],output=str(output),diagnostics=str(report_path))
