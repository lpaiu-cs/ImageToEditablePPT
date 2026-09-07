"""Bind R2 to the six frozen R0 ROI scenes, not the R1 oracle selections."""
import json
from pathlib import Path
from image_to_editable_ppt.research.region_first import digest

root=Path(__file__).resolve().parents[1]
samples=json.loads((root/'benchmarks/region_first_r0_v1.json').read_text())['samples']
r0=json.loads((root/'benchmarks/region_first_r0_evidence_v1.json').read_text())
# R0 run ledger is bound below; frozen evidence remains separately tracked.
run=root/'artifacts/region-first-r0/run1/results.json'
records=json.loads(run.read_text())['records']
inputs=[]
for s in samples:
    r=next(r for r in records if r['sample']==s['id'] and r['arm']=='roi_cv')
    if digest(root/r['scene_path'])!=r['scene_sha256'] or digest(root/s['path'])!=s['sha256']:
        raise ValueError('R0 input drift')
    inputs.append(dict(sample=s['id'],source_path=s['path'],source_sha256=s['sha256'],roi=s['roi'],
        scene_path=r['scene_path'],scene_sha256=r['scene_sha256']))
with (root/'benchmarks/region_first_r2_inputs_v1.json').open('x',encoding='utf-8') as f:
    json.dump(dict(status='consumed_development_roi_candidates_not_holdout',
        r0_run_sha256=digest(run),r0_evidence_sha256=digest(root/'benchmarks/region_first_r0_evidence_v1.json'),
        target_manifest_sha256=digest(root/'benchmarks/region_first_r0_v1.json'),inputs=inputs),f,indent=2)
