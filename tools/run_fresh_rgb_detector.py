"""Fresh, attested RGB-only detector forward pass; no prediction cache or GT."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def write(path,value):
    with Path(path).open('x',encoding='utf-8') as f:
        json.dump(value,f,indent=2,ensure_ascii=False,allow_nan=False)


def main():
    p=argparse.ArgumentParser();p.add_argument('--inputs',type=Path,required=True)
    p.add_argument('--checkpoint',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();a.out=a.out.resolve();a.inputs=a.inputs.resolve();a.checkpoint=a.checkpoint.resolve()
    a.out.mkdir(parents=True,exist_ok=False)
    import numpy as np
    import numpy.ma
    import torch
    import torchvision
    import lightning
    from PIL import Image
    from image_to_editable_ppt.ml.lightning_module import DetectorLightningModule
    from image_to_editable_ppt.ml.dataset import to_rgb_chw_tensor,label_to_kind
    Image.init();torch.set_num_threads(8);torch.manual_seed(1303)
    inputs=json.loads(a.inputs.read_text())
    if len(inputs)!=15 or any(set(r)!={'id','image','image_sha256'} for r in inputs):
        raise ValueError('Exactly the 15 locked RGB entries required')
    if len({r['id'] for r in inputs})!=15:raise ValueError('Duplicate image ID')
    adapter={1:1,2:2,3:4,4:5,5:6,6:7}
    names=['box','rounded_box','section','label_anchor','flow_cluster','panel']
    assert [str(label_to_kind(adapter[i])) for i in range(1,7)]==names
    code_paths={Path(__file__).resolve()}
    for name,module in list(sys.modules.items()):
        if name.startswith('image_to_editable_ppt') and getattr(module,'__file__',None):
            path=Path(module.__file__).resolve()
            if not path.is_relative_to(ROOT/'src'):raise RuntimeError('Wrong checkout import: '+str(path))
            code_paths.add(path)
    code_hashes={str(path):sha(path) for path in sorted(code_paths)}
    git=subprocess.run(['rtk','proxy','git','rev-parse','HEAD'],cwd=ROOT,capture_output=True,text=True,check=True).stdout.strip()
    # Warm constructor before read restriction; weights=None means no download.
    model=DetectorLightningModule(num_classes=7,learning_rate=.0003).eval()
    lock=dict(schema='fresh_rgb_detector_execution_v1',git_commit=git,code_sha256=code_hashes,
        checkpoint=dict(path=str(a.checkpoint),sha256=sha(a.checkpoint)),inputs_sha256=sha(a.inputs),
        inputs=inputs,class_map=adapter,class_names=names,class_map_provenance='legacy_inferred_from_a00d61c_enum_and_3ae7caf_insertion',
        limitations=['Training checkpoint does not attest its class names or training code SHA.',
                    'These 15 validation images were previously exposed; not an unseen holdout.'],
        environment=dict(python=sys.version,torch=torch.__version__,torchvision=torchvision.__version__,
                         lightning=lightning.__version__,numpy=np.__version__,pillow=Image.__version__,device='cpu',threads=8),
        inference=dict(checkpoint_load='torch.load(weights_only=True), strict state_dict',batch_size=1,model_eval=True,
                       cache=False,preprocessing='current to_rgb_chw_tensor, full original RGB',postprocess='torchvision model defaults only'))
    write(a.out/'execution-lock.json',lock)
    allowed={a.checkpoint,a.inputs,*code_paths,*(Path(r['image']).resolve() for r in inputs)}
    outputs={a.out/'predictions.json',a.out/'execution.json',a.out/'reads.json'}
    events=[]
    def guard(event,values):
        if event!='open' or not isinstance(values[0],(str,bytes)):return
        path=Path(os.fsdecode(values[0])).resolve();mode=values[1];flags=values[2]
        writing=(isinstance(mode,str) and any(c in mode for c in 'wax+')) or bool(flags & (os.O_WRONLY|os.O_RDWR))
        permitted=path in (outputs if writing else allowed)
        events.append(dict(path=str(path),mode=str(mode),allowed=permitted))
        if not permitted:raise PermissionError('Fresh inference allowlist denied: '+str(path))
    sys.addaudithook(guard)
    started=time.monotonic()
    try:
        checkpoint=torch.load(a.checkpoint,map_location='cpu',weights_only=True)
        if checkpoint['hyper_parameters']['num_classes']!=7:raise ValueError('Checkpoint schema changed')
        model.load_state_dict(checkpoint['state_dict'],strict=True);model.eval()
        predictions=[]
        with torch.inference_mode():
            for row in inputs:
                if sha(row['image'])!=row['image_sha256']:raise ValueError('RGB SHA changed')
                with Image.open(row['image']) as im:tensor=to_rgb_chw_tensor(np.asarray(im.convert('RGB')))
                result=model([tensor])[0]
                source_labels=result['labels'].tolist()
                labels=torch.tensor([adapter[int(v)] for v in source_labels],dtype=torch.int64)
                predictions.append(dict(id=row['id'],source_sha256=row['image_sha256'],image_size=[tensor.shape[2],tensor.shape[1]],
                    coordinate_system='original_image_pixels',source_labels=source_labels,
                    prediction=dict(boxes=result['boxes'].tolist(),labels=labels.tolist(),scores=result['scores'].tolist())))
                print(row['id'],len(source_labels),flush=True)
        for path,digest in code_hashes.items():
            if sha(path)!=digest:raise RuntimeError('Execution code changed during run')
        if sha(a.checkpoint)!=lock['checkpoint']['sha256']:raise RuntimeError('Weights changed during run')
        result=dict(schema='fresh_rgb_detector_predictions_v1',checkpoint_sha256=lock['checkpoint']['sha256'],
            inputs_sha256=lock['inputs_sha256'],label_adapter=adapter,seconds=time.monotonic()-started,
            inference_code=lock['code_sha256'],run_git_commit=git,execution_attested=True,predictions=predictions)
        write(a.out/'predictions.json',result)
        write(a.out/'execution.json',dict(status='complete',samples=len(predictions),raw_objects=sum(len(r['source_labels']) for r in predictions),
              elapsed_seconds=result['seconds'],denied_reads=sum(not e['allowed'] for e in events)))
    except Exception as error:
        write(a.out/'execution.json',dict(status='failed',error=repr(error)));raise
    finally:write(a.out/'reads.json',dict(scope='Python file opens after imports/model construction, before checkpoint loading and all forward passes',events=list(events)))


if __name__=='__main__':main()
