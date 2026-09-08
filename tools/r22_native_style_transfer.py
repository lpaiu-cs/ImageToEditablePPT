"""Matched native style intervention; reuse frozen detector and metric contracts."""
import argparse
import json
from pathlib import Path
import random
import time
import torch
from r19_instance_detector import (ROOT, digest, save, verify, code_lock, environment,
    read_rgb, image_tensor, target, new_model, observe, board, representative,
    geometry, summary, object_counts, select_threshold, write_shapes, load_trained)


def pairs(plain, styled):
    originals = json.loads(plain.read_text())['records']
    variants = json.loads(styled.read_text())['records']
    lookup = {r['original_id']: r for r in variants}
    assert len(lookup) == len(variants) == len(originals) == 384
    result = []
    for r in originals:
        s = lookup[r['id']]
        assert all(r[k] == s[k] for k in ('split', 'family', 'stage'))
        contract = lambda row: [(o['id'], o['kind'], o['bbox'], o['role'], o.get('parent_id')) for o in row['objects']]
        assert contract(r) == contract(s), r['id']
        result.append((r, s))
    return result


def schedule(count, steps=1800, batch=4):
    geometry_rng = random.Random(1901)
    style_rng = random.Random(2201)
    for _ in range(steps):
        yield [(geometry_rng.randrange(count), int(style_rng.random() < .5)) for _ in range(batch)]


def files(plain, styled, rows):
    paths = [plain, styled, Path(__file__), ROOT / 'docs/r22_native_style_transfer_spec.md']
    return {**code_lock(), **{str(p.resolve()): digest(p) for p in paths},
            **{r['image']: r['image_sha256'] for pair in rows for r in pair}}


def train(plain, styled, control, output):
    env = environment()
    rows = [p for p in pairs(plain, styled) if p[0]['split'] == 'train']
    assert len(rows) == 288
    gate = json.loads((control / 'training.json').read_text())
    assert gate['control'] and gate['control_gate']
    verify(json.loads((control / 'lock.json').read_text()))
    output.mkdir(parents=True, exist_ok=False)
    lock = dict(files=files(plain, styled, rows), control=False, manifest=str(plain.resolve()),
        style_manifest=str(styled.resolve()), environment=env, steps=1800, batch=4,
        seed=1901, style_seed=2201, learning_rate=.0003, weight_decay=.0001, lr_drop_step=1200)
    lock['files'].update({str((control / n).resolve()): digest(control / n) for n in ('training.json', 'lock.json')})
    verify(lock)
    model = new_model(pretrained=True).cuda()
    backbone = Path(torch.hub.get_dir()) / 'checkpoints/resnet50-0676ba61.pth'
    lock['files'][str(backbone.resolve())] = digest(backbone)
    save(output / 'lock.json', lock)
    cached = []
    for r, s in rows:
        images = [read_rgb(v['image']) for v in (r, s)]
        assert images[0].shape == images[1].shape == (600, 960, 3)
        cached.append(([image_tensor(im) for im in images], target(r['objects'], (960, 600))))
    optimizer = torch.optim.AdamW(model.parameters(), lr=.0003, weight_decay=.0001)
    samples = representative([r for r, _ in rows])
    sample_ids = {r['id'] for r in samples}
    samples = [(r, s) for r, s in rows if r['id'] in sample_ids]
    losses, snapshots = [], []
    started = time.monotonic()
    for step, selection in enumerate(schedule(len(cached)), 1):
        model.train()
        images = [cached[i][0][v].cuda() for i, v in selection]
        targets = [{k: t.cuda() for k, t in cached[i][1].items()} for i, _ in selection]
        optimizer.zero_grad(set_to_none=True)
        parts = model(images, targets)
        loss = sum(parts.values())
        if not torch.isfinite(loss):
            raise RuntimeError('Nonfinite training loss')
        loss.backward()
        optimizer.step()
        row = dict(step=step, loss=float(loss.detach()), parts={k: float(v.detach()) for k, v in parts.items()})
        losses.append(row)
        if step % 25 == 0:
            print(json.dumps(dict(**row, seconds=round(time.monotonic() - started, 1))), flush=True)
        if step in (100, 600, 1200, 1800):
            folder = output / f'step-{step:04d}'
            folder.mkdir()
            checks = []
            for pair in samples:
                for variant, r in zip(('plain', 'style'), pair):
                    candidates, _ = observe(model, r['image'])
                    kept = [o for o in candidates if o['confidence'] >= .5]
                    board(r['image'], kept, folder / f'{variant}--{r["id"]}.png')
                    checks.append(dict(id=r['id'], variant=variant, objects=kept, **object_counts(kept, r['objects'])))
            snap = dict(step=step, rows=checks, strict=summary(checks))
            snapshots.append(snap)
            save(folder / 'checks.json', snap)
            print(json.dumps(dict(snapshot=step, strict=snap['strict'])), flush=True)
        if step == 1200:
            for group in optimizer.param_groups:
                group['lr'] = .0001
    verify(lock)
    torch.save(model.cpu().state_dict(), output / 'final.pt')
    save(output / 'training.json', dict(control=False, control_gate=None, losses=losses, snapshots=snapshots,
        checkpoint_sha256=digest(output / 'final.pt'), lock_sha256=digest(output / 'lock.json'),
        seconds=time.monotonic() - started, peak_gpu_bytes=torch.cuda.max_memory_allocated()))


def evaluate(plain, styled, trained, output):
    env = environment()
    rows = pairs(plain, styled)
    model, prior = load_trained(trained)
    assert not prior['control']
    output.mkdir(parents=True, exist_ok=False)
    lock = dict(files={**prior['files'], **files(plain, styled, rows),
        str((trained / 'final.pt').resolve()): digest(trained / 'final.pt')}, environment=env)
    verify(lock)
    save(output / 'lock.json', lock)
    cal = [(r, observe(model, r['image'])[0]) for pair in rows if pair[0]['split'] == 'calibration' for r in pair]
    assert len(cal) == 96
    checks = {str(t): summary([object_counts([o for o in obs if o['confidence'] >= t], r['objects'])
        for r, obs in cal]) for t in (.3, .5, .7, .85, .95, .99)}
    threshold, passed = select_threshold(checks)
    save(output / 'calibration.json', dict(threshold=threshold, gate_pass=passed, checks=checks))
    # All paired eval pixels are consumed after this fixed checkpoint's calibration decision.
    arms = {}
    for index, variant in enumerate(('plain', 'style')):
        observed = []
        for pair in rows:
            if pair[0]['split'] != 'eval':
                continue
            r = pair[index]
            candidates, size = observe(model, r['image'])
            kept = [o for o in candidates if o['confidence'] >= threshold]
            fixed = [o for o in candidates if o['confidence'] >= .95]
            folder = output / variant / pair[0]['id']
            folder.mkdir(parents=True)
            write_shapes(kept, size, folder / 'result.pptx')
            board(r['image'], kept, folder / 'inspection.png')
            observed.append(dict(id=pair[0]['id'], image=r['image'], family=r['family'], stage=r['stage'],
                objects=kept, all_candidates=candidates, **object_counts(kept, r['objects']),
                fixed95=object_counts(fixed, r['objects']), coverage=geometry(candidates, r['objects']),
                geometry=geometry(kept, r['objects']), pptx_sha256=digest(folder / 'result.pptx')))
        assert len(observed) == 48
        arms[variant] = dict(**summary(observed), rows=observed,
            fixed95=summary([r['fixed95'] for r in observed]), coverage=summary([r['coverage'] for r in observed]),
            geometry=summary([r['geometry'] for r in observed]), negative_fp=sum(r['fp'] for r in observed if r['stage'] == 'negative'),
            per_family={f: summary([r for r in observed if r['family'] == f]) for f in sorted({r['family'] for r in observed})})
    verify(lock)
    save(output / 'results.json', dict(arms=arms, threshold=threshold, calibration_gate=passed,
        manifest_sha256=digest(plain), style_manifest_sha256=digest(styled), lock_sha256=digest(output / 'lock.json'),
        scope='Exposed geometry paired development evaluation, not independent product validation.'))
    print(json.dumps({a: {k: v for k, v in r.items() if k != 'rows'} for a, r in arms.items()}, indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('mode', choices=['train', 'evaluate'])
    for name in ('plain', 'styled', 'trained', 'control', 'output'):
        p.add_argument('--' + name, type=Path, required=name in ('plain', 'styled', 'output'))
    a = p.parse_args()
    if a.mode == 'train':
        train(a.plain, a.styled, a.control, a.output)
    else:
        evaluate(a.plain, a.styled, a.trained, a.output)
