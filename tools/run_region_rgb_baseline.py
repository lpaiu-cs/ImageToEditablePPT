"""공통 RGB-only 개발 subset의 기존 region 기준선. GT 평가는 별도 프로세스다."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, data):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(data, stream, indent=2, ensure_ascii=False)


def worker(image, output):
    import cv2
    from image_to_editable_ppt.region.convert import convert_region
    from image_to_editable_ppt.research.image_only_guard import install_guard
    cv2.setNumThreads(1)
    reads, denied = install_guard(image, output.parent, ROOT / 'src')
    result = convert_region(image, output, region=(0, 0, 1, 1))
    save(output.with_suffix('.io.json'), dict(
        python_read_paths=sorted(reads), denied_paths=denied,
        boundary='Python audit hook; not an OS sandbox', result=result))
    print(json.dumps(result))


def run(manifest, out):
    rows = json.loads(manifest.read_text(encoding='utf-8'))
    if len({r['id'] for r in rows}) != len(rows):
        raise ValueError('duplicate input identity')
    for row in rows:
        if set(row) != {'id', 'image', 'image_sha256'} or digest(row['image']) != row['image_sha256']:
            raise ValueError('RGB-only manifest/hash contract')
    out.mkdir(parents=True, exist_ok=False)
    images = out / 'rgb'
    images.mkdir()
    outputs = out / 'pptx'
    outputs.mkdir()
    runtime = {str(p.relative_to(ROOT)): digest(p) for p in (ROOT / 'src/image_to_editable_ppt/region').glob('*.py')}
    save(out / 'lock.json', dict(input_manifest_sha256=digest(manifest), runtime_sha256=runtime,
         runner_sha256=digest(__file__), guard_sha256=digest(ROOT / 'src/image_to_editable_ppt/research/image_only_guard.py'),
         roi=[0, 0, 1, 1], ocr=True, styles=True,
         population='shared synthetic validation diagnostic; not unseen acceptance',
         source_identity=[dict(id=r['id'], sha256=r['image_sha256']) for r in rows]))
    records = []
    for index, row in enumerate(rows):
        name = f'{index:03d}'
        image = images / f'{name}.png'
        payload = Path(row['image']).read_bytes()
        if hashlib.sha256(payload).hexdigest() != row['image_sha256']:
            raise ValueError('source changed after initial validation')
        with image.open('xb') as stream:
            stream.write(payload)
        output = outputs / f'{name}.pptx'
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
        p = subprocess.run([sys.executable, str(Path(__file__).resolve()), 'worker',
                            '--image', str(image.resolve()), '--output', str(output.resolve())],
                           cwd=ROOT, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=180)
        rec = dict(id=row['id'], slot=name, source_sha256=row['image_sha256'],
                   returncode=p.returncode, stdout=p.stdout, stderr=p.stderr)
        if p.returncode == 0:
            rec.update(report=json.loads(output.with_suffix('.region.json').read_text(encoding='utf-8')),
                       report_sha256=digest(output.with_suffix('.region.json')), pptx_sha256=digest(output),
                       io=json.loads(output.with_suffix('.io.json').read_text(encoding='utf-8')))
        records.append(rec)
        print(name, rec.get('report', {}).get('counts', p.stderr[-300:]), flush=True)
    assert all(digest(ROOT / p) == sha for p, sha in runtime.items())
    save(out / 'results.json', dict(mode='R6 image-only full-ROI baseline', lock_sha256=digest(out / 'lock.json'), records=records))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['run', 'worker'])
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--image', type=Path)
    args = parser.parse_args()
    if args.mode == 'worker': worker(args.image, args.output)
    else: run(args.manifest, args.output)
