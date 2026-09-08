"""Fixed CPU pretraining ablation; RGB-only predictor is a separate CLI mode."""
import argparse
from collections import Counter
import json
from pathlib import Path
import random
import sys
import time

import numpy as np
from PIL import Image,ImageDraw
import torch
from torch.nn import functional as F
from run_region_rgb_baseline import ROOT,digest,save
sys.path.insert(0,str(ROOT/'src'))
from image_to_editable_ppt.research.ppt_primitive_learning import (
    PrimitiveUNet,SIZE,PALETTE,KINDS,palette_target,components,object_counts,write_shapes)


def image_tensor(path):
    with Image.open(path) as im:
        if im.mode!='RGB':raise ValueError(f'RGB required: {path}')
        size=im.size;array=np.array(im.resize(SIZE,Image.Resampling.BILINEAR))
    return torch.from_numpy(array.copy()).permute(2,0,1).float()/255,size


def load_sample(record):
    image,size=image_tensor(record['image'])
    with Image.open(record['mask']) as im:
        if im.size!=size:raise ValueError('mask and RGB dimensions differ')
        target=palette_target(np.asarray(im.convert('RGB')))
    target=np.array(Image.fromarray(target).resize(SIZE,Image.Resampling.NEAREST))
    return image,torch.from_numpy(target.astype(np.int64)),size


def runtime_lock():
    paths=[Path(__file__).resolve(),ROOT/'docs/r16_ppt_primitive_pretraining_spec.md',
        ROOT/'src/image_to_editable_ppt/research/ppt_primitive_learning.py',
        ROOT/'src/image_to_editable_ppt/ml/connector_segmenter.py']
    return {str(p):digest(p) for p in paths}


def summary(counts):
    totals=Counter()
    for c in counts:totals.update({k:c[k] for k in ('tp','fp','fn')})
    tp,fp,fn=[totals[k] for k in ('tp','fp','fn')]
    return dict(tp=tp,fp=fp,fn=fn,precision=tp/max(1,tp+fp),recall=tp/max(1,tp+fn))


def train(manifest,output):
    output.mkdir(parents=True,exist_ok=False)
    data=json.loads(manifest.read_text(encoding='utf-8'));records=data['records']
    expected={('primitive','train'):24,('scene','train'):24,('scene','calibration'):8,
        ('scene','eval'):8,('negative','train'):4,('negative','calibration'):2,('negative','eval'):2}
    assert Counter((r['stage'],r['split']) for r in records)==expected
    assert len({r['id'] for r in records})==len(records)
    inputs={str(Path(r[k]).resolve()):digest(r[k]) for r in records for k in ('image','mask')}
    groups={}
    for r in records:
        sha=inputs[str(Path(r['image']).resolve())]
        if sha in groups and groups[sha]!=r['split']:raise ValueError('cross-split duplicate RGB')
        groups[sha]=r['split']
    code=runtime_lock();torch.set_num_threads(4);torch.manual_seed(1601)
    lock=dict(manifest=str(manifest.resolve()),manifest_sha256=digest(manifest),input_sha256=inputs,
        code_sha256=code,seed=1601,steps=80,batch=4,lr=.001,size=SIZE,
        torch_version=torch.__version__,device='cpu',classes=KINDS,
        scope='closed-region semantic pilot; no instance embedding/GNN/GT inference/production approval')
    save(output/'lock.json',lock)
    # Training payloads only; calibration/eval are not used for gradients.
    rows=[r for r in records if r['split']=='train'];loaded=[load_sample(r) for r in rows]
    images=torch.stack([v[0] for v in loaded]);targets=torch.stack([v[1] for v in loaded])
    primitive=[i for i,r in enumerate(rows) if r['stage']=='primitive']
    scene=[i for i,r in enumerate(rows) if r['stage']!='primitive']
    counts=torch.bincount(targets[scene][targets[scene]!=255],minlength=7).float().clamp_min(1)
    weights=counts.rsqrt();weights/=weights.mean()
    initial=PrimitiveUNet().state_dict();logs={}
    def stage(model,pool,seed):
        rng=random.Random(seed);optimizer=torch.optim.AdamW(model.parameters(),lr=.001)
        model.train();losses=[];started=time.monotonic()
        for step in range(80):
            indices=[rng.choice(pool) for _ in range(4)]
            optimizer.zero_grad(set_to_none=True);loss=F.cross_entropy(model(images[indices]),targets[indices],weight=weights,ignore_index=255)
            if not torch.isfinite(loss):raise ValueError('non-finite training loss')
            loss.backward();optimizer.step();losses.append(float(loss.detach()))
            if (step+1)%20==0:print(f'{arm} step {step+1}/80 loss={losses[-1]:.5f}',flush=True)
        return dict(losses=losses,seconds=time.monotonic()-started)
    for arm in ('scratch80','pretrain80_scene80','scene80_scene80'):
        model=PrimitiveUNet();model.load_state_dict(initial);phases=[]
        if arm!='scratch80':phases.append(stage(model,primitive if arm.startswith('pretrain') else scene,1602))
        phases.append(stage(model,scene,1603));logs[arm]=phases
        checkpoint=output/(arm+'.pt');torch.save(model.state_dict(),checkpoint)
        save(output/(arm+'-training.json'),dict(phases=phases,checkpoint_sha256=digest(checkpoint)))
    assert digest(manifest)==lock['manifest_sha256']
    assert all(digest(p)==sha for p,sha in {**inputs,**code}.items())
    save(output/'training.json',dict(arms=logs,class_weights=weights.tolist(),lock_sha256=digest(output/'lock.json')))


def infer_probabilities(model,path):
    image,size=image_tensor(path)
    with torch.inference_mode():prob=model(image[None]).softmax(1)[0].numpy()
    return prob,size


def load_model(path):
    torch.set_num_threads(4);model=PrimitiveUNet()
    model.load_state_dict(torch.load(path,map_location='cpu',weights_only=True));model.eval();return model


def predict(checkpoint,image,output,threshold):
    output.mkdir(parents=True,exist_ok=False);code=runtime_lock();source=digest(image)
    model=load_model(checkpoint);prob,size=infer_probabilities(model,image)
    objects=components(prob,size,threshold)
    write_shapes(objects,size,output/'result.pptx')
    save(output/'result.json',dict(objects=objects,image_size=size,source_sha256=source,
        checkpoint_sha256=digest(checkpoint),threshold=threshold,code_sha256=code,pptx_sha256=digest(output/'result.pptx'),
        scope='RGB-only semantic shapes; no OCR, connectors, original fill or GT inputs'))
    overlay(image,prob,objects,output/'inspection.png')
    assert source==digest(image) and all(digest(p)==sha for p,sha in code.items())


def overlay(path,prob,objects,output):
    source=Image.open(path).convert('RGB');w,h=source.size
    mask=Image.fromarray(PALETTE[prob.argmax(0)]).resize((w,h),Image.Resampling.NEAREST)
    board=Image.new('RGB',(w*2,h),'white');board.paste(source);board.paste(mask,(w,0));draw=ImageDraw.Draw(board)
    for obj in objects:
        draw.rectangle(obj['bbox'],outline='red',width=2);draw.text(obj['bbox'][:2],str(obj['kind']),fill='red')
    board.save(output)


def evaluate(manifest,trained,output):
    output.mkdir(parents=True,exist_ok=False);data=json.loads(manifest.read_text());records=data['records']
    lock=json.loads((trained/'lock.json').read_text());assert digest(manifest)==lock['manifest_sha256']
    assert all(digest(p)==sha for p,sha in {**lock['input_sha256'],**lock['code_sha256']}.items())
    calibration=[r for r in records if r['split']=='calibration'];evaluation=[r for r in records if r['split']=='eval']
    results={};calibration_results={}
    # Freeze every arm's threshold before any eval payload is opened.
    for arm in ('scratch80','pretrain80_scene80','scene80_scene80'):
        model=load_model(trained/(arm+'.pt'));observed=[(r,*infer_probabilities(model,r['image'])) for r in calibration]
        checks={str(t):summary([object_counts(components(p,size,t),r['objects']) for r,p,size in observed]) for t in (.5,.7,.85,.95)}
        eligible=[float(t) for t,c in checks.items() if c['fp']==0]
        threshold=max(eligible,key=lambda t:(checks[str(t)]['recall'],t)) if eligible else .95
        calibration_results[arm]=dict(threshold=threshold,checks=checks,gate_pass=bool(eligible))
    save(output/'calibration.json',calibration_results)
    for arm in calibration_results:
        model=load_model(trained/(arm+'.pt'));threshold=calibration_results[arm]['threshold'];rows=[]
        confusion=np.zeros((7,7),np.int64)
        for record in evaluation:
            prob,size=infer_probabilities(model,record['image']);objects=components(prob,size,threshold)
            counts=object_counts(objects,record['objects']);target=load_sample(record)[1].numpy();valid=target!=255
            confusion+=np.bincount((target[valid]*7+prob.argmax(0)[valid]).ravel(),minlength=49).reshape(7,7)
            folder=output/arm/record['id'];folder.mkdir(parents=True)
            write_shapes(objects,size,folder/'result.pptx');overlay(record['image'],prob,objects,folder/'inspection.png')
            rows.append(dict(id=record['id'],stage=record['stage'],**counts,objects=objects,
                per_kind={str(k):object_counts([o for o in objects if o['kind']==k],[o for o in record['objects'] if o['kind']==k]) for k in range(1,7)},
                source_sha256=digest(record['image']),pptx_sha256=digest(folder/'result.pptx')))
        den=confusion.sum(0)+confusion.sum(1)-confusion.diagonal()
        iou=np.divide(confusion.diagonal(),den,out=np.zeros(7),where=den>0)
        results[arm]=dict(**calibration_results[arm],**summary(rows),rows=rows,
            pixel_iou=iou.tolist(),foreground_macro_iou=float(iou[1:].mean()),
            per_kind={str(k):summary([r['per_kind'][str(k)] for r in rows]) for k in range(1,7)},
            negative_fp=sum(r['fp'] for r in rows if r['stage']=='negative'),checkpoint_sha256=digest(trained/(arm+'.pt')))
    save(output/'results.json',dict(arms=results,manifest_sha256=digest(manifest),training_lock_sha256=digest(trained/'lock.json')))
    print(json.dumps({k:{n:v for n,v in r.items() if n not in ('rows','checks')} for k,r in results.items()},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['train','evaluate','predict'])
    p.add_argument('--manifest',type=Path);p.add_argument('--trained',type=Path);p.add_argument('--checkpoint',type=Path)
    p.add_argument('--image',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--threshold',type=float,default=.95)
    a=p.parse_args()
    if a.mode=='train':train(a.manifest,a.output)
    elif a.mode=='evaluate':evaluate(a.manifest,a.trained,a.output)
    else:predict(a.checkpoint,a.image,a.output,a.threshold)
