"""Freeze validated R5 evidence; expected graph is a post-inspection source audit."""
import json
from pathlib import Path
from image_to_editable_ppt.research.region_first import digest


def main():
    root=Path(__file__).resolve().parents[1]
    def read(path): return json.loads((root/path).read_text(encoding='utf-8-sig'))
    base='artifacts/region-complex-r5/'
    evidence=read(base+'final-v2/review/evidence.json')
    assert all(digest(root/path)==sha for path,sha in evidence['manifest']['runtime_sha256'].items())
    primary=evidence['results']['records'][0]['report']['emitted_scene']
    names={s['id']:' '.join(s['label'].split()) for s in primary['shapes']}
    expected=[]
    for i in (1,2,3):
        expected.extend([(f'Decoder {i}',f'Program {i}'),(f'Program {i}',f'Executor {i}'),
            (f'Executor {i}',f'Symbolic Prediction {i}'),('Text Embedding',f'Decoder {i}'),
            ('Text Embedding',f'Predictor {i}'),(f'Predictor {i}',f'Neural Prediction {i}')])
    expected.extend([('Input','Encoder'),('Encoder','Text Embedding'),('Text Embedding','Gating Network'),
        ('Gating Network','Mixture-of-Experts'),('Mixture-of-Experts','Final Prediction'),
        ('Neural Prediction 1','Mixture-of-Experts')])
    emitted=[(names[c['source_owner_id']],names[c['target_owner_id']]) for c in primary['connectors']]
    assert len(names)==24 and len(set(names.values()))==24
    assert len(emitted)==24 and set(emitted)==set(expected)
    assert all(c['arrowhead_end'] and not c['arrowhead_start'] for c in primary['connectors'])
    probe=read(base+'final-v2/edit-probe/probe.json')
    record=probe['records'][0]
    assert record['input_sha256']==evidence['results']['records'][0]['pptx_sha256']
    before={s['name']:s for s in record['before'] if s.get('begin_connected')}
    fields=('begin_owner','end_owner','begin_site','end_site')
    for stage in ('edited','reopened'):
        after={s['name']:s for s in record[stage] if s.get('begin_connected')}
        assert set(before)==set(after) and len(before)==24
        assert all(before[k][f]==after[k][f] for k in before for f in fields)
    assert record['text_edit_succeeded'] and record['original_unchanged']
    regression=read(base+'regression-final/results.json')
    rows=[r for r in regression['records'] if 'metrics' in r]
    assert sum(r['metrics']['matched_objects'] for r in rows)==23
    assert sum(r['metrics']['matched_directed_edges'] for r in rows)==15
    assert all(not r['metrics']['unmatched_local_objects'] for r in rows)
    synthetic=read(base+'synthetic-final/results.json')
    assert len(synthetic['records'])==11 and all(r['passed'] for r in synthetic['records'])
    package=read(base+'package/verification.json')
    assert package['runtime_sha256']==evidence['manifest']['runtime_sha256']
    assert package['installed_runtime_matches_source'] and digest(root/package['wheel_path'])==package['wheel_sha256']
    result=dict(manifest=evidence['manifest'],primary_graph_audit=dict(method='post-inspection source graph consistency, not frozen holdout metric',
        names=names,expected_solid_edges=expected,emitted_solid_edges=emitted),
        visual_review=read('benchmarks/region_complex_r5_visual_review.json'),
        cohort=[dict(id=r['id'],counts=r.get('report',{}).get('counts'),returncode=r['returncode'],
            pptx_sha256=r.get('pptx_sha256'),report_sha256=r.get('report_sha256')) for r in evidence['results']['records']],
        audits=evidence['audits'],renders=evidence['render_manifest'],sheets=evidence['sheets'],
        native_edit=probe,package=package,regression=[dict(sample=r['sample'],metrics=r['metrics']) for r in rows],
        synthetic_contracts_passed=11,
        provenance={path:digest(root/path) for path in [base+'final-v2/review/evidence.json',base+'regression-final/results.json',
            base+'synthetic-final/results.json',base+'final-v2/edit-probe/probe.json',base+'package/verification.json',
            'benchmarks/region_complex_r5_visual_review.json','tools/summarize_region_r5.py']})
    with (root/'benchmarks/region_complex_r5_evidence_v2.json').open('x',encoding='utf-8') as handle:
        json.dump(result,handle,indent=2)
    print('R5: graph 24/24 solid links; native edit 24 bindings; ROI 23 objects/15 edges; synthetic 11/11; installed wheel SHA matches')

if __name__=='__main__': main()
