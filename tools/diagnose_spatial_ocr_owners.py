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
from image_to_editable_ppt.research.spatial_ocr_observation import observe
from image_to_editable_ppt.v3.text.ocr import _load_engine


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
