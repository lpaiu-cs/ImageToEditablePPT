import json
from pathlib import Path
from image_to_editable_ppt.research.region_first import digest
root=Path(__file__).resolve().parents[1]
base=json.loads((root/'benchmarks/region_first_r2_inputs_v1.json').read_text())
r21=json.loads((root/'benchmarks/region_first_r21_evidence_v1.json').read_text())['results']['records']
r0=json.loads((root/'artifacts/region-first-r0/run1/results.json').read_text())['records']
inputs=[]
for original in base['inputs']:
    row={k:v for k,v in original.items() if not k.startswith('scene_')}
    for kind,ledger,arm in [('selected',r21,'combined'),('oracle',r0,'oracle_boxes')]:
        r=next(r for r in ledger if r['sample']==row['sample'] and r['arm']==arm)
        if digest(root/r['scene_path'])!=r['scene_sha256']: raise ValueError('scene drift')
        row[kind+'_path']=r['scene_path']; row[kind+'_sha256']=r['scene_sha256']
    inputs.append(row)
with (root/'benchmarks/region_first_r3_inputs_v1.json').open('x',encoding='utf-8') as f:
    json.dump(dict(target_manifest_sha256=base['target_manifest_sha256'],inputs=inputs),f,indent=2)
