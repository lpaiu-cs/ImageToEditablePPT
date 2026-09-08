"""Verify completed C-v2 artifacts and bind the diagnostic freeze; no inference."""
from collections import Counter
import json
from pathlib import Path
from run_region_rgb_baseline import ROOT, digest, save


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def main():
    out = ROOT / 'artifacts/region-source-evidence-r9/centerline-v2'
    baseline = ROOT / 'artifacts/region-image-only-r8/attachment-t-v1'
    prior, current = read(baseline/'results.json'), read(out/'results.json')
    lock = read(out/'lock.json')
    assert digest(out/'lock.json') == current['lock_sha256']
    assert digest(baseline/'results.json') == lock['source_results_sha256']
    assert all(digest(ROOT/p) == sha for p, sha in lock['runtime_sha256'].items())
    changes, unchanged, reasons = [], [], Counter()
    for old, new in zip(prior['records'], current['records'], strict=True):
        slot = new['slot']
        assert old['id'] == new['id'] and old['slot'] == slot
        assert not new['io']['denied_paths'] and new['returncode'] == 0
        assert digest(out/'rgb'/f'{slot}.png') == old['source_sha256'] == new['source_sha256']
        assert digest(out/'pptx'/f'{slot}.pptx') == new['pptx_sha256']
        assert digest(out/'pptx'/f'{slot}.region.json') == new['report_sha256']
        a, b = old['report'], new['report']
        assert a['source_scene']['shapes'] == b['source_scene']['shapes']
        assert a['emitted_scene']['shapes'] == b['emitted_scene']['shapes']
        for x, y in zip(a['source_scene']['connectors'], b['source_scene']['connectors'], strict=True):
            assert {k:v for k,v in x.items() if k != 'path_points'} == {k:v for k,v in y.items() if k != 'path_points'}
            if x['path_points'] != y['path_points']:
                changes.append(dict(slot=slot, connector_id=y['id']))
        reasons.update(v['reason'] for v in b['centerline_audit']['centerlines'].values())
        if digest(baseline/'renders'/f'{slot}.png') == digest(out/'renders'/f'{slot}.png'):
            unchanged.append(slot)
    assert len(changes) == 6 and {r['slot'] for r in changes} == {'013'}
    assert unchanged == [f'{i:03}' for i in range(15) if i != 13]
    evaluation = read(out/'evaluation.json')
    assert evaluation['totals']['native_edges'] == dict(tp=32,fp=5,fn=35,predictions=37,references=67)
    d = read(ROOT/'benchmarks/r9_d_v1_controls.json')
    assert digest(d['results_path']) == d['results_sha256']
    actual = read(Path(d['results_path']))
    failures = Counter(f for r in actual['results'] for f in r['failures'])
    assert failures == {'false_suppression':376}
    assert sum(r['passed'] for r in actual['results']) == 3280
    assert not actual['denied_file_opens']
    assert digest(ROOT/'src/image_to_editable_ppt/research/duplicate_owner_observations.py') == '90eb83235e988cecc371794f701fd591dc8fe189193d23e2f70ad1ce50a34846'
    files = ['lock.json','results.json','evaluation.json','renders/powerpoint_render_manifest.json']
    files += [f'review/contact-{i}.png' for i in range(3)] + ['review/012.png','review/013.png','review/014.png']
    summary = dict(phase='R9-C v2', verdict='narrow_source_path_gain_not_production',
        artifact_root=str(out.relative_to(ROOT)).replace('\\','/'),
        implementation_lock_commit='15f761b',runner_lock_commit='1a20cc7',
        population=evaluation['population'], files={p:digest(out/p) for p in files},
        controls_passed=43,changed_paths=changes,decision_reasons=dict(reasons),
        supported_but_already_identical_paths=1,
        unchanged_native_render_slots=unchanged,all_owner_label_direction_fields_unchanged=True,
        native_relation_before=dict(tp=26,fp=5,fn=41),native_relation_after=evaluation['totals']['native_edges'],
        traced_relations=evaluation['totals']['traced_edges'],labels=evaluation['labels'],
        raw_fit_rejections_before=20,raw_fit_rejections_after=14,
        direct_visual_review=dict(contact_sheets=3,images=15,enlarged_tree_images=3),
        human_edit_cost_measured=False,product_runtime_changed=False,D_suppression_enabled=False,
        D_result_independent_hash_and_failure_count_check=True)
    save(ROOT/'benchmarks/r9_centerline_v2_results.json',summary)
    print(json.dumps(summary,ensure_ascii=False))


if __name__ == '__main__':
    main()
