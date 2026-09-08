"""Replay consumed development sources through the actual installed CLI boundary."""
import argparse
import json
import subprocess
import sys
from pathlib import Path
from image_to_editable_ppt.research.region_first import digest,evaluate
from image_to_editable_ppt.research.native_emit import load_scene


def main():
    p=argparse.ArgumentParser(); p.add_argument('--output-dir',required=True); args=p.parse_args()
    root=Path(__file__).resolve().parents[1]; out=root/args.output_dir; out.mkdir(parents=True,exist_ok=False)
    inputs=json.loads((root/'benchmarks/region_first_r3_inputs_v1.json').read_text())['inputs']
    targets={s['id']:s for s in json.loads((root/'benchmarks/region_first_r0_v1.json').read_text())['samples']}
    result=dict(git_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        git_status=subprocess.check_output(['git','status','--porcelain'],text=True).strip(),
        code_sha256={str(p.relative_to(root)):digest(p) for p in (root/'src/image_to_editable_ppt/region').glob('*.py')},records=[])
    for item in inputs:
        sample=item['sample']; source=root/item['source_path']; assert digest(source)==item['source_sha256']
        output=out/f'{sample}--region_native.pptx'
        command=[sys.executable,'-m','image_to_editable_ppt.ml.convert_to_pptx',str(source),'-o',str(output),'--region',*map(str,item['roi'])]
        run=subprocess.run(command,cwd=root,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=180)
        if run.returncode:
            result['records'].append(dict(sample=sample,status='cli_rejected',source_sha256=item['source_sha256'],roi=item['roi'],
                command=command,returncode=run.returncode,stdout=run.stdout,stderr=run.stderr))
            (out/'results.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
            print(sample,'REJECTED',run.stderr.strip(),flush=True)
            continue
        report_path=output.with_suffix('.region.json'); report=json.loads(report_path.read_text(encoding='utf-8'))
        sp=out/f'{sample}.json'; sp.write_text(json.dumps(report['source_scene'],indent=2),encoding='utf-8')
        scene=load_scene(sp); metrics=evaluate(scene,targets[sample])
        result['records'].append(dict(sample=sample,source_sha256=item['source_sha256'],roi=item['roi'],
            command=command,stdout=run.stdout,stderr=run.stderr,metrics=metrics,
            scene_path=str(sp.relative_to(root)),scene_sha256=digest(sp),
            pptx_path=str(output.relative_to(root)),pptx_sha256=digest(output),
            report_path=str(report_path.relative_to(root)),report_sha256=digest(report_path),report=report))
        (out/'results.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(sample,report['counts'],'targets',metrics['matched_objects'],'extra',metrics['unmatched_local_objects'],'edges',metrics['matched_directed_edges'],flush=True)


if __name__=='__main__': main()
