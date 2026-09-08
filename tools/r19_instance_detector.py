"""GPU instance experiment with fixed final checkpoint and calibration-before-eval."""
import argparse
import json
from pathlib import Path
import random
import sys
import time
import numpy as np
from PIL import Image,ImageDraw
import torch
import torchvision
from run_region_rgb_baseline import ROOT,digest,save
from r17_object_primitive import verify
from r18_candidate_validity import geometry
from r16_primitive_pretraining import summary
from image_to_editable_ppt.research.instance_detector import new_model,image_tensor,target,decode
from image_to_editable_ppt.research.ppt_primitive_learning import object_counts,select_threshold,write_shapes


def environment():
    if not torch.cuda.is_available():raise RuntimeError('R19 requires actual CUDA, not CPU fallback')
    torch.set_num_threads(4);torch.set_float32_matmul_precision('high');torch.manual_seed(1901)
    return dict(python=sys.version,torch=str(torch.__version__),torchvision=str(torchvision.__version__),
        cuda=torch.version.cuda,gpu=torch.cuda.get_device_name(0),capability=torch.cuda.get_device_capability(0))


def code_lock():
    paths=['tools/r19_instance_detector.py','docs/r19_instance_detector_spec.md',
        'src/image_to_editable_ppt/research/instance_detector.py','src/image_to_editable_ppt/research/ppt_primitive_learning.py',
        'src/image_to_editable_ppt/research/closed_rect_proposals.py','tools/r18_candidate_validity.py',
        'tools/r17_object_primitive.py','tools/r16_primitive_pretraining.py','tools/run_region_rgb_baseline.py']
    return {str(ROOT/p):digest(ROOT/p) for p in paths}


def read_rgb(path):
    with Image.open(path) as im:
        if im.mode!='RGB':raise ValueError('Original RGB required')
        return np.array(im)


def observe(model,path):
    image=read_rgb(path);size=(image.shape[1],image.shape[0])
    model.eval()
    with torch.inference_mode():prediction=model([image_tensor(image).cuda()])[0]
    return decode(prediction,size,.05),size


def board(path,objects,destination):
    im=Image.fromarray(read_rgb(path));draw=ImageDraw.Draw(im)
    for o in objects:
        draw.rectangle(o['bbox'],outline='red',width=2)
        draw.text(o['bbox'][:2],f'k{o["kind"]} {o["confidence"]:.2f}',fill='red')
    im.save(destination)


def representative(rows):
    return [next(r for r in rows if r['family']==f) for f in sorted({r['family'] for r in rows})]


def train(manifest,output,control=False,control_run=None):
    output.mkdir(parents=True,exist_ok=False);env=environment();records=json.loads(manifest.read_text())['records']
    rows=[r for r in records if r['split']=='train']
    if control:rows=representative(rows);assert len(rows)==5
    else:
        if len(rows)!=288:raise ValueError('R19 train population must be 288')
        if control_run is None:raise ValueError('Successful control run required')
        control_log=json.loads((control_run/'training.json').read_text())
        assert control_log['control'] and control_log['control_gate']
        verify(json.loads((control_run/'lock.json').read_text()))
    steps,batch=(100,2) if control else (1800,4)
    lock=dict(files={**code_lock(),str(manifest.resolve()):digest(manifest),**{r['image']:digest(r['image']) for r in rows}},
        environment=env,manifest=str(manifest.resolve()),control=control,steps=steps,batch=batch,seed=1901,
        learning_rate=.0003,weight_decay=.0001,lr_drop_step=None if control else 1200)
    if control_run:
        lock['files'].update({str((control_run/n).resolve()):digest(control_run/n) for n in ('training.json','lock.json')})
    for r in rows:assert lock['files'][r['image']]==r['image_sha256']
    model=new_model(pretrained=True).cuda()
    backbone_path=Path(torch.hub.get_dir())/'checkpoints/resnet50-0676ba61.pth'
    lock['files'][str(backbone_path.resolve())]=digest(backbone_path);save(output/'lock.json',lock);verify(lock)
    cached=[]
    for r in rows:
        image=read_rgb(r['image']);cached.append((image_tensor(image),target(r['objects'],(image.shape[1],image.shape[0]))))
    optimizer=torch.optim.AdamW(model.parameters(),lr=.0003,weight_decay=.0001);rng=random.Random(1901)
    started=time.monotonic();losses=[];samples=representative(rows);snapshots=[]
    for step in range(1,steps+1):
        model.train();indices=[rng.randrange(len(cached)) for _ in range(batch)]
        images=[cached[i][0].cuda() for i in indices];targets=[{k:v.cuda() for k,v in cached[i][1].items()} for i in indices]
        optimizer.zero_grad(set_to_none=True);parts=model(images,targets);loss=sum(parts.values())
        if not torch.isfinite(loss):raise RuntimeError('Nonfinite training loss')
        loss.backward();optimizer.step();row=dict(step=step,loss=float(loss.detach()),parts={k:float(v.detach()) for k,v in parts.items()})
        losses.append(row)
        if step%25==0:print(json.dumps(dict(**row,seconds=round(time.monotonic()-started,1))),flush=True)
        if step in (100,600,1200,1800):
            folder=output/f'step-{step:04d}';folder.mkdir();checks=[]
            for r in samples:
                objects,size=observe(model,r['image']);kept=[o for o in objects if o['confidence']>=.5]
                board(r['image'],kept,folder/(r['id']+'.png'))
                checks.append(dict(id=r['id'],objects=kept,geometry=geometry(kept,r['objects']),**object_counts(kept,r['objects'])))
            snap=dict(step=step,rows=checks,strict=summary(checks),geometry=summary([r['geometry'] for r in checks]))
            save(folder/'checks.json',snap);snapshots.append(snap)
            print(json.dumps(dict(snapshot=step,strict=snap['strict'],geometry=snap['geometry'])),flush=True)
        if step==1200 and not control:
            for group in optimizer.param_groups:group['lr']=.0001
    verify(lock);torch.save(model.cpu().state_dict(),output/'final.pt')
    last=snapshots[-1];passed=last['geometry']['recall']>=.9 and last['strict']['recall']>=.8
    save(output/'training.json',dict(control=control,control_gate=passed if control else None,losses=losses,snapshots=snapshots,
        checkpoint_sha256=digest(output/'final.pt'),lock_sha256=digest(output/'lock.json'),seconds=time.monotonic()-started,
        peak_gpu_bytes=torch.cuda.max_memory_allocated()))
    print(json.dumps(dict(done=True,control_gate=passed,seconds=time.monotonic()-started)),flush=True)


def load_trained(trained):
    lock=json.loads((trained/'lock.json').read_text());verify(lock)
    run=json.loads((trained/'training.json').read_text());assert digest(trained/'final.pt')==run['checkpoint_sha256']
    model=new_model();model.load_state_dict(torch.load(trained/'final.pt',map_location='cpu',weights_only=True));return model.cuda().eval(),lock


def evaluate(manifest,trained,output):
    output.mkdir(parents=True,exist_ok=False);env=environment();model,prior=load_trained(trained)
    if prior['control']:raise ValueError('Control weights cannot be formally evaluated')
    assert prior['manifest']==str(manifest.resolve());records=json.loads(manifest.read_text())['records']
    assert len([r for r in records if r['split']=='calibration'])==len([r for r in records if r['split']=='eval'])==48
    lock=dict(files={**prior['files'],str((trained/'final.pt').resolve()):digest(trained/'final.pt'),
        **{r['image']:digest(r['image']) for r in records}},environment=env)
    for r in records:assert digest(r['image'])==r['image_sha256']
    save(output/'lock.json',lock);cal=[(r,*observe(model,r['image'])) for r in records if r['split']=='calibration']
    checks={str(t):summary([object_counts([o for o in obs if o['confidence']>=t],r['objects']) for r,obs,_ in cal]) for t in (.3,.5,.7,.85,.95,.99)}
    threshold,passed=select_threshold(checks);save(output/'calibration.json',dict(threshold=threshold,gate_pass=passed,checks=checks))
    rows=[]
    # Eval pixels are first consumed here, after the sole final-checkpoint calibration decision.
    for r in records:
        if r['split']!='eval':continue
        objects,size=observe(model,r['image']);kept=[o for o in objects if o['confidence']>=threshold]
        folder=output/'instance'/r['id'];folder.mkdir(parents=True);write_shapes(kept,size,folder/'result.pptx');board(r['image'],kept,folder/'inspection.png')
        rows.append(dict(id=r['id'],family=r['family'],stage=r['stage'],objects=kept,all_candidates=objects,
            **object_counts(kept,r['objects']),geometry=geometry(kept,r['objects']),coverage=geometry(objects,r['objects']),
            source_sha256=r['image_sha256'],pptx_sha256=digest(folder/'result.pptx')))
    by_family={f:summary([r for r in rows if r['family']==f]) for f in sorted({r['family'] for r in rows})}
    total=summary(rows);negative_fp=sum(r['fp'] for r in rows if r['stage']=='negative')
    gate=passed and total['precision']==1 and total['recall']>=.8 and negative_fp==0 and all(v['recall']>=.5 for f,v in by_family.items() if f!='hard_negative')
    arm=dict(**total,rows=rows,per_family=by_family,negative_fp=negative_fp,calibration=dict(threshold=threshold,gate_pass=passed),
        coverage=summary([r['coverage'] for r in rows]),geometry=summary([r['geometry'] for r in rows]),research_gate=gate)
    verify(lock);save(output/'results.json',dict(arms=dict(instance=arm),manifest_sha256=digest(manifest),lock_sha256=digest(output/'lock.json')))
    print(json.dumps({k:v for k,v in arm.items() if k!='rows'},indent=2))


def predict(trained,image,threshold,output):
    output.mkdir(parents=True,exist_ok=False);env=environment();model,prior=load_trained(trained)
    objects,size=observe(model,image);kept=[o for o in objects if o['confidence']>=threshold]
    write_shapes(kept,size,output/'result.pptx');board(image,kept,output/'inspection.png')
    save(output/'result.json',dict(objects=kept,all_candidates=objects,threshold=threshold,environment=env,
        input_sha256=digest(image),checkpoint_sha256=digest(trained/'final.pt'),pptx_sha256=digest(output/'result.pptx'),
        scope='RGB-only forward; training lock verified, no source annotation passed to model'))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['control','train','evaluate','predict'])
    for name in ('manifest','trained','image','output','control-run'):p.add_argument('--'+name,type=Path,required=name=='output')
    p.add_argument('--threshold',type=float,default=.95);a=p.parse_args()
    if a.mode in ('control','train'):train(a.manifest,a.output,a.mode=='control',a.control_run)
    elif a.mode=='evaluate':evaluate(a.manifest,a.trained,a.output)
    else:predict(a.trained,a.image,a.threshold,a.output)
