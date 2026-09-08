"""Evaluate frozen owner-region RGB against snapshot P2 masks, without OCR."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
from PIL import Image


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def snapshot(path, out, name):
    target = out/(name+'.py')
    target.write_bytes(path.read_bytes())
    spec = importlib.util.spec_from_file_location(name, target)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, sha(target)


def run(fixtures, source, out):
    out.mkdir(parents=True, exist_ok=False)
    p, psha = snapshot(source/'closed_rect_proposals.py', out, 'proposal_snapshot')
    m, msha = snapshot(source/'closed_owner_regions.py', out, 'owner_snapshot')
    lock = json.loads((fixtures/'lock.json').read_text())
    assert sha(fixtures/'manifest.json') == lock['manifest_sha256']
    rows = []
    for case in json.loads((fixtures/'manifest.json').read_text()):
        path = fixtures/case['rgb']
        assert sha(path) == case['sha256']
        rgb = np.array(Image.open(path)); before = rgb.copy()
        selected, _ = p.propose(rgb)
        candidate = max(selected, key=lambda c:p._iou(c['bbox'], case['parent_bbox']), default=None)
        if candidate is None or p._iou(candidate['bbox'], case['parent_bbox']) < .9:
            rows.append(dict(id=case['id'], parent_missing=True)); continue
        own, excluded, fill, audit = m.owner_region(rgb, candidate, m.closed_regions(rgb))
        assert np.array_equal(rgb, before)
        word_stats = []
        for word in case['words']:
            a,b,c,d = word['bbox']
            a,b,c,d = int(np.floor(a)),int(np.floor(b)),int(np.ceil(c)),int(np.ceil(d))
            word_stats.append(dict(**word, excluded_fraction=float(excluded[b:d,a:c].mean()),
                                   own_fraction=float(own[b:d,a:c].mean())))
        children = []
        for child in case['children']:
            a,b,c,d = child['bbox']
            children.append(dict(**child, interior_owned_fraction=float(own[b+4:d-4,a+4:c-4].mean())))
        rows.append(dict(id=case['id'], parent_missing=False, fill=fill,
                         correct_fill=list(fill)==case['parent_fill'] if fill is not None else None,
                         words=word_stats, children=children, audit=audit))
    result = dict(proposal_sha256=psha, owner_sha256=msha,
                  fixture_lock_sha256=sha(fixtures/'lock.json'), runner_sha256=sha(__file__),
                  scope='Mask coverage and fill only. Annotation bboxes are evaluator-only; no OCR execution.', rows=rows)
    (out/'results.json').write_text(json.dumps(result, indent=2))
    print(json.dumps({k:v for k,v in result.items() if k!='rows'}))
    for r in rows:
        print(r['id'], 'MISSING' if r['parent_missing'] else
              str((r['fill'], [(w['text'], round(w['excluded_fraction'],3)) for w in r['words']],
                   [round(c['interior_owned_fraction'],3) for c in r['children']])))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--fixtures',type=Path,required=True)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args = parser.parse_args()
    run(args.fixtures,args.source,args.out)
