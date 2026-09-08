"""R7 연구용 주석 검토, 해시 동결 및 오라클 복원 한계 측정."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import subprocess

from PIL import Image, ImageDraw
from image_to_editable_ppt.research.accepted_owners import (
    load_annotation, proposals, accept_oracle, observe_accepted, match, targets,
    SUPPORTED, box_tuple, intersection, area,
)
from image_to_editable_ppt.region.geometry import normalize_scene
from image_to_editable_ppt.region.emitter import write_native
from image_to_editable_ppt.region.tracing import trace_scene
from image_to_editable_ppt.region.text import recover_labels
from image_to_editable_ppt.v3.emit import sample_shape_styles

ROOT = Path(__file__).resolve().parents[1]
ANNOTATIONS = ROOT / 'benchmarks/region_r7_annotations'
LOCK = ROOT / 'benchmarks/region_r7_lock.json'
BASE = ROOT / 'artifacts/region-accepted-owners-r7'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)


def overlay(rgb, shapes, path, scope, exclusions=()):
    im = Image.fromarray(rgb).copy()
    draw = ImageDraw.Draw(im)
    for e in exclusions:
        draw.rectangle(e, outline='#ff00aa', width=2)
    for sid, box, role in shapes:
        draw.rectangle(box, outline='#e11d48' if role == 'node' else '#2563eb', width=2)
        draw.text((box[0]+2, box[1]+2), sid, fill='#6d00a8', stroke_width=1, stroke_fill='white')
    im.crop(scope).save(path)


def review_annotations():
    out = BASE / 'annotation-review'
    out.mkdir(parents=True, exist_ok=False)
    for path in sorted(ANNOTATIONS.glob('*.json')):
        data, rgb = load_annotation(path, ROOT)
        overlay(rgb, [(o['id'], o['bbox'], o['role']) for o in targets(data)],
                out / f'{data["id"]}.png', data['scope'],
                [o['bbox'] for o in data['objects'] if o['role'] in {'nonstructural', 'unknown'}])
        print(data['id'], 'source frame validated', flush=True)


def freeze():
    files = [*sorted(ANNOTATIONS.glob('*.json')), Path(__file__).resolve(),
             ROOT / 'src/image_to_editable_ppt/research/accepted_owners.py',
             ROOT / 'docs/region_accepted_owners_r7_spec.md']
    r6 = json.loads((ROOT / 'benchmarks/region_r6_candidate.json').read_text())
    for path, sha in r6['runtime_sha256'].items():
        if digest(ROOT / path) != sha:
            raise ValueError(f'R6 runtime changed: {path}')
    if digest(ROOT / 'src/image_to_editable_ppt/ml/convert_to_pptx.py') != r6['cli_sha256']:
        raise ValueError('production CLI changed')
    for path in sorted(ANNOTATIONS.glob('*.json')):
        data, _ = load_annotation(path, ROOT)
        files.append(BASE / 'annotation-review' / f'{data["id"]}.png')
    save(LOCK, dict(schema='r7_oracle_lock_v1', population='consumed_development',
                   promotion=False, baseline='0b9c699',
                   files={str(p.relative_to(ROOT)): digest(p) for p in files},
                   baseline_runtime=r6))
    print('R7 development inputs and implementation frozen')


def verify_lock():
    lock = json.loads(LOCK.read_text(encoding='utf-8'))
    for path, sha in lock['files'].items():
        if digest(ROOT / path) != sha:
            raise ValueError(f'locked file changed: {path}')
    for path, sha in lock['baseline_runtime']['runtime_sha256'].items():
        if digest(ROOT / path) != sha:
            raise ValueError(f'baseline runtime changed: {path}')
    if digest(ROOT / 'src/image_to_editable_ppt/ml/convert_to_pptx.py') != lock['baseline_runtime']['cli_sha256']:
        raise ValueError('production CLI changed')


def proposal_metrics(candidate, data):
    mapping = match(candidate, data)
    truth = {o['id']: o for o in targets(data)}
    found = set(mapping.values())
    supported = {oid for oid, o in truth.items() if o['geometry'] in SUPPORTED}
    exclusions = [o['bbox'] for o in data['objects'] if o['role'] in {'nonstructural', 'unknown'}]
    return dict(candidates=len(candidate.scene.shapes), total_targets=len(truth),
                matched=len(found), supported_targets=len(supported), supported_matched=len(found & supported),
                missing=sorted(set(truth)-found), unmatched_candidates=len(candidate.scene.shapes)-len(found),
                role_errors=[s.id for s in candidate.scene.shapes if s.id in mapping
                             and s.owner_kind.value != truth[mapping[s.id]]['role']],
                excluded_candidates=[s.id for s in candidate.scene.shapes if any(
                    intersection(box_tuple(s), e) / max(1, area(box_tuple(s))) >= .50 for e in exclusions)])


def scene_metrics(scene, data, id_map=None):
    truth = {o['id']: o for o in targets(data)}
    mapping = id_map if id_map is not None else {s.id: s.id for s in scene.shapes}
    expected = {(r['source'], r['target']) for r in data['relations']}
    actual = []
    undirected = []
    for c in scene.connectors:
        a, b = mapping.get(c.source_owner_id, c.source_owner_id), mapping.get(c.target_owner_id, c.target_owner_id)
        if c.arrowhead_end and not c.arrowhead_start:
            actual.append((a, b))
        elif c.arrowhead_start and not c.arrowhead_end:
            actual.append((b, a))
        else:
            undirected.append((a, b))
    unique = set(actual)
    labels = []
    normalize = lambda value: ''.join((value or '').split()).casefold()
    for s in scene.shapes:
        target = truth.get(mapping.get(s.id))
        if target and target['role'] == 'node':
            labels.append(dict(id=target['id'], expected=target.get('label'), actual=s.label,
                               exact=bool(s.label) and normalize(s.label) == normalize(target.get('label'))))
    return dict(nodes=sum(s.owner_kind.value == 'node' for s in scene.shapes),
                containers=sum(s.owner_kind.value == 'container' for s in scene.shapes),
                directed_tp=sorted(unique & expected), directed_fp=sorted(unique - expected),
                directed_fn=sorted(expected - unique), duplicate_directed=len(actual)-len(unique),
                undirected=undirected, labels=labels,
                correct_labels=sum(r['exact'] for r in labels),
                wrong_labels=sum(bool(r['actual']) and not r['exact'] for r in labels))


def run():
    verify_lock()
    out = BASE / 'run'
    out.mkdir(parents=True, exist_ok=False)
    records = []
    for path in sorted(ANNOTATIONS.glob('*.json')):
        data, rgb = load_annotation(path, ROOT)
        global_candidates = proposals(rgb, data['scope'])
        local_candidates = proposals(rgb, data['scope'], local=True)
        rec = dict(id=data['id'], annotation_sha256=digest(path), source_sha256=data['source_sha256'],
                   scope=data['scope'], global_proposals=proposal_metrics(global_candidates, data),
                   local_proposals=proposal_metrics(local_candidates, data), arms={})
        for name, candidate, exact in [('r6', global_candidates, False),
                                       ('global-oracle', global_candidates, False),
                                       ('local-oracle', local_candidates, False),
                                       ('geometry-oracle', global_candidates, True)]:
            pp = out / f'{data["id"]}-{name}.pptx'
            if name == 'r6':
                h, w = rgb.shape[:2]
                roi = tuple(v / (w, h)[i % 2] for i, v in enumerate(data['scope']))
                # Baseline ends with the same post-OCR identity filter as R6.
                from image_to_editable_ppt.region.identity import filter_identity
                traced, trace, _ = trace_scene(candidate.scene, rgb, roi, transparent_gaps=True)
                labeled, text = recover_labels(traced, rgb)
                scene, identity = filter_identity(labeled, rgb, roi)
                audit = dict(tracing=trace, text=text, identity=identity)
                acceptance = None
                id_map = match(candidate, data)
            else:
                accepted, acceptance = accept_oracle(candidate, data, exact_geometry=exact)
                scene, audit = observe_accepted(accepted, rgb, data['scope'])
                acceptance['parents'] = accepted.parents
                id_map = None
            normalized, scale = normalize_scene(scene)
            emitted, emission = write_native(normalized, pp, styles=sample_shape_styles(rgb, scene))
            record = dict(metrics=scene_metrics(scene, data, id_map),
                          emitted_metrics=scene_metrics(emitted, data, id_map),
                          acceptance=acceptance, observation=audit, emission=emission,
                          source_scene=asdict(scene), emitted_scene=asdict(emitted), normalization_scale=scale,
                          pptx_sha256=digest(pp))
            rec['arms'][name] = record
            save(pp.with_suffix('.json'), record)
            print(data['id'], name, {k: record['metrics'][k] for k in
                                    ('nodes', 'containers', 'directed_tp', 'directed_fp', 'correct_labels', 'wrong_labels')}, flush=True)
        for name, candidate in [('global', global_candidates), ('local', local_candidates)]:
            overlay(rgb, [(s.id, box_tuple(s), s.owner_kind.value) for s in candidate.scene.shapes],
                    out / f'{data["id"]}-{name}-proposals.png', data['scope'])
        records.append(rec)
        save(out / f'{data["id"]}-evidence.json', rec)
    verify_lock()
    save(out / 'results.json', dict(schema='r7_oracle_evidence_v1', lock_sha256=digest(LOCK),
                                  population='consumed_development', promotion=False, records=records))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('mode', choices=['review-annotations', 'freeze', 'run'])
    mode = p.parse_args().mode
    {'review-annotations': review_annotations, 'freeze': freeze, 'run': run}[mode]()
