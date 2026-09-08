"""R9-C v2: source-only path intervention on frozen A-T scenes."""
import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from run_region_rgb_baseline import ROOT, digest, save
sys.path.insert(0, str(ROOT / 'src'))



def worker(image, output):
    import numpy as np
    from PIL import Image
    from image_to_editable_ppt.research.image_only_guard import install_guard
    from image_to_editable_ppt.research.native_emit import load_scene
    from image_to_editable_ppt.research.label_anchor_native import write_label_anchor_native
    from image_to_editable_ppt.region.geometry import normalize_scene
    from image_to_editable_ppt.v3.emit import sample_shape_styles
    from image_to_editable_ppt.research.source_centerline_v2 import trace_with_centerlines
    import numpy.ma  # preload before the file-read boundary
    reads, denied = install_guard(image, output.parent, ROOT / 'src')
    identity = json.loads(sys.stdin.read())
    input_scene = output.with_suffix('.input.json')
    if digest(image) != identity['image_sha256'] or digest(input_scene) != identity['scene_sha256']:
        raise ValueError('frozen input SHA mismatch')
    scene = load_scene(input_scene)
    with Image.open(image) as im:
        if im.mode != 'RGB' or im.size != (scene.image_size.width, scene.image_size.height):
            raise ValueError('source RGB contract')
        rgb = np.asarray(im)
    refined, replayed, centerline_audit = trace_with_centerlines(scene, rgb)
    canonical = lambda value: json.loads(json.dumps(asdict(value)))
    if canonical(replayed)['connectors'] != canonical(scene)['connectors']:
        raise ValueError('original trace replay differs from frozen source')
    if refined.shapes != scene.shapes:
        raise ValueError('owner or OCR mutation')
    for old, new in zip(scene.connectors, refined.connectors, strict=True):
        a, b = asdict(old), asdict(new)
        a.pop('path_points'); b.pop('path_points')
        if a != b:
            raise ValueError('non-path connector mutation')
    scene = refined
    normalized, scale = normalize_scene(scene)
    emitted, emission = write_label_anchor_native(normalized, output, styles=sample_shape_styles(rgb, scene))
    report = dict(schema='research_source_centerline_v2', mode='cached_owners_rgb_path_only',
        source_sha256=identity['image_sha256'], source_size=[scene.image_size.width, scene.image_size.height],
        source_scene=asdict(scene), emitted_scene=asdict(emitted), normalization_scale=scale,
        emission=emission, centerline_audit=centerline_audit,
        counts=dict(nodes=sum(s.owner_kind.value == 'node' for s in emitted.shapes),
                    containers=sum(s.owner_kind.value == 'container' for s in emitted.shapes),
                    connectors=len(emitted.connectors), labels=sum(bool(s.label) for s in emitted.shapes),
                    omitted_connectors=len(emission['rejected_connectors'])))
    save(output.with_suffix('.region.json'), report)
    save(output.with_suffix('.io.json'), dict(python_read_paths=sorted(reads), denied_paths=denied,
                                           boundary='Python audit hook; not an OS sandbox'))
    print(json.dumps(report['counts']))


def run(out):
    reference_path = ROOT / 'benchmarks/region_r8a_attachment.json'
    reference = json.loads(reference_path.read_text())['arms']['t']
    baseline = ROOT / reference['artifact_root']
    if digest(baseline / 'results.json') != reference['files']['results.json']:
        raise ValueError('not the frozen source baseline')
    prior = json.loads((baseline / 'results.json').read_text(encoding='utf-8'))
    out.mkdir(parents=True, exist_ok=False)
    (out / 'rgb').mkdir()
    (out / 'pptx').mkdir()
    files = list((ROOT / 'src/image_to_editable_ppt/region').glob('*.py'))
    files += list((ROOT / 'src/image_to_editable_ppt/v3/emit').glob('*.py'))
    files += [ROOT / 'src/image_to_editable_ppt/research' / name for name in
              ('native_emit.py', 'image_only_guard.py', 'label_anchor_native.py', 'source_centerline_v2.py')]
    files += [Path(__file__).resolve(), ROOT / 'docs/r9_source_centerline_v2_spec.md', ROOT / 'docs/r9_source_centerline_spec.md', ROOT / 'tests/test_source_centerline_v2.py']
    code = {str(p.relative_to(ROOT)): digest(p) for p in files}
    save(out / 'lock.json', dict(source_arm='frozen_A-T',
        source_manifest_sha256=digest(reference_path), source_results_sha256=digest(baseline / 'results.json'),
        runtime_sha256=code, intervention='source_centerline_v2_path_only_D_off',
        population='cached shared synthetic validation diagnostic; not unseen acceptance'))
    records = []
    for previous in prior['records']:
        slot = previous['slot']
        image = out / 'rgb' / f'{slot}.png'
        data = (baseline / 'rgb' / f'{slot}.png').read_bytes()
        if hashlib.sha256(data).hexdigest() != previous['source_sha256']:
            raise ValueError('baseline RGB changed')
        with image.open('xb') as stream:
            stream.write(data)
        output = out / 'pptx' / f'{slot}.pptx'
        input_scene = output.with_suffix('.input.json')
        save(input_scene, previous['report']['source_scene'])
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
        proc = subprocess.run([sys.executable, str(Path(__file__).resolve()), 'worker', '--image',
            str(image.resolve()), '--output', str(output.resolve())], cwd=ROOT, env=env, timeout=180,
            input=json.dumps(dict(image_sha256=previous['source_sha256'], scene_sha256=digest(input_scene))),
            capture_output=True, text=True, encoding='utf-8', errors='replace')
        record = dict(id=previous['id'], slot=slot, source_sha256=previous['source_sha256'],
                      returncode=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)
        if proc.returncode == 0:
            record.update(report=json.loads(output.with_suffix('.region.json').read_text(encoding='utf-8')),
                report_sha256=digest(output.with_suffix('.region.json')), pptx_sha256=digest(output),
                io=json.loads(output.with_suffix('.io.json').read_text(encoding='utf-8')))
        records.append(record)
        print(slot, record.get('report', {}).get('counts', proc.stderr[-800:]), flush=True)
    assert all(digest(ROOT / p) == sha for p, sha in code.items())
    save(out / 'results.json', dict(mode='R9-C v2 frozen A-T RGB path-only intervention',
         lock_sha256=digest(out / 'lock.json'), records=records))
    if any(r['returncode'] != 0 for r in records):
        raise RuntimeError('inference subprocess failure; see results.json')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['run', 'worker'])
    parser.add_argument('--image', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.mode == 'worker':
        worker(args.image, args.output)
    else:
        run(args.output)


