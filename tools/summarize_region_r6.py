"""Freeze success and failure evidence without promoting the R6 candidate."""
import json
from pathlib import Path
from image_to_editable_ppt.research.region_first import digest

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'artifacts/region-generalization-r6'

def read(path): return json.loads(path.read_text(encoding='utf-8-sig'))

def main():
    frozen=read(ROOT/'benchmarks/region_r6_candidate.json')
    assert all(digest(ROOT/p)==sha for p,sha in frozen['runtime_sha256'].items())
    groups={}
    provenance={}
    for group in ('complex-candidate2','transfer-baseline','transfer-candidate'):
        directory=BASE/group; result=read(directory/'results.json'); compact=[]
        for record in result['records']:
            row={k:v for k,v in record.items() if k not in ('report','stdout','stderr')}
            if record['returncode']==0:
                pp=directory/f"{record['id']}.pptx"; rp=pp.with_suffix('.region.json')
                assert digest(pp)==record['pptx_sha256'] and digest(rp)==record['report_sha256']
                report=record['report']; row.update(counts=report['counts'],emitted_scene=report['emitted_scene'],
                    directed_connectors=sum(c['arrowhead_end'] for c in report['emitted_scene']['connectors']),
                    rejected_connectors=report['emission']['rejected_connectors'])
            else: row['rejection']=record['stderr']
            compact.append(row)
        groups[group]=compact
        provenance[str((directory/'results.json').relative_to(ROOT))]=digest(directory/'results.json')
        render=read(directory/'renders/powerpoint_render_manifest.json')
        for r in render['records']:
            assert digest(Path(r['pptx_path']))==r['pptx_sha256'] and digest(Path(r['render_path']))==r['render_sha256']
        provenance[str((directory/'renders/powerpoint_render_manifest.json').relative_to(ROOT))]=digest(directory/'renders/powerpoint_render_manifest.json')
    scene=groups['complex-candidate2'][0]['emitted_scene']
    names={s['id']:' '.join(s['label'].split()) for s in scene['shapes']}
    expected=read(ROOT/'benchmarks/region_complex_r5_evidence_v2.json')['primary_graph_audit']['expected_solid_edges']
    assert len(names)==24 and len(scene['connectors'])==24
    assert {(names[c['source_owner_id']],names[c['target_owner_id']]) for c in scene['connectors'] if c['arrowhead_end']}==set(map(tuple,expected))
    dark=next(r for r in groups['complex-candidate2'] if r['id']=='dark-transformer')
    assert dark['counts']['connectors']==2 and dark['directed_connectors']==0
    roi=read(BASE/'roi-regression2/results.json')
    rows=[r for r in roi['records'] if 'metrics' in r]
    assert sum(r['metrics']['matched_objects'] for r in rows)==23
    assert sum(r['metrics']['matched_directed_edges'] for r in rows)==15
    assert all(not r['metrics']['unmatched_local_objects'] for r in rows)
    synth=read(BASE/'old-synthetic2/results.json')
    assert len(synth['records'])==11 and all(r['passed'] for r in synth['records'])
    for path in [BASE/'roi-regression2/results.json',BASE/'old-synthetic2/results.json',
        ROOT/'tests/test_region_r6.py',ROOT/'tools/run_region_r6.py',ROOT/'tools/review_region_r6.py',Path(__file__),
        ROOT/'benchmarks/region_r6_transfer_inputs.json',ROOT/'benchmarks/region_r6_visual_review.json']:
        provenance[str(path.relative_to(ROOT))]=digest(path)
    result=dict(verdict='GENERALIZATION_NOT_ESTABLISHED_NO_PROMOTION',candidate=frozen,
        transfer_manifest=read(ROOT/'benchmarks/region_r6_transfer_inputs.json'),groups=groups,
        visual_review=read(ROOT/'benchmarks/region_r6_visual_review.json'),
        native_audits=dict(complex=read(BASE/'complex-review/audit.json'),transfer=read(BASE/'transfer-review-complete/audit.json')),
        protected_primary_named_edges=24,roi_objects=23,roi_directed_edges=15,synthetic_contracts=11,
        full_suite=dict(passed=309,warnings=9,new_r6_tests=30),provenance=provenance)
    with (ROOT/'benchmarks/region_r6_evidence.json').open('x',encoding='utf-8',newline='\n') as f: json.dump(result,f,indent=2)
    print('Frozen R6 NO PROMOTION, including direction regression and non-diagram false positives')

if __name__=='__main__': main()
