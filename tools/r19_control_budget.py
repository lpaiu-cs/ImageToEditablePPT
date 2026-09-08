"""Fixed 600-step repeat of a failed training-only control; no new eval pixels."""
import argparse
from r19_instance_detector import *


def run(manifest,output):
    output.mkdir(parents=True,exist_ok=False);env=environment()
    rows=representative([r for r in json.loads(manifest.read_text())['records'] if r['split']=='train']);assert len(rows)==5
    lock=dict(files={**code_lock(),str(Path(__file__).resolve()):digest(__file__),
        str(ROOT/'docs/r19_control_budget_amendment.md'):digest(ROOT/'docs/r19_control_budget_amendment.md'),
        str(manifest.resolve()):digest(manifest),**{r['image']:digest(r['image']) for r in rows}},
        environment=env,manifest=str(manifest.resolve()),control=True,steps=600,batch=2,seed=1901)
    model=new_model(pretrained=True).cuda();weights=Path(torch.hub.get_dir())/'checkpoints/resnet50-0676ba61.pth'
    lock['files'][str(weights.resolve())]=digest(weights);save(output/'lock.json',lock);verify(lock)
    cached=[]
    for r in rows:
        assert digest(r['image'])==r['image_sha256'];image=read_rgb(r['image'])
        cached.append((image_tensor(image),target(r['objects'],(image.shape[1],image.shape[0]))))
    optimizer=torch.optim.AdamW(model.parameters(),lr=.0003,weight_decay=.0001);rng=random.Random(1901)
    losses=[];snapshots=[];started=time.monotonic()
    for step in range(1,601):
        model.train();indices=[rng.randrange(len(cached)) for _ in range(2)];optimizer.zero_grad(set_to_none=True)
        parts=model([cached[i][0].cuda() for i in indices],[{k:v.cuda() for k,v in cached[i][1].items()} for i in indices]);loss=sum(parts.values())
        assert torch.isfinite(loss);loss.backward();optimizer.step();losses.append(dict(step=step,loss=float(loss.detach())))
        if step%100==0:print(json.dumps(dict(step=step,loss=losses[-1]['loss'],seconds=time.monotonic()-started)),flush=True)
        if step in (100,300,600):
            folder=output/f'step-{step:04d}';folder.mkdir();checks=[]
            for r in rows:
                objects,size=observe(model,r['image']);kept=[o for o in objects if o['confidence']>=.5]
                board(r['image'],kept,folder/(r['id']+'.png'))
                checks.append(dict(id=r['id'],objects=kept,geometry=geometry(kept,r['objects']),**object_counts(kept,r['objects'])))
            snap=dict(step=step,rows=checks,strict=summary(checks),geometry=summary([r['geometry'] for r in checks]))
            save(folder/'checks.json',snap);snapshots.append(snap);print(json.dumps({k:v for k,v in snap.items() if k!='rows'}),flush=True)
    verify(lock);torch.save(model.cpu().state_dict(),output/'final.pt');last=snapshots[-1]
    save(output/'training.json',dict(control=True,control_gate=last['geometry']['recall']>=.9 and last['strict']['recall']>=.8,
        losses=losses,snapshots=snapshots,checkpoint_sha256=digest(output/'final.pt'),lock_sha256=digest(output/'lock.json'),seconds=time.monotonic()-started))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.manifest,a.output)
