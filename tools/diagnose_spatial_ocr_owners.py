"""Image/owner-only OCR observations; no ground truth, no suppression."""
import argparse
import importlib.metadata
import itertools
import json
import math
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from run_region_rgb_baseline import ROOT, digest, save
from image_to_editable_ppt.research.duplicate_owner_observations import overlap,components
from image_to_editable_ppt.v3.text.ocr import _load_engine


def observe(rgb, owners, engine):
    adj=[set() for _ in owners]
    for i,j in itertools.combinations(range(len(owners)),2):
        if overlap(owners[i]['bbox'],owners[j]['bbox'])[0]>0:adj[i].add(j);adj[j].add(i)
    results=[]
    for indices in components(adj):
        if len(indices)<2:continue
        group=[owners[i] for i in indices];boxes=[o['bbox'] for o in group]
        row=dict(owners=group,observations=[]);results.append(row)
        if len(indices)>4 or any(j not in adj[i] for i,j in itertools.combinations(indices,2)):
            row['reason']='unsupported_cluster';continue
        x0=max(0,math.floor(min(b[0] for b in boxes))-2);y0=max(0,math.floor(min(b[1] for b in boxes))-2)
        x1=min(rgb.shape[1],math.ceil(max(b[2] for b in boxes))+2);y1=min(rgb.shape[0],math.ceil(max(b[3] for b in boxes))+2)
        crop=rgb[y0:y1,x0:x1];color=np.median(crop.reshape(-1,3),axis=0).tolist()
        padded=cv2.copyMakeBorder(crop,16,16,16,16,cv2.BORDER_CONSTANT,value=color)
        row['crop']=[x0,y0,x1,y1]
        for scale in (3.,4.5):
            enlarged=cv2.resize(padded,None,fx=scale,fy=scale,interpolation=cv2.INTER_CUBIC)
            found,_=engine(enlarged)
            row['observations'].append(dict(scale=scale,words=[dict(
                polygon=[[float(p[0])/scale-16+x0,float(p[1])/scale-16+y0] for p in word[0]],
                text=word[1],confidence=float(word[2])) for word in found or []]))
    return results


def main(args):
    baseline=ROOT/'artifacts/region-image-only-r8/attachment-t-v1'
    ref=json.loads((ROOT/'benchmarks/region_r8a_attachment.json').read_text())['arms']['t']
    assert digest(baseline/'results.json')==ref['files']['results.json']
    rows=json.loads((baseline/'results.json').read_text(encoding='utf-8'))['records']
    args.output.mkdir(parents=True,exist_ok=False)
    import rapidocr_onnxruntime
    package=Path(rapidocr_onnxruntime.__file__).parent
    save(args.output/'lock.json',dict(source_results_sha256=digest(baseline/'results.json'),
        code_sha256=digest(Path(__file__)),spec_sha256=digest(ROOT/'docs/r10_spatial_ocr_owner_spec.md'),
        models={p.name:digest(p) for p in (package/'models').glob('*.onnx')},
        rapidocr=importlib.metadata.version('rapidocr-onnxruntime'),numpy=np.__version__,opencv=cv2.__version__,
        stage='before_OCR',annotation_access=False))
    cv2.setNumThreads(1);engine=_load_engine()
    if engine is None:raise RuntimeError('OCR unavailable')
    records=[]
    for row in rows:
        image=baseline/'rgb'/f"{row['slot']}.png"
        assert digest(image)==row['source_sha256']
        owners=[dict(id=s['id'],bbox=[s['bbox'][k] for k in ('x0','y0','x1','y1')])
            for s in row['report']['source_scene']['shapes'] if s['shape_kind']=='label_anchor']
        observations=observe(np.array(Image.open(image).convert('RGB')),owners,engine)
        records.append(dict(slot=row['slot'],source_sha256=row['source_sha256'],clusters=observations))
        if observations:print(json.dumps(records[-1],ensure_ascii=False),flush=True)
    save(args.output/'results.json',dict(purpose='source-only spatial OCR diagnosis',records=records))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);main(p.parse_args())
