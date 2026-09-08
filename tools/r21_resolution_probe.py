"""Frozen full-detector resolution probe, RGB input only and no score tuning."""
import argparse
import json
from pathlib import Path
import time
import torch
from r19_instance_detector import ROOT,digest,save,verify,environment,load_trained,observe,board,write_shapes


def run(trained,image,output):
    output.mkdir(parents=True,exist_ok=False);env=environment();model,prior=load_trained(trained)
    checkpoint=trained/'final.pt';assert digest(checkpoint)=='3c74f33ca5e98fdb9cc8ff585b71ff69e802dffa53529e4db580b351efcb8120'
    files={**prior['files'],str(image.resolve()):digest(image),str(checkpoint.resolve()):digest(checkpoint),
        str(Path(__file__).resolve()):digest(__file__),str(ROOT/'docs/r21_resolution_probe_spec.md'):digest(ROOT/'docs/r21_resolution_probe_spec.md')}
    save(output/'lock.json',dict(files=files,environment=env));verify(dict(files=files));arms={}
    for short,long in ((600,960),(1200,1920),(1800,2880)):
        arm=f'full{short}';folder=output/arm;folder.mkdir();model.transform.min_size=(short,);model.transform.max_size=long
        torch.cuda.reset_peak_memory_stats();torch.cuda.synchronize();started=time.monotonic()
        candidates,size=observe(model,image);torch.cuda.synchronize();elapsed=time.monotonic()-started
        objects=[o for o in candidates if o['confidence']>=.95];write_shapes(objects,size,folder/'result.pptx');board(image,objects,folder/'inspection.png')
        arms[arm]=dict(objects=objects,all_candidates=candidates,seconds=elapsed,peak_gpu_bytes=torch.cuda.max_memory_allocated(),pptx_sha256=digest(folder/'result.pptx'))
        print(arm,len(candidates),len(objects),round(elapsed,3),flush=True)
    verify(dict(files=files));save(output/'results.json',dict(arms=arms,files=files,environment=env,input_sha256=digest(image),scope='Exposed development RGB, no GT input; frozen full detector resolution only'))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('trained','image','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();run(a.trained,a.image,a.output)
