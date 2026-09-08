"""Frozen object-level pretraining experiment; prediction accepts RGB, not source annotations."""
import argparse
from collections import Counter
import json
from pathlib import Path
import random
import time
import numpy as np
from PIL import Image,ImageDraw
import torch
from torch.nn import functional as F
from scipy.optimize import linear_sum_assignment
from r16_primitive_pretraining import ROOT,digest,save,load_model,infer_probabilities,summary
from image_to_editable_ppt.research.object_primitive_learning import object_classifier,candidate_crops,classify_candidates
from image_to_editable_ppt.research.ppt_primitive_learning import object_counts,select_threshold,write_shapes,KINDS
from image_to_editable_ppt.research.closed_rect_proposals import _iou

ARMS=('scratch_scene300','pretrain300_scene300','scene300_scene300')
OCCUPANCY_SHA='ae597e2fac851708caa3502457bc18cda1d21f0064f354da519a60c5581759d4'


def code_lock():
    paths=['tools/r17_object_primitive.py','docs/r17_object_primitive_spec.md',
        'src/image_to_editable_ppt/research/object_primitive_learning.py',
        'src/image_to_editable_ppt/research/ppt_primitive_learning.py',
        'src/image_to_editable_ppt/research/closed_rect_proposals.py',
        'src/image_to_editable_ppt/ml/family_classifier.py','src/image_to_editable_ppt/ml/connector_segmenter.py',
        'tools/r16_primitive_pretraining.py','tools/run_region_rgb_baseline.py']
    return {str(ROOT/p):digest(ROOT/p) for p in paths}


def verify(lock):
    assert all(digest(p)==sha for p,sha in lock['files'].items())


def candidates(occupancy,path):
    prob,size=infer_probabilities(occupancy,path)
    with Image.open(path) as im:rgb=np.array(im)
    objects,crops=candidate_crops(rgb,prob)
    return objects,crops,size


def samples(manifest,occupancy):
    rows=json.loads(manifest.read_text())['records'];pools={stage:[[],[]] for stage in ('primitive','scene')};audit=[]
    assert Counter((r['stage'],r['split']) for r in rows if r['split']=='train')=={('primitive','train'):24,('scene','train'):24,('negative','train'):4}
    for r in rows:
        if r['split']!='train':continue
        objects,crops,_=candidates(occupancy,r['image']);expected=r['objects'];matched=[]
        scores=np.array([[_iou(a['bbox'],b['bbox']) for b in expected] for a in objects]).reshape(len(objects),len(expected))
        if scores.size:
            ii,jj=linear_sum_assignment(-((scores>=.5).astype(float)+scores/(min(scores.shape)+1)))
            for i,j in zip(ii,jj,strict=True):
                if scores[i,j]>=.5:
                    matched.append((int(i),int(j)));pools[r['stage']][0].append(crops[i]);pools[r['stage']][1].append(expected[j]['kind']-1)
        audit.append(dict(id=r['id'],stage=r['stage'],expected=len(expected),proposed=len(objects),matched=len(matched),
            false_candidates=len(objects)-len(matched),missing=len(expected)-len(matched)))
    return {s:(torch.stack(x),torch.tensor(y)) for s,(x,y) in pools.items()},audit


def accuracy(model,data):
    x,y=data;model.eval()
    with torch.inference_mode():p=torch.cat([model(v).softmax(1) for v in x.split(24)])
    correct=p.argmax(1)==y
    return dict(correct=int(correct.sum()),total=len(y),per_kind={str(k+1):dict(correct=int(correct[y==k].sum()),total=int((y==k).sum())) for k in range(6)}),p


def fit(model,data,seed,name):
    x,y=data;rng=random.Random(seed);by_kind=[torch.where(y==k)[0].tolist() for k in range(6)]
    if not all(by_kind):raise ValueError('Training candidates omit a required kind')
    optimizer=torch.optim.AdamW(model.parameters(),lr=.001);model.train();losses=[];started=time.monotonic()
    for step in range(300):
        indices=[rng.choice(pool) for pool in by_kind for _ in range(2)]
        optimizer.zero_grad(set_to_none=True);loss=F.cross_entropy(model(x[indices]),y[indices])
        if not torch.isfinite(loss):raise ValueError('nonfinite loss')
        loss.backward();optimizer.step();losses.append(float(loss.detach()))
        if (step+1)%50==0:print(f'{name} {step+1}/300 loss={losses[-1]:.5f}',flush=True)
    return dict(losses=losses,seconds=time.monotonic()-started,accuracy=accuracy(model,data)[0])


def new_classifier(checkpoint):
    model=object_classifier();model.load_state_dict(torch.load(checkpoint,map_location='cpu',weights_only=True));model.eval();return model


def positive(manifest,occupancy_path,output):
    output.mkdir(parents=True,exist_ok=False);assert digest(occupancy_path)==OCCUPANCY_SHA
    records=json.loads(manifest.read_text())['records']
    files={**code_lock(),str(manifest.resolve()):digest(manifest),str(occupancy_path.resolve()):digest(occupancy_path),
        **{r['image']:digest(r['image']) for r in records if r['split']=='train'}}
    lock=dict(files=files,manifest=str(manifest.resolve()),occupancy=str(occupancy_path.resolve()),seed=1701,
        steps=300,batch=12,lr=.001,crop_size=64,torch_version=torch.__version__,device='cpu')
    save(output/'lock.json',lock);torch.set_num_threads(4);torch.manual_seed(1701)
    occupancy=load_model(occupancy_path);data,audit=samples(manifest,occupancy);save(output/'candidates.json',audit)
    # Reset after loading the frozen detector so classifier initialization is explicit.
    torch.manual_seed(1701);model=object_classifier();torch.save(model.state_dict(),output/'initial.pt')
    phase=fit(model,data['primitive'],1702,'primitive positive');torch.save(model.state_dict(),output/'primitive.pt')
    stats,prob=accuracy(model,data['primitive']);primitive=[r for r in audit if r['stage']=='primitive']
    passed=stats['correct']==stats['total']==24 and all(r['matched']==r['expected']==r['proposed']==1 for r in primitive)
    board=Image.new('RGB',(512,6*94),'white');draw=ImageDraw.Draw(board)
    x,y=data['primitive']
    for i,(crop,label,p) in enumerate(zip(x,y,prob,strict=True)):
        left=(i%4)*128;top=(i//4)*94
        for j in range(2):board.paste(Image.fromarray((crop[j].numpy()*255).astype(np.uint8)).convert('RGB'),(left+j*64,top+28))
        draw.text((left+2,top),f'GT{int(label)+1} Pred{int(p.argmax())+1} {float(p.max()):.2f}',fill='black')
    board.save(output/'positive-crops.png');verify(lock)
    save(output/'positive.json',dict(passed=passed,accuracy=stats,phase=phase,primitive_sha256=digest(output/'primitive.pt'),
        initial_sha256=digest(output/'initial.pt'),lock_sha256=digest(output/'lock.json'),scope='Training learnability, not generalization'))
    print(json.dumps(dict(passed=passed,accuracy=stats)))


def train(positive_dir,output):
    output.mkdir(parents=True,exist_ok=False);control=json.loads((positive_dir/'positive.json').read_text());assert control['passed']
    lock=json.loads((positive_dir/'lock.json').read_text());verify(lock)
    assert digest(positive_dir/'primitive.pt')==control['primitive_sha256'] and digest(positive_dir/'initial.pt')==control['initial_sha256']
    lock['files'].update({str((positive_dir/name).resolve()):digest(positive_dir/name) for name in ('positive.json','primitive.pt','initial.pt','lock.json')})
    save(output/'lock.json',lock);torch.set_num_threads(4)
    data,audit=samples(Path(lock['manifest']),load_model(Path(lock['occupancy'])));save(output/'candidates.json',audit);results={}
    for arm in ARMS:
        model=new_classifier(positive_dir/('primitive.pt' if arm.startswith('pretrain') else 'initial.pt'));phases=[]
        if arm=='scene300_scene300':
            phases.append(fit(model,data['scene'],1702,arm+' first'));torch.save(model.state_dict(),output/'scene-first.pt')
        phases.append(fit(model,data['scene'],1703,arm));path=output/(arm+'.pt');torch.save(model.state_dict(),path)
        results[arm]=dict(phases=phases,checkpoint_sha256=digest(path),
            primitive_accuracy=accuracy(model,data['primitive'])[0],scene_accuracy=accuracy(model,data['scene'])[0])
    verify(lock);save(output/'training.json',dict(arms=results,lock_sha256=digest(output/'lock.json')))
    print(json.dumps({a:{k:v for k,v in r.items() if k!='phases'} for a,r in results.items()},indent=2))


def predict_objects(occupancy,model,path):
    objects,crops,size=candidates(occupancy,path)
    return classify_candidates(model,objects,crops),size


def inspect(path,objects,output):
    with Image.open(path) as im:board=im.convert('RGB')
    draw=ImageDraw.Draw(board)
    for obj in objects:
        draw.rectangle(obj['bbox'],outline='red',width=1);draw.text(obj['bbox'][:2],f'{obj["kind"]}:{obj["confidence"]:.2f}',fill='black')
    board.save(output)


def evaluate(manifest,trained,output):
    output.mkdir(parents=True,exist_ok=False);lock=json.loads((trained/'lock.json').read_text());verify(lock)
    records=json.loads(manifest.read_text())['records'];training=json.loads((trained/'training.json').read_text())
    assert Counter((r['stage'],r['split']) for r in records)=={('scene','calibration'):12,('negative','calibration'):4,('scene','eval'):12,('negative','eval'):4}
    inputs={r['image']:digest(r['image']) for r in records}
    assert len(set(inputs.values()))==32
    old_records=json.loads(Path(lock['manifest']).read_text())['records']
    assert not set(inputs.values()) & {r['image_sha256'] for r in old_records}
    checkpoints={str((trained/(a+'.pt')).resolve()):training['arms'][a]['checkpoint_sha256'] for a in ARMS}
    lock['files'].update({**inputs,**checkpoints,str(manifest.resolve()):digest(manifest),str((trained/'training.json').resolve()):digest(trained/'training.json')})
    verify(lock);save(output/'lock.json',lock);occupancy=load_model(Path(lock['occupancy']));calibration={}
    for arm in ARMS:
        model=new_classifier(trained/(arm+'.pt'))
        observed=[(r,*predict_objects(occupancy,model,r['image'])) for r in records if r['split']=='calibration']
        checks={str(t):summary([object_counts([o for o in obj if o['confidence']>=t],r['objects']) for r,obj,_ in observed]) for t in (.5,.7,.85,.95)}
        threshold,gate_pass=select_threshold(checks);calibration[arm]=dict(threshold=threshold,gate_pass=gate_pass,checks=checks)
    save(output/'calibration.json',calibration)
    results={}
    for arm,cal in calibration.items():
        model=new_classifier(trained/(arm+'.pt'));rows=[]
        for record in records:
            if record['split']!='eval':continue
            all_objects,size=predict_objects(occupancy,model,record['image']);objects=[o for o in all_objects if o['confidence']>=cal['threshold']]
            folder=output/arm/record['id'];folder.mkdir(parents=True);write_shapes(objects,size,folder/'result.pptx');inspect(record['image'],objects,folder/'inspection.png')
            coverage=object_counts([dict(o,kind=1) for o in all_objects],[dict(o,kind=1) for o in record['objects']])
            rows.append(dict(id=record['id'],stage=record['stage'],**object_counts(objects,record['objects']),objects=objects,all_candidates=all_objects,coverage=coverage,
                per_kind={str(k):object_counts([o for o in objects if o['kind']==k],[o for o in record['objects'] if o['kind']==k]) for k in range(1,7)},
                source_sha256=digest(record['image']),pptx_sha256=digest(folder/'result.pptx')))
        results[arm]=dict(**cal,**summary(rows),rows=rows,coverage=summary([r['coverage'] for r in rows]),
            per_kind={str(k):summary([r['per_kind'][str(k)] for r in rows]) for k in range(1,7)},
            negative_fp=sum(r['fp'] for r in rows if r['stage']=='negative'),checkpoint_sha256=training['arms'][arm]['checkpoint_sha256'])
    verify(lock);save(output/'results.json',dict(arms=results,manifest_sha256=digest(manifest),training_lock_sha256=digest(trained/'lock.json')))
    print(json.dumps({a:{k:v for k,v in r.items() if k not in ('rows','checks')} for a,r in results.items()},indent=2))


def predict(occupancy_path,checkpoint,image,threshold,output):
    output.mkdir(parents=True,exist_ok=False);assert digest(occupancy_path)==OCCUPANCY_SHA
    files={**code_lock(),str(occupancy_path.resolve()):digest(occupancy_path),str(checkpoint.resolve()):digest(checkpoint),str(image.resolve()):digest(image)}
    objects,size=predict_objects(load_model(occupancy_path),new_classifier(checkpoint),image);objects=[o for o in objects if o['confidence']>=threshold]
    write_shapes(objects,size,output/'result.pptx');inspect(image,objects,output/'inspection.png');verify(dict(files=files))
    save(output/'result.json',dict(objects=objects,threshold=threshold,image_size=size,files=files,pptx_sha256=digest(output/'result.pptx'),scope='RGB and weights only; no GT input'))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['positive','train','evaluate','predict'])
    for name in ('manifest','occupancy','positive','trained','checkpoint','image'):p.add_argument('--'+name,type=Path)
    p.add_argument('--threshold',type=float,default=.95);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.mode=='positive':positive(a.manifest,a.occupancy,a.output)
    elif a.mode=='train':train(a.positive,a.output)
    elif a.mode=='evaluate':evaluate(a.manifest,a.trained,a.output)
    else:predict(a.occupancy,a.checkpoint,a.image,a.threshold,a.output)
