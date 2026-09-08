"""Reserve transfer sources before tuning; execute hash-bound CLI comparisons."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from image_to_editable_ppt.research.region_first import digest

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'artifacts/region-generalization-r6'

def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8',newline='\n') as f: json.dump(value,f,indent=2)

def reserve():
    pool_path=ROOT/'artifacts/phase16-sample-pool-v1/pool_manifest.json'
    pool=json.loads(pool_path.read_text()); selection=json.loads((ROOT/'benchmarks/phase16_selection_v1.json').read_text())
    used={x['pool_id'] for split in selection['splits'].values() for rows in split.values() for x in rows}
    used_rows=[r for r in pool['records'] if r['pool_id'] in used]
    groups={r['source_group'] for r in used_rows}; hashes={r['sha256'] for r in used_rows}
    eligible=[r for r in pool['records'] if r['pool_id'] not in used and r['source_group'] not in groups
        and r['sha256'] not in hashes and all((int(r['perceptual_hash'],16)^int(s['perceptual_hash'],16)).bit_count()>4 for s in used_rows)]
    chosen=[]
    for kind,count in [('diagram_candidate',8),('non_diagram_candidate',4)]:
        for r in sorted([r for r in eligible if r['suggestion']==kind],key=lambda r:r['sha256']):
            if r['source_group'] in {x['source_group'] for x in chosen}: continue
            item=dict(r,path=str((pool_path.parent/r['path']).relative_to(ROOT)),roi=[0,0,1,1])
            assert digest(ROOT/item['path'])==item['sha256']
            chosen.append(item)
            if sum(x['suggestion']==kind for x in chosen)==count: break
    save(ROOT/'benchmarks/region_r6_transfer_inputs.json',dict(baseline='80b0937',pool_sha256=digest(pool_path),
        population='Unused by Phase16 split evaluation; historical source-sheet exposure; R6-reserved transfer, NOT formal holdout',
        rule='SHA-sorted 8 caption-suggested diagrams + 4 non-diagrams, excluded split source groups and <=4-bit perceptual neighbors; no output-based replacement',samples=chosen))
    print([(r['pool_id'],r['suggestion']) for r in chosen])

def freeze():
    save(ROOT/'benchmarks/region_r6_candidate.json',dict(runtime_sha256={str(p.relative_to(ROOT)):digest(p)
        for p in (ROOT/'src/image_to_editable_ppt/region').glob('*.py')},
        cli_sha256=digest(ROOT/'src/image_to_editable_ppt/ml/convert_to_pptx.py')))

def run(cohort,arm):
    if cohort=='complex':
        samples=json.loads((ROOT/'benchmarks/region_complex_r5_inputs_v2.json').read_text())['samples']
    else:
        samples=json.loads((ROOT/'benchmarks/region_r6_transfer_inputs.json').read_text())['samples']
        frozen=json.loads((ROOT/'benchmarks/region_r6_candidate.json').read_text())
        assert all(digest(ROOT/p)==sha for p,sha in frozen['runtime_sha256'].items())
        assert digest(ROOT/'src/image_to_editable_ppt/ml/convert_to_pptx.py')==frozen['cli_sha256']
    out=BASE/f'{cohort}-{arm}'; out.mkdir(parents=True,exist_ok=False)
    target=ROOT/'artifacts/region-complex-r5/package/installed'
    baseline=json.loads((ROOT/'artifacts/region-complex-r5/package/verification.json').read_text())
    if arm=='baseline':
        assert all(digest(target/Path(p).relative_to('src'))==sha for p,sha in baseline['runtime_sha256'].items())
    records=[]
    for item in samples:
        name=item.get('id',item.get('pool_id')); source=ROOT/item['path']; assert digest(source)==item['sha256']
        pp=out/f'{name}.pptx'
        argv=[str(source),'-o',str(pp),'--region',*map(str,item['roi'])]
        if arm=='baseline':
            script=f"import sys; sys.path.insert(0,{str(target)!r}); from image_to_editable_ppt.ml.convert_to_pptx import main; raise SystemExit(main({argv!r}))"
            command=[sys.executable,'-I','-c',script]
        else: command=[sys.executable,'-m','image_to_editable_ppt.ml.convert_to_pptx',*argv]
        r=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=180)
        record=dict(id=name,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr,source_sha256=item['sha256'])
        if r.returncode==0:
            rp=pp.with_suffix('.region.json'); record.update(report=json.loads(rp.read_text()),pptx_sha256=digest(pp),report_sha256=digest(rp))
        records.append(record); print(name,record.get('report',{}).get('counts',r.stderr[-180:]),flush=True)
    save(out/'results.json',dict(cohort=cohort,arm=arm,records=records,
        runtime_sha256=baseline['runtime_sha256'] if arm=='baseline' else {str(p.relative_to(ROOT)):digest(p) for p in (ROOT/'src/image_to_editable_ppt/region').glob('*.py')}))

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('mode',choices=['reserve','freeze','run'])
    p.add_argument('--cohort',choices=['complex','transfer'],default='complex'); p.add_argument('--arm',default='candidate')
    args=p.parse_args()
    if args.mode=='reserve': reserve()
    elif args.mode=='freeze': freeze()
    else: run(args.cohort,args.arm)
