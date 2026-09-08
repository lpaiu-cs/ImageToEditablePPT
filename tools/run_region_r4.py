"""R4 frozen-scene identity/text/style diagnostic; no production quality claim."""
import argparse
import json
import subprocess
from pathlib import Path
import numpy as np
from PIL import Image
from image_to_editable_ppt.region.identity import filter_identity
from image_to_editable_ppt.region.text import recover_labels
from image_to_editable_ppt.region.emitter import write_native
from image_to_editable_ppt.research.native_emit import load_scene,normalize_scene
from image_to_editable_ppt.research.region_first import digest,evaluate,serialize_scene,inspect_pptx
from image_to_editable_ppt.v3.emit import sample_shape_styles


def main():
    p=argparse.ArgumentParser(); p.add_argument('--output-dir',required=True); args=p.parse_args()
    root=Path(__file__).resolve().parents[1]; out=root/args.output_dir; out.mkdir(parents=True,exist_ok=False)
    inputs={r['sample']:r for r in json.loads((root/'benchmarks/region_first_r3_inputs_v1.json').read_text())['inputs']}
    targets={s['id']:s for s in json.loads((root/'benchmarks/region_first_r0_v1.json').read_text())['samples']}
    records=[r for r in json.loads((root/'benchmarks/region_first_r3_evidence_v1.json').read_text())['results']['records'] if r['arm']=='transparent_gap_trace']
    result=dict(git_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        code_sha256={str(p.relative_to(root)):digest(p) for p in (root/'src/image_to_editable_ppt/region').glob('*.py')},records=[])
    for r in records:
        sample=r['sample']; item=inputs[sample]
        assert digest(root/r['scene_path'])==r['scene_sha256'] and digest(root/item['source_path'])==item['source_sha256']
        scene=load_scene(root/r['scene_path'])
        with Image.open(root/item['source_path']) as im: rgb=np.asarray(im.convert('RGB'))
        selected,identity=filter_identity(scene,rgb,item['roi'])
        labeled,text=recover_labels(selected,rgb)
        pp=out/f'{sample}--region_native.pptx'; sp=out/f'{sample}.json'
        emitted,emission=write_native(normalize_scene(labeled),pp,styles=sample_shape_styles(rgb,labeled))
        sp.write_text(json.dumps(serialize_scene(labeled),indent=2),encoding='utf-8')
        metrics=evaluate(labeled,targets[sample])
        result['records'].append(dict(sample=sample,identity=identity,text=text,emission=emission,metrics=metrics,
            source_sha256=item['source_sha256'],input_scene_sha256=r['scene_sha256'],
            scene_path=str(sp.relative_to(root)),scene_sha256=digest(sp),pptx_path=str(pp.relative_to(root)),pptx_sha256=digest(pp),native=inspect_pptx(pp)))
        (out/'results.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(sample,'objects',metrics['matched_objects'],'extra',metrics['unmatched_local_objects'],'edges',metrics['matched_directed_edges'],'labels',sum(s.label is not None for s in labeled.shapes),'removed',identity['removed'],flush=True)


if __name__=='__main__': main()
