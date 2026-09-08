"""R7b 후속 개발 실험. R7의 실패 판정과 파일은 수정하지 않는다."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
from run_region_r7 import ROOT, BASE, ANNOTATIONS, LOCK, digest, save, verify_lock, scene_metrics
from image_to_editable_ppt.research.accepted_owners import load_annotation, proposals, accept_oracle
from image_to_editable_ppt.research.ownership_guards import observe_guarded, owned_styles
from image_to_editable_ppt.region.geometry import normalize_scene
from image_to_editable_ppt.region.emitter import write_native

LOCK_B = ROOT / 'benchmarks/region_r7b_lock.json'


def freeze():
    verify_lock()
    files = [LOCK, Path(__file__).resolve(),
             ROOT / 'src/image_to_editable_ppt/research/ownership_guards.py',
             ROOT / 'docs/region_ownership_guards_r7b_spec.md',
             ROOT / 'tests/test_region_r7b.py',
             ROOT / 'benchmarks/region_r7_evidence.json']
    save(LOCK_B, dict(schema='r7b_diagnostic_lock_v1', population='consumed_development',
                     promotion=False, files={str(p.relative_to(ROOT)): digest(p) for p in files}))


def verify():
    verify_lock()
    for p, sha in json.loads(LOCK_B.read_text(encoding='utf-8'))['files'].items():
        assert digest(ROOT / p) == sha, p


def run():
    verify()
    out = BASE / 'r7b-run'
    out.mkdir(parents=True, exist_ok=False)
    records = []
    previous = {r['id']: r for r in json.loads((BASE / 'run/results.json').read_text(encoding='utf-8'))['records']}
    for path in sorted(ANNOTATIONS.glob('*.json')):
        data, rgb = load_annotation(path, ROOT)
        candidate = proposals(rgb, data['scope'], local=True)
        accepted, acceptance = accept_oracle(candidate, data)
        scene, audit, blocked = observe_guarded(accepted, rgb, data['scope'], data)
        styles, style_audit = owned_styles(accepted, rgb)
        normalized, scale = normalize_scene(scene)
        pp = out / f'{data["id"]}.pptx'
        emitted, emission = write_native(normalized, pp, styles=styles)
        # The topology/style arm must not change R7's owner identities, geometry,
        # or OCR text. A changed backend output fails instead of being hidden.
        prior_scene = previous[data['id']]['arms']['local-oracle']['source_scene']
        assert [(s['id'], s['bbox'], s['label']) for s in asdict(scene)['shapes']] == [
            (s['id'], s['bbox'], s['label']) for s in prior_scene['shapes']]
        rec = dict(id=data['id'], source_sha256=data['source_sha256'],
                   annotation_sha256=digest(path), acceptance=acceptance,
                   before=previous[data['id']]['arms']['local-oracle']['metrics'],
                   after_blockers=scene_metrics(blocked, data), after_boundary=scene_metrics(scene, data),
                   emitted_metrics=scene_metrics(emitted, data), observation=audit,
                   style_audit=style_audit, styles={k: asdict(v) for k, v in styles.items()},
                   source_scene=asdict(scene), emitted_scene=asdict(emitted),
                   normalization_scale=scale, emission=emission, pptx_sha256=digest(pp))
        save(pp.with_suffix('.json'), rec)
        records.append(rec)
        print(data['id'], 'FP before/blockers/boundary:', [len(rec[key]['directed_fp']) for key in
                                                        ('before', 'after_blockers', 'after_boundary')],
              'TP:', len(rec['after_boundary']['directed_tp']), flush=True)
    verify()
    save(out / 'results.json', dict(schema='r7b_diagnostic_results_v1', lock_sha256=digest(LOCK_B),
                                  population='consumed_development', promotion=False, records=records))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('mode', choices=['freeze', 'run'])
    {'freeze': freeze, 'run': run}[p.parse_args().mode]()
