"""Rescore immutable predicted boxes under four input interventions; no GT input."""
import argparse
import json
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
import torch
from torchvision.models.detection.transform import resize_boxes
from r19_instance_detector import ROOT,digest,save,verify,environment,load_trained,read_rgb,image_tensor,write_shapes
from image_to_editable_ppt.research.closed_rect_proposals import _iou


def scores(model,image,boxes):
    tensor=image_tensor(image).cuda();source_size=tensor.shape[-2:]
    with torch.inference_mode():
        batch,_=model.transform([tensor],None);features=model.backbone(batch.tensors)
        scaled=resize_boxes(torch.tensor(boxes,dtype=torch.float32,device='cuda'),source_size,batch.image_sizes[0])
        pooled=model.roi_heads.box_roi_pool(features,[scaled],batch.image_sizes)
        logits,_=model.roi_heads.box_predictor(model.roi_heads.box_head(pooled))
        return logits.softmax(-1).cpu().numpy()


def crop_view(image,box,ablate):
    x,y,a,b=box;h,w=image.shape[:2];dx=(a-x)*.15;dy=(b-y)*.15
    left=max(0,int(np.floor(x-dx)));top=max(0,int(np.floor(y-dy)));right=min(w,int(np.ceil(a+dx)));bottom=min(h,int(np.ceil(b+dy)))
    crop=image[top:bottom,left:right].copy();local=[x-left,y-top,a-left,b-top]
    if ablate:
        x,y,a,b=map(round,local);roi=crop[y:b,x:a];rh,rw=roi.shape[:2]
        border=np.ones((rh,rw),bool);border[round(rh*.12):round(rh*.88),round(rw*.12):round(rw*.88)]=False
        color=np.median(roi[border],axis=0).astype('uint8')
        roi[round(rh*.2):round(rh*.8),round(rw*.2):round(rw*.8)]=color
    return crop,local


def selected(candidates,probabilities):
    rows=[]
    for o,p in zip(candidates,probabilities,strict=True):
        kind=int(np.argmax(p[1:]))+1;score=float(p[kind])
        if score>=.95:rows.append(dict(id=o['id'],bbox=o['bbox'],kind=kind,confidence=score))
    kept=[]
    for o in sorted(rows,key=lambda r:-r['confidence']):
        if not any(_iou(o['bbox'],p['bbox'])>.7 for p in kept):kept.append(o)
    return kept


def run(trained,source,predictions,output):
    output.mkdir(parents=True,exist_ok=False);env=environment();model,prior=load_trained(trained);image=read_rgb(source)
    saved=json.loads(predictions.read_text());assert saved['input_sha256']==digest(source)
    assert saved['checkpoint_sha256']==digest(trained/'final.pt')
    candidates=saved['all_candidates'];assert len(candidates)==94
    files={**prior['files'],str(source.resolve()):digest(source),str(predictions.resolve()):digest(predictions),str((trained/'final.pt').resolve()):digest(trained/'final.pt'),
        str(Path(__file__).resolve()):digest(__file__),str(ROOT/'docs/r20_fixed_roi_probe_spec.md'):digest(ROOT/'docs/r20_fixed_roi_probe_spec.md')}
    save(output/'lock.json',dict(files=files,environment=env));verify(dict(files=files));arms={}
    boxes=[o['bbox'] for o in candidates]
    for arm in ('full600','full1200','local','local_ablated'):
        folder=output/arm;folder.mkdir();model.transform.min_size=(1200,) if arm=='full1200' else (600,);model.transform.max_size=1920 if arm=='full1200' else 960
        if arm.startswith('full'):p=scores(model,image,boxes)
        else:
            predictions_local=[];sheet=Image.new('RGB',(8*180,12*130),'white');draw=ImageDraw.Draw(sheet)
            for i,box in enumerate(boxes):
                crop,local=crop_view(image,box,arm=='local_ablated');predictions_local.append(scores(model,crop,[local])[0])
                im=Image.fromarray(crop);im.thumbnail((178,110));x=i%8*180;y=i//8*130
                sheet.paste(im,(x,y+18));draw.text((x+2,y),candidates[i]['id'],fill='black')
            p=np.stack(predictions_local);sheet.save(folder/'roi-inputs.png')
        assert p.shape==(94,7) and np.isfinite(p).all() and np.allclose(p.sum(1),1)
        objects=selected(candidates,p);write_shapes(objects,(image.shape[1],image.shape[0]),folder/'result.pptx')
        arms[arm]=dict(objects=objects,probabilities=p.tolist(),pptx_sha256=digest(folder/'result.pptx'))
        save(folder/'prediction.json',arms[arm]);print(arm,len(objects),flush=True)
    verify(dict(files=files));save(output/'results.json',dict(arms=arms,candidates=candidates,files=files,environment=env,
        scope='Frozen predicted boxes; no GT, no RPN or bbox regression. Development intervention only.'))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('trained','source','predictions','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();run(a.trained,a.source,a.predictions,a.output)
