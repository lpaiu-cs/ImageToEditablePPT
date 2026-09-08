"""R10-O: RGB-derived spatial OCR owners, optional separately logged C-v2."""
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
    from image_to_editable_ppt.research.spatial_ocr_owners import apply_observations
    from image_to_editable_ppt.region.tracing import trace_scene
    from image_to_editable_ppt.v3.text.ocr import _load_engine
    from diagnose_spatial_ocr_owners import observe
    import cv2
    cv2.setNumThreads(1)
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
    replayed, _, _ = trace_scene(scene,rgb,(0,0,1,1),transparent_gaps=True)
    canonical = lambda value: json.loads(json.dumps(asdict(value)))
    if canonical(replayed)['connectors'] != canonical(scene)['connectors']:
        raise ValueError('original trace replay differs from frozen source')
    owners=[dict(id=s.id,bbox=[s.bbox.x0,s.bbox.y0,s.bbox.x1,s.bbox.y1])
            for s in scene.shapes if s.shape_kind.value=='label_anchor']
    observed=observe(rgb,owners,_load_engine())
    selected,owner_audit=apply_observations(scene,rgb,observed)
    if any(s not in scene.shapes for s in selected.shapes):
        raise ValueError('surviving owner fields changed')
    if identity['centerline']:
        scene, _, tracing_audit=trace_with_centerlines(selected,rgb)
    else:
        scene, tracing_audit, _=trace_scene(selected,rgb,(0,0,1,1),transparent_gaps=True)
    normalized, scale = normalize_scene(scene)
    emitted, emission = write_label_anchor_native(normalized, output, styles=sample_shape_styles(rgb, scene))
    report = dict(schema='research_spatial_ocr_owners_v1', mode='image_derived_spatial_ocr',
        source_sha256=identity['image_sha256'], source_size=[scene.image_size.width, scene.image_size.height],
        source_scene=asdict(scene), emitted_scene=asdict(emitted), normalization_scale=scale,
        emission=emission, owner_audit=owner_audit, spatial_ocr=observed, tracing_audit=tracing_audit, centerline_enabled=identity['centerline'],
        counts=dict(nodes=sum(s.owner_kind.value == 'node' for s in emitted.shapes),
                    containers=sum(s.owner_kind.value == 'container' for s in emitted.shapes),
                    connectors=len(emitted.connectors), labels=sum(bool(s.label) for s in emitted.shapes),
                    omitted_connectors=len(emission['rejected_connectors'])))
    save(output.with_suffix('.region.json'), report)
    save(output.with_suffix('.io.json'), dict(python_read_paths=sorted(reads), denied_paths=denied,
                                           boundary='Python audit hook; not an OS sandbox'))
    print(json.dumps(report['counts']))


def run(out, centerline=False):
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
              ('native_emit.py', 'image_only_guard.py', 'label_anchor_native.py', 'source_centerline_v2.py', 'spatial_ocr_owners.py', 'duplicate_owner_observations.py')]
    files += [Path(__file__).resolve(), ROOT / 'docs/r10_spatial_ocr_owner_spec.md', ROOT / 'docs/r10_spatial_ocr_selection_v1.md', ROOT / 'tools/diagnose_spatial_ocr_owners.py', ROOT / 'tests/test_spatial_ocr_owners.py']
    code = {str(p.relative_to(ROOT)): digest(p) for p in files}
    import rapidocr_onnxruntime
    package=Path(rapidocr_onnxruntime.__file__).parent
    models={str(p):digest(p) for p in (package/'models').glob('*.onnx')}
    save(out / 'lock.json', dict(source_arm='frozen_A-T', models_sha256=models, centerline_enabled=centerline,
        source_manifest_sha256=digest(reference_path), source_results_sha256=digest(baseline / 'results.json'),
        runtime_sha256=code, intervention='spatial_OCR_owner_selection'+('_plus_C_v2' if centerline else '_only'),
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
            input=json.dumps(dict(image_sha256=previous['source_sha256'], scene_sha256=digest(input_scene),centerline=centerline)),
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
    save(out / 'results.json', dict(mode='R10 spatial OCR owner intervention',
         lock_sha256=digest(out / 'lock.json'), records=records))
    if any(r['returncode'] != 0 for r in records):
        raise RuntimeError('inference subprocess failure; see results.json')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['run', 'worker'])
    parser.add_argument('--image', type=Path)
    parser.add_argument('--centerline', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.mode == 'worker':
        worker(args.image, args.output)
    else:
        run(args.output,args.centerline)




