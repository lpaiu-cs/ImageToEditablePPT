"""R8-A frozen predicted scenes: change native text-owner attachment only."""
import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from run_region_rgb_baseline import ROOT, digest, save

SOURCES = {
    'predicted': 'benchmarks/region_r8_predicted_owners_baseline.json',
    'ocr': 'benchmarks/region_r8t_text_only_ocr.json',
}


def worker(image, output):
    import numpy as np
    from PIL import Image
    from image_to_editable_ppt.research.image_only_guard import install_guard
    from image_to_editable_ppt.research.native_emit import load_scene
    from image_to_editable_ppt.research.label_anchor_native import write_label_anchor_native
    from image_to_editable_ppt.region.geometry import normalize_scene
    from image_to_editable_ppt.v3.emit import sample_shape_styles
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
    normalized, scale = normalize_scene(scene)
    emitted, emission = write_label_anchor_native(normalized, output, styles=sample_shape_styles(rgb, scene))
    report = dict(schema='research_label_anchor_attachment_v1', mode='cached_scene_native_only',
        source_sha256=identity['image_sha256'], source_size=[scene.image_size.width, scene.image_size.height],
        source_scene=asdict(scene), emitted_scene=asdict(emitted), normalization_scale=scale,
        emission=emission,
        counts=dict(nodes=sum(s.owner_kind.value == 'node' for s in emitted.shapes),
                    containers=sum(s.owner_kind.value == 'container' for s in emitted.shapes),
                    connectors=len(emitted.connectors), labels=sum(bool(s.label) for s in emitted.shapes),
                    omitted_connectors=len(emission['rejected_connectors'])))
    save(output.with_suffix('.region.json'), report)
    save(output.with_suffix('.io.json'), dict(python_read_paths=sorted(reads), denied_paths=denied,
                                           boundary='Python audit hook; not an OS sandbox'))
    print(json.dumps(report['counts']))


def run(source_arm, out):
    reference_path = ROOT / SOURCES[source_arm]
    reference = json.loads(reference_path.read_text())
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
              ('native_emit.py', 'image_only_guard.py', 'label_anchor_native.py')]
    files += [Path(__file__).resolve(), ROOT / 'docs/label_anchor_attachment_r8a_spec.md']
    code = {str(p.relative_to(ROOT)): digest(p) for p in files}
    save(out / 'lock.json', dict(source_arm=source_arm,
        source_manifest_sha256=digest(reference_path), source_results_sha256=digest(baseline / 'results.json'),
        runtime_sha256=code, intervention='label_anchor_native_attachment_only',
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
    save(out / 'results.json', dict(mode='R8-A '+source_arm+' frozen scene native-only intervention',
         lock_sha256=digest(out / 'lock.json'), records=records))
    if any(r['returncode'] != 0 for r in records):
        raise RuntimeError('inference subprocess failure; see results.json')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['run', 'worker'])
    parser.add_argument('--source-arm', choices=list(SOURCES))
    parser.add_argument('--image', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.mode == 'worker':
        worker(args.image, args.output)
    else:
        run(args.source_arm, args.output)
