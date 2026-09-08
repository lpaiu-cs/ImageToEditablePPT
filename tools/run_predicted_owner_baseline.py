"""연구용 고정 검출 객체와 기존 추적/OCR/native 단계의 결합 기준선."""
import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from run_region_rgb_baseline import ROOT, digest, save


def worker(image, output):
    import cv2
    import numpy as np
    from PIL import Image
    from image_to_editable_ppt.research.image_only_guard import install_guard
    from image_to_editable_ppt.research.predicted_owners import prediction_scene, supported_owner_connections
    from image_to_editable_ppt.region.tracing import trace_scene
    from image_to_editable_ppt.region.text import recover_labels
    from image_to_editable_ppt.region.geometry import normalize_scene
    from image_to_editable_ppt.region.emitter import write_native
    from image_to_editable_ppt.v3.emit import sample_shape_styles
    cv2.setNumThreads(1)
    reads, denied = install_guard(image, output.parent, ROOT / 'src')
    sample = json.loads(sys.stdin.read())
    raw = image.read_bytes()
    if hashlib.sha256(raw).hexdigest() != sample['source_sha256']:
        raise ValueError('RGB hash mismatch')
    import io
    with Image.open(io.BytesIO(raw)) as im:
        if im.mode != 'RGB' or list(im.size) != sample['image_size']:
            raise ValueError('RGB image contract mismatch')
        rgb = np.asarray(im)
    selected = prediction_scene(sample)
    traced, trace, _ = trace_scene(selected, rgb, (0, 0, 1, 1), transparent_gaps=True)
    labeled, text = recover_labels(traced, rgb)
    native_input, unsupported = supported_owner_connections(labeled)
    normalized, scale = normalize_scene(native_input)
    styles = sample_shape_styles(rgb, labeled)
    emitted, emission = write_native(normalized, output, styles=styles)
    emission['unsupported_owner_connectors'] = unsupported
    emission['rejected_connectors'].update(unsupported)
    report = dict(schema='research_predicted_owners_v1', mode='fixed_rgb_prediction_baseline',
        source_sha256=sample['source_sha256'], source_size=sample['image_size'],
        source_scene=asdict(labeled), prediction_scene=asdict(selected),
        emitted_scene=asdict(emitted), normalization_scale=scale,
        tracing=trace, text=text, emission=emission,
        counts=dict(nodes=sum(s.owner_kind.value == 'node' for s in emitted.shapes),
                    containers=sum(s.owner_kind.value == 'container' for s in emitted.shapes),
                    connectors=len(emitted.connectors), labels=sum(bool(s.label) for s in emitted.shapes),
                    omitted_connectors=len(emission['rejected_connectors'])))
    save(output.with_suffix('.region.json'), report)
    save(output.with_suffix('.io.json'), dict(python_read_paths=sorted(reads), denied_paths=denied,
         boundary='Python audit hook; not an OS sandbox'))
    print(json.dumps(report['counts']))


def run(bundle_path, out, allow_legacy):
    from image_to_editable_ppt.research.prediction_handoff import validate_bundle
    bundle = validate_bundle(bundle_path, allow_legacy_research=allow_legacy)
    out.mkdir(parents=True, exist_ok=False)
    (out / 'rgb').mkdir()
    (out / 'pptx').mkdir()
    files = list((ROOT / 'src/image_to_editable_ppt/region').glob('*.py'))
    files += list((ROOT / 'src/image_to_editable_ppt/v3/emit').glob('*.py'))
    files += [ROOT / 'src/image_to_editable_ppt/research' / name for name in
              ('predicted_owners.py', 'prediction_handoff.py', 'image_only_guard.py')]
    files += [Path(__file__).resolve(), ROOT / 'docs/region_predicted_owners_r8_spec.md']
    code = {str(p.relative_to(ROOT)): digest(p) for p in files}
    save(out / 'lock.json', dict(handoff_sha256=digest(bundle_path), payload_sha256=bundle['payload_sha256'],
        runtime_sha256=code, limitations=bundle['payload']['limitations'],
        settings=dict(geometry='unchanged', trace='R6 transparent_gaps', ocr='R6 two-scale',
                      native='R6; explicit label_anchor attachment abstention'),
        population='shared synthetic validation diagnostic; not unseen acceptance'))
    records = []
    for index, sample in enumerate(bundle['payload']['samples']):
        slot = f'{index:03d}'
        image = out / 'rgb' / f'{slot}.png'
        data = Path(sample['source_rgb']['path']).read_bytes()
        if hashlib.sha256(data).hexdigest() != sample['source_rgb']['sha256']:
            raise ValueError('RGB changed after validation')
        with image.open('xb') as stream:
            stream.write(data)
        output = out / 'pptx' / f'{slot}.pptx'
        # Only image identity and model-derived objects enter the inference process.
        request = dict(source_sha256=sample['source_rgb']['sha256'], image_size=sample['image_size'],
                       objects=[{k: o[k] for k in ('id', 'role', 'semantic_kind', 'bbox_xyxy', 'confidence')}
                                for o in sample['objects']])
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
        proc = subprocess.run([sys.executable, str(Path(__file__).resolve()), 'worker', '--image',
                    str(image.resolve()), '--output', str(output.resolve())], cwd=ROOT, env=env,
                    input=json.dumps(request), capture_output=True, text=True, encoding='utf-8',
                    errors='replace', timeout=180)
        record = dict(id=sample['source_record_id'], slot=slot, source_sha256=sample['source_rgb']['sha256'],
                      returncode=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)
        if proc.returncode == 0:
            record.update(report=json.loads(output.with_suffix('.region.json').read_text(encoding='utf-8')),
                report_sha256=digest(output.with_suffix('.region.json')), pptx_sha256=digest(output),
                io=json.loads(output.with_suffix('.io.json').read_text(encoding='utf-8')))
        records.append(record)
        print(slot, record.get('report', {}).get('counts', proc.stderr[-800:]), flush=True)
    assert all(digest(ROOT / p) == sha for p, sha in code.items())
    save(out / 'results.json', dict(mode='fixed RGB prediction + R6 downstream',
         lock_sha256=digest(out / 'lock.json'), records=records))
    if any(r['returncode'] != 0 for r in records):
        raise RuntimeError('One or more inference subprocesses failed; see results.json')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['run', 'worker'])
    parser.add_argument('--bundle', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--image', type=Path)
    parser.add_argument('--allow-legacy-research', action='store_true')
    args = parser.parse_args()
    if args.mode == 'worker':
        worker(args.image, args.output)
    else:
        run(args.bundle, args.output, args.allow_legacy_research)
