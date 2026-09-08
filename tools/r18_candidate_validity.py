"""Independent candidate-scale and binary-validity ablation, with frozen kind classification."""
import argparse
from collections import Counter
import json
from pathlib import Path
import random
import numpy as np
from PIL import Image,ImageDraw
import torch
from torch import nn
from torch.nn import functional as F
from r17_object_primitive import ROOT,digest,save,verify,load_model,new_classifier,code_lock as prior_lock
from r16_primitive_pretraining import summary
from image_to_editable_ppt.research.candidate_validity import propose,supervision,validity_scores
from image_to_editable_ppt.research.object_primitive_learning import classify_candidates
from image_to_editable_ppt.research.ppt_primitive_learning import object_counts,select_threshold,write_shapes

OCC=ROOT/'artifacts/region-image-only-r16/primitive-training-v1/scene80_scene80.pt'
KIND=ROOT/'artifacts/region-image-only-r17/training-v1/scene300_scene300.pt'
WEIGHTS={str(OCC):'ae597e2fac851708caa3502457bc18cda1d21f0064f354da519a60c5581759d4',
    str(KIND):'3db8a6e8b47ea3cfa5ed1d5dbe71e5064b8345af626d1fbd64f21f62fd78ad4d'}


def code_lock():
    paths=['tools/r18_candidate_validity.py','docs/r18_candidate_validity_spec.md','src/image_to_editable_ppt/research/candidate_validity.py']
    return {**prior_lock(),**{str(ROOT/p):digest(ROOT/p) for p in paths}}


def rgb(path):
    with Image.open(path) as im:
        if im.mode!='RGB':raise ValueError('RGB input required')
        return np.array(im)


def geometry(objects,expected):
    return object_counts([dict(o,kind=1) for o in objects],[dict(o,kind=1) for o in expected])


def board(rgb_array,objects,path):
    im=Image.fromarray(rgb_array);draw=ImageDraw.Draw(im)
    for o in objects:draw.rectangle(o['bbox'],outline='red',width=2)
    im.save(path)


def prepare(manifest,output):
    output.mkdir(parents=True,exist_ok=False);verify(dict(files=WEIGHTS))
    rows=json.loads(manifest.read_text())['records']
    assert Counter((r['stage'],r['split']) for r in rows)=={('scene','train'):32,('negative','train'):8,('scene','calibration'):12,('negative','calibration'):4,('scene','eval'):12,('negative','eval'):4}
    lock=dict(files={**code_lock(),**WEIGHTS,str(manifest.resolve()):digest(manifest),
        **{r['image']:digest(r['image']) for r in rows if r['split']=='train'}},manifest=str(manifest.resolve()),seed=1801,steps=450,batch=32,lr=.001)
    save(output/'lock.json',lock);occupancy=load_model(OCC);xs=[];ys=[];audit=[]
    for r in rows:
        if r['split']!='train':continue
        image=rgb(r['image']);views=propose(occupancy,image);objects,crops=views['multiscale'];labels=supervision(objects,r['objects'])
        keep=labels>=0;xs.extend(crops[keep]);ys.extend(labels[keep].tolist())
        audit.append(dict(id=r['id'],family=r['family'],labels=Counter(map(int,labels)),
            full=geometry(views['full'][0],r['objects']),multiscale=geometry(objects,r['objects'])))
        if len(audit)<=8:
            board(image,views['full'][0],output/(r['id']+'-full.png'));board(image,objects,output/(r['id']+'-multi.png'))
    if not xs:raise ValueError('No training candidates')
    x=torch.stack(xs);y=torch.tensor(ys);torch.save(dict(x=x,y=y),output/'crops.pt')
    counts=Counter(ys);save(output/'prepared.json',dict(counts=counts,rows=audit,crops_sha256=digest(output/'crops.pt'),lock_sha256=digest(output/'lock.json')))
    selected=[int(i) for k in (1,0) for i in torch.where(y==k)[0][:16]]
    image=Image.new('RGB',(512,8*86),'white');draw=ImageDraw.Draw(image)
    for n,i in enumerate(selected):
        left=n%4*128;top=n//4*86;draw.text((left+2,top),f'label={int(y[i])}',fill='black')
        for ch in range(2):image.paste(Image.fromarray((x[i,ch].numpy()*255).astype('uint8')).convert('RGB'),(left+ch*64,top+20))
    image.save(output/'training-crops.png');verify(lock);print(json.dumps(dict(counts=counts,images=len(audit))))


def validator(checkpoint=None):
    model=new_classifier(KIND);model[11]=nn.Linear(1024,2)
    if checkpoint:model.load_state_dict(torch.load(checkpoint,map_location='cpu',weights_only=True))
    return model


def train(prepared,output):
    output.mkdir(parents=True,exist_ok=False);lock=json.loads((prepared/'lock.json').read_text());verify(lock)
    stats=json.loads((prepared/'prepared.json').read_text());assert digest(prepared/'crops.pt')==stats['crops_sha256']
    data=torch.load(prepared/'crops.pt',weights_only=True);x,y=data['x'],data['y'];pools=[torch.where(y==k)[0].tolist() for k in (0,1)]
    if min(map(len,pools))<24:raise ValueError('Need at least 24 observed positive and negative candidates')
    lock['files'].update({str((prepared/n).resolve()):digest(prepared/n) for n in ('crops.pt','prepared.json','lock.json')})
    save(output/'lock.json',lock);torch.set_num_threads(4);torch.manual_seed(1801);model=validator();model.train()
    optimizer=torch.optim.AdamW(model.parameters(),lr=.001);rng=random.Random(1801);losses=[]
    for step in range(450):
        indices=[rng.choice(pool) for pool in pools for _ in range(16)];optimizer.zero_grad(set_to_none=True)
        loss=F.cross_entropy(model(x[indices]),y[indices]);assert torch.isfinite(loss)
        loss.backward();optimizer.step();losses.append(float(loss.detach()))
        if (step+1)%75==0:print(f'validity {step+1}/450 loss={losses[-1]:.5f}',flush=True)
    model.eval();p=validity_scores(model,x);recalls={str(k):float(np.mean((p[y.numpy()==k]>=.5)==k)) for k in (0,1)}
    torch.save(model.state_dict(),output/'validity.pt');verify(lock)
    save(output/'training.json',dict(recalls=recalls,train_gate=all(v>=.9 for v in recalls.values()),losses=losses,
        checkpoint_sha256=digest(output/'validity.pt'),lock_sha256=digest(output/'lock.json')))
    print(json.dumps(dict(recalls=recalls,train_gate=all(v>=.9 for v in recalls.values()))))


def observe(occupancy,kind,validity,path):
    image=rgb(path);views=propose(occupancy,image);result={}
    for name,(objects,crops) in views.items():
        classified=classify_candidates(kind,objects,crops);p=validity_scores(validity,crops)
        result[name]=[dict(o,validity=float(v)) for o,v in zip(classified,p,strict=True)]
    return result,(image.shape[1],image.shape[0])


def select(objects,threshold=None):
    return [o for o in objects if o['confidence']>=.95 and (threshold is None or o['validity']>=threshold)]


def evaluate(manifest,trained,output):
    output.mkdir(parents=True,exist_ok=False);lock=json.loads((trained/'lock.json').read_text());verify(lock)
    training=json.loads((trained/'training.json').read_text());assert training['train_gate']
    assert digest(trained/'validity.pt')==training['checkpoint_sha256']
    assert str(manifest.resolve())==lock['manifest'];rows=json.loads(manifest.read_text())['records']
    lock['files'].update({**{r['image']:digest(r['image']) for r in rows},str((trained/'validity.pt').resolve()):digest(trained/'validity.pt'),str((trained/'training.json').resolve()):digest(trained/'training.json')})
    assert len({r['image_sha256'] for r in rows})==len(rows)
    for r in rows:assert digest(r['image'])==r['image_sha256']
    save(output/'lock.json',lock);occupancy=load_model(OCC);kind=new_classifier(KIND);validity=validator(trained/'validity.pt').eval()
    calibration=[(r,*observe(occupancy,kind,validity,r['image'])) for r in rows if r['split']=='calibration'];choices={}
    for view in ('full','multiscale'):
        checks={str(t):summary([geometry([o for o in observed[view] if o['validity']>=t],r['objects']) for r,observed,_ in calibration]) for t in (.5,.7,.85,.95,.99)}
        threshold,passed=select_threshold(checks);choices[view]=dict(threshold=threshold,gate_pass=passed,checks=checks)
    save(output/'calibration.json',choices);results={name:[] for name in ('full_raw','full_valid','multiscale_raw','multiscale_valid')}
    # No eval image pixels opened before every calibration choice above is saved.
    for r in rows:
        if r['split']!='eval':continue
        observed,size=observe(occupancy,kind,validity,r['image'])
        for arm,items in results.items():
            view,mode=arm.split('_');all_objects=observed[view];threshold=choices[view]['threshold'] if mode=='valid' else None
            objects=select(all_objects,threshold);folder=output/arm/r['id'];folder.mkdir(parents=True)
            write_shapes(objects,size,folder/'result.pptx');board(rgb(r['image']),objects,folder/'inspection.png')
            items.append(dict(id=r['id'],stage=r['stage'],family=r['family'],**object_counts(objects,r['objects']),objects=objects,all_candidates=all_objects,
                coverage=geometry(all_objects,r['objects']),validity_geometry=geometry([o for o in all_objects if threshold is None or o['validity']>=threshold],r['objects']),
                per_kind={str(k):object_counts([o for o in objects if o['kind']==k],[g for g in r['objects'] if g['kind']==k]) for k in range(1,7)},
                source_sha256=digest(r['image']),pptx_sha256=digest(folder/'result.pptx')))
    arms={}
    for arm,items in results.items():
        arms[arm]=dict(**summary(items),rows=items,coverage=summary([r['coverage'] for r in items]),validity_geometry=summary([r['validity_geometry'] for r in items]),
            per_family={f:summary([r for r in items if r['family']==f]) for f in sorted({r['family'] for r in items})},
            per_kind={str(k):summary([r['per_kind'][str(k)] for r in items]) for k in range(1,7)},
            negative_fp=sum(r['fp'] for r in items if r['stage']=='negative'),calibration=choices[arm.split('_')[0]])
    verify(lock);save(output/'results.json',dict(arms=arms,manifest_sha256=digest(manifest),lock_sha256=digest(output/'lock.json')))
    print(json.dumps({a:{k:v for k,v in r.items() if k not in ('rows','per_kind','calibration')} for a,r in arms.items()},indent=2))


def predict(checkpoint,path,thresholds,output):
    output.mkdir(parents=True,exist_ok=False);files={**code_lock(),**WEIGHTS,str(checkpoint.resolve()):digest(checkpoint),str(path.resolve()):digest(path)}
    verify(dict(files=files));observed,size=observe(load_model(OCC),new_classifier(KIND),validator(checkpoint).eval(),path);arms={}
    for view in ('full','multiscale'):
        for mode in ('raw','valid'):
            arm=view+'_'+mode;folder=output/arm;folder.mkdir();objects=select(observed[view],thresholds[view] if mode=='valid' else None)
            write_shapes(objects,size,folder/'result.pptx');board(rgb(path),objects,folder/'inspection.png')
            arms[arm]=dict(objects=objects,all_candidates=observed[view],pptx_sha256=digest(folder/'result.pptx'))
    verify(dict(files=files));save(output/'result.json',dict(arms=arms,files=files,thresholds=thresholds,scope='RGB and frozen weights only; no GT input'))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','train','evaluate','predict'])
    for name in ('manifest','prepared','trained','checkpoint','image'):p.add_argument('--'+name,type=Path)
    p.add_argument('--full-threshold',type=float,default=.95);p.add_argument('--multi-threshold',type=float,default=.95)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.mode=='prepare':prepare(a.manifest,a.output)
    elif a.mode=='train':train(a.prepared,a.output)
    elif a.mode=='evaluate':evaluate(a.manifest,a.trained,a.output)
    else:predict(a.checkpoint,a.image,dict(full=a.full_threshold,multiscale=a.multi_threshold),a.output)
