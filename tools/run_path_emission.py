import argparse
import json
from pathlib import Path
import subprocess
import numpy as np
from PIL import Image
from image_to_editable_ppt.research.path_emit import write_path_sites,path_audit
from image_to_editable_ppt.research.native_emit import load_scene,normalize_scene
from image_to_editable_ppt.research.region_first import digest,inspect_pptx
from image_to_editable_ppt.v3.emit import sample_shape_styles


def main():
    p=argparse.ArgumentParser(); p.add_argument('--output-dir',required=True); args=p.parse_args()
    root=Path(__file__).resolve().parents[1]
    ep=root/'benchmarks/region_first_r3_evidence_v1.json'
    evidence=json.loads(ep.read_text())
    inputs=[r for r in evidence['results']['records'] if r['arm']=='transparent_gap_trace']
    sources={i['sample']:i for i in json.loads((root/'benchmarks/region_first_r3_inputs_v1.json').read_text())['inputs']}
    for r in inputs:
        assert digest(root/r['scene_path'])==r['scene_sha256']
        assert digest(root/sources[r['sample']]['source_path'])==sources[r['sample']]['source_sha256']
    output=root/args.output_dir; output.mkdir(parents=True,exist_ok=False)
    paths=['src/image_to_editable_ppt/research/path_emit.py','src/image_to_editable_ppt/research/native_emit.py',
        'src/image_to_editable_ppt/v3/emit/pptx_writer.py','src/image_to_editable_ppt/v3/emit/style.py',
        'tools/run_path_emission.py','docs/region_first_r3e_protocol.md']
    result=dict(status='R3E_native_path_diagnostic',input_evidence_sha256=digest(ep),
        git_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        git_status=subprocess.check_output(['git','status','--porcelain'],text=True).strip(),
        code_sha256={s:digest(root/s) for s in paths},records=[])
    for r in inputs:
        scene=load_scene(root/r['scene_path'])
        with Image.open(root/sources[r['sample']]['source_path']) as im: rgb=np.asarray(im.convert('RGB'))
        path=output/f"{r['sample']}--native_path.pptx"
        normalized=normalize_scene(scene)
        sites=write_path_sites(normalized,path,styles=sample_shape_styles(rgb,scene))
        audit=path_audit(normalized,path)
        result['records'].append(dict(sample=r['sample'],input_scene_path=r['scene_path'],input_scene_sha256=r['scene_sha256'],
            pptx_path=str(path.relative_to(root)),pptx_sha256=digest(path),sites=sites,path_audit=audit,native=inspect_pptx(path)))
        (output/'results.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(r['sample'],max((a['max_vertex_error_pt'] for a in audit),default=0))


if __name__=='__main__': main()
