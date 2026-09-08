"""Verify a fresh RGB detector execution and reconstruct native PPT from it."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from run_region_rgb_baseline import ROOT,digest,save
sys.path.insert(0,str(ROOT/'src'))


def verified_inputs(handoff_path):
    from image_to_editable_ppt.research.prediction_handoff import digest as canonical_digest,LEGACY_ADAPTER,CLASS_ENTRIES,SETTINGS
    handoff=json.loads(handoff_path.read_text(encoding='utf-8'))
    payload=handoff['payload']
    if canonical_digest(payload)!=handoff['payload_sha256'] or payload['schema']!='fresh_rgb_detector_handoff_v1':
        raise ValueError('fresh detector handoff signature/schema mismatch')
    if payload['execution_attested'] is not True or payload['research_only'] is not True:
        raise ValueError('fresh execution research contract required')
    loaded={}
    if set(payload['artifacts'])!={'predictions.json','execution-lock.json','execution.json','reads.json'}:
        raise ValueError('exact fresh execution artifacts required')
    for name,ref in payload['artifacts'].items():
        path=Path(ref['path'])
        if path.name!=name or digest(path)!=ref['sha256']:
            raise ValueError('fresh execution artifact SHA mismatch: '+name)
        loaded[name]=json.loads(path.read_text(encoding='utf-8'))
    pred=loaded['predictions.json'];lock=loaded['execution-lock.json'];execution=loaded['execution.json']
    if execution['status']!='complete' or execution['denied_reads'] or any(not r['allowed'] for r in loaded['reads.json']['events']):
        raise ValueError('fresh execution did not finish within its read contract')
    if pred['schema']!='fresh_rgb_detector_predictions_v1' or pred['execution_attested'] is not True:
        raise ValueError('not fresh predictions')
    if pred['label_adapter']!=LEGACY_ADAPTER or lock['class_map']!=LEGACY_ADAPTER or payload['class_map']!=LEGACY_ADAPTER:
        raise ValueError('explicit legacy class map differs')
    if pred['run_git_commit']!=payload['run_git_commit'] or pred['run_git_commit']!=lock['git_commit']:
        raise ValueError('inference Git attestation mismatch')
    if pred['inference_code']!=lock['code_sha256']:
        raise ValueError('inference code lock mismatch')
    for path,sha in lock['code_sha256'].items():
        if digest(path)!=sha:raise ValueError('inference source changed: '+path)
    if digest(lock['checkpoint']['path'])!=lock['checkpoint']['sha256'] or pred['checkpoint_sha256']!=lock['checkpoint']['sha256'] or payload['checkpoint_sha256']!=lock['checkpoint']['sha256']:
        raise ValueError('checkpoint identity mismatch')
    if pred['inputs_sha256']!=lock['inputs_sha256']:
        raise ValueError('RGB input manifest identity mismatch')
    rows=lock['inputs'];by_id={r['id']:r for r in rows}
    if not rows or any(set(r)!={'id','image','image_sha256'} for r in rows):
        raise ValueError('RGB-only input rows required')
    if len(by_id)!=len(rows) or len(pred['predictions'])!=len(rows) or len(rows)!=payload['sample_count'] or execution['samples']!=len(rows):
        raise ValueError('input sample identity mismatch')
    raw_count=sum(len(p['source_labels']) for p in pred['predictions'])
    if raw_count!=payload['raw_object_count'] or raw_count!=execution['raw_objects']:
        raise ValueError('raw detection count mismatch')
    import torch
    from image_to_editable_ppt.ml.detection_postprocess import select_detection_indices
    from image_to_editable_ppt.research.source_evidence_pipeline import detector_scene
    from PIL import Image
    import numpy as np
    semantics={e['raw_label']:e for e in CLASS_ENTRIES[1:]}
    samples=[];seen=set()
    for raw in pred['predictions']:
        if raw['id'] in seen:raise ValueError('duplicate prediction image')
        seen.add(raw['id']);row=by_id[raw['id']]
        image=Path(row['image'])
        if digest(image)!=row['image_sha256'] or raw['source_sha256']!=row['image_sha256']:
            raise ValueError('original RGB SHA mismatch')
        with Image.open(image) as im:
            if im.mode!='RGB' or list(im.size)!=raw['image_size']:raise ValueError('RGB geometry mismatch')
            rgb=np.asarray(im)
        if raw['coordinate_system']!='original_image_pixels':raise ValueError('coordinate mismatch')
        p=raw['prediction'];objects=[]
        if not len(p['boxes'])==len(p['scores'])==len(p['labels'])==len(raw['source_labels']):
            raise ValueError('detection field lengths differ')
        for i,(box,score,label,source_label) in enumerate(zip(p['boxes'],p['scores'],p['labels'],raw['source_labels'],strict=True)):
            if label!=LEGACY_ADAPTER.get(str(source_label)):raise ValueError('raw/current class mismatch')
            e=semantics[label]
            objects.append(dict(id=f"rgb-{row['image_sha256']}:det:{i}",role=e['role'],semantic_kind=e['semantic_kind'],bbox_xyxy=box,confidence=score))
        detector_scene(rgb,objects)  # Validate every raw object before score/NMS selection.
        tensor=dict(boxes=torch.tensor(p['boxes'],dtype=torch.float32).reshape(-1,4),scores=torch.tensor(p['scores']),labels=torch.tensor(p['labels']))
        selected=select_detection_indices(tensor,**SETTINGS)
        samples.append(dict(id=row['id'],image=str(image),source_sha256=row['image_sha256'],objects=[objects[i] for i in selected]))
    return samples,dict(handoff_sha256=digest(handoff_path),execution=payload,inference_lock=lock,
        postprocess=SETTINGS,postprocess_sha256=digest(ROOT/'src/image_to_editable_ppt/ml/detection_postprocess.py'))


def worker(image,output):
    import cv2
    import numpy as np
    import numpy.ma
    from PIL import Image
    from image_to_editable_ppt.research.source_evidence_pipeline import reconstruct
    from image_to_editable_ppt.research.image_only_guard import install_guard
    cv2.setNumThreads(1)
    reads,denied=install_guard(image,output.parent,ROOT/'src')
    request=json.loads(sys.stdin.read())
    if set(request)!={'source_sha256','objects','closed_nodes'} or type(request['closed_nodes']) is not bool or digest(image)!=request['source_sha256']:
        raise ValueError('RGB/detection-only request required')
    with Image.open(image) as im:
        if im.mode!='RGB':raise ValueError('RGB mode required')
        rgb=np.asarray(im)
    report=reconstruct(rgb,request['objects'],output,closed_nodes=request['closed_nodes'])
    report['source_sha256']=request['source_sha256']
    save(output.with_suffix('.region.json'),report)
    save(output.with_suffix('.io.json'),dict(python_read_paths=sorted(reads),denied_paths=denied,boundary='Python audit hook, not an OS sandbox'))
    print(json.dumps(report['counts']))


def run(handoff,out,*,closed_nodes=False):
    samples,provenance=verified_inputs(handoff)
    out.mkdir(parents=True,exist_ok=False);(out/'rgb').mkdir();(out/'pptx').mkdir()
    paths=[Path(__file__).resolve(),ROOT/'docs/r10_fresh_rgb_pipeline_spec.md']
    for directory in ('region','research','v3/emit','v3/core','v3/text'):
        paths.extend((ROOT/'src/image_to_editable_ppt'/directory).glob('*.py'))
    code={str(p.relative_to(ROOT)):digest(p) for p in paths}
    import rapidocr_onnxruntime
    models={str(p):digest(p) for p in (Path(rapidocr_onnxruntime.__file__).parent/'models').glob('*.onnx')}
    save(out/'lock.json',dict(provenance=provenance,code_sha256=code,models_sha256=models,
        mode='fresh_detector_to_native',closed_nodes=closed_nodes,population=provenance['inference_lock'].get('population','previously exposed synthetic validation; not unseen acceptance')))
    records=[]
    for index,sample in enumerate(samples):
        slot=f'{index:03d}';image=out/'rgb'/f'{slot}.png';output=out/'pptx'/f'{slot}.pptx'
        data=Path(sample['image']).read_bytes()
        if hashlib.sha256(data).hexdigest()!=sample['source_sha256']:raise ValueError('RGB changed')
        with image.open('xb') as stream:stream.write(data)
        request=dict(source_sha256=sample['source_sha256'],objects=sample['objects'],closed_nodes=closed_nodes)
        env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
        p=subprocess.run([sys.executable,str(Path(__file__).resolve()),'worker','--image',str(image.resolve()),'--output',str(output.resolve())],
            input=json.dumps(request),capture_output=True,text=True,encoding='utf-8',errors='replace',cwd=ROOT,env=env,timeout=240)
        row=dict(id=sample['id'],slot=slot,source_sha256=sample['source_sha256'],returncode=p.returncode,stdout=p.stdout,stderr=p.stderr)
        if p.returncode==0:
            row.update(report=json.loads(output.with_suffix('.region.json').read_text(encoding='utf-8')),report_sha256=digest(output.with_suffix('.region.json')),
                pptx_sha256=digest(output),io=json.loads(output.with_suffix('.io.json').read_text(encoding='utf-8')))
        records.append(row);print(slot,row.get('report',{}).get('counts',p.stderr[-1000:]),flush=True)
    assert all(digest(ROOT/p)==sha for p,sha in code.items())
    save(out/'results.json',dict(mode='fresh RGB detector + source evidence native',lock_sha256=digest(out/'lock.json'),records=records))
    if any(r['returncode'] for r in records):raise RuntimeError('native reconstruction worker failed')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['run','worker']);p.add_argument('--handoff',type=Path)
    p.add_argument('--closed-nodes',action='store_true')
    p.add_argument('--image',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.mode=='worker':worker(a.image,a.output)
    else:run(a.handoff,a.output,closed_nodes=a.closed_nodes)
