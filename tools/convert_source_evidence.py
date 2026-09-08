"""One command: user RGB + explicit legacy checkpoint -> editable research PPT."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from run_region_rgb_baseline import ROOT,digest,save
from run_source_evidence_pipeline import run
from image_to_editable_ppt.research.prediction_handoff import digest as canonical_digest


def convert(image,checkpoint,output,*,closed_nodes=False):
    image=image.resolve();checkpoint=checkpoint.resolve();output=output.resolve()
    if not image.is_file() or not checkpoint.is_file():
        raise ValueError('existing image and checkpoint required')
    from PIL import Image
    with Image.open(image) as im:
        if im.mode!='RGB':raise ValueError('RGB image required; no implicit compositing or color conversion')
        im.verify()
    output.mkdir(parents=True,exist_ok=False)
    inputs=output/'inputs.json'
    save(inputs,[dict(id='user-image',image=str(image),image_sha256=digest(image))])
    detector=output/'detector'
    subprocess.run([sys.executable,str(ROOT/'tools/run_fresh_rgb_detector.py'),'--user-images',
        '--inputs',str(inputs),'--checkpoint',str(checkpoint),'--out',str(detector)],cwd=ROOT,check=True)
    pred=json.loads((detector/'predictions.json').read_text(encoding='utf-8'))
    payload=dict(schema='fresh_rgb_detector_handoff_v1',
        artifacts={name:dict(path=str(detector/name),sha256=digest(detector/name)) for name in
                   ('predictions.json','execution-lock.json','execution.json','reads.json')},
        run_git_commit=pred['run_git_commit'],checkpoint_sha256=pred['checkpoint_sha256'],
        sample_count=len(pred['predictions']),raw_object_count=sum(len(r['source_labels']) for r in pred['predictions']),
        class_map=pred['label_adapter'],execution_attested=True,training_class_provenance='legacy_inferred',research_only=True)
    handoff=output/'handoff.json';save(handoff,dict(payload=payload,payload_sha256=canonical_digest(payload)))
    run(handoff,output/'native',closed_nodes=closed_nodes)
    print(str(output/'native/pptx/000.pptx'))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--image',required=True,type=Path);p.add_argument('--checkpoint',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--closed-nodes',action='store_true')
    p.add_argument('--acknowledge-legacy-research-model',action='store_true',required=True,
                   help='Training class provenance is inferred and ellipse is unsupported; this is not production approval')
    a=p.parse_args();convert(a.image,a.checkpoint,a.output,closed_nodes=a.closed_nodes)
