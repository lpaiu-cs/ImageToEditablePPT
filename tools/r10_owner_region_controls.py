"""Independent synthetic owner-region RGB fixtures; annotations never enter propose."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build(out, font_path):
    out.mkdir(parents=True, exist_ok=False)
    rows = []
    modes = ['two_children', 'square_child', 'thin_child', 'small_child',
             'photo_icon', 'open_child']
    for mode in modes:
        for scale in [1, 2]:
            for aa in [1, 4]:
                r = scale * aa
                im = Image.new('RGB', (1000*r, 600*r), 'white')
                draw = ImageDraw.Draw(im)
                parent = [80, 80, 480, 280]
                fill = [220, 240, 220]
                children, words = [], []

                def box(bounds, color, kind='diagram', closed=True):
                    draw.rectangle(tuple(v*r for v in bounds), fill=tuple(color), outline='black', width=r)
                    if not closed:
                        x, y, _, _ = bounds
                        draw.rectangle(((x+20)*r, (y-2)*r, (x+35)*r, (y+2)*r), fill=tuple(color))
                    children.append(dict(bbox=bounds, kind=kind, closed=closed, fill=color))

                def word(text, xy, owner, size=18):
                    font = ImageFont.truetype(str(font_path), size*r)
                    p = (xy[0]*r, xy[1]*r)
                    bounds = draw.textbbox(p, text, font=font)
                    draw.text(p, text, font=font, fill='black')
                    words.append(dict(text=text, bbox=[v/aa for v in bounds], owner=owner))

                draw.rectangle(tuple(v*r for v in parent), fill=tuple(fill), outline='black', width=r)
                word('PARENT HEADER', (100, 88), 'parent')
                if mode == 'two_children':
                    box([90, 125, 270, 270], [240, 170, 180])
                    box([280, 125, 470, 270], [240, 170, 180])
                    word('ALPHA ONLY', (105, 165), 'child0')
                    word('BETA ONLY', (295, 165), 'child1')
                elif mode == 'square_child':
                    box([105, 120, 255, 270], [240, 170, 180])
                    word('SQUARE', (115, 165), 'child0')
                elif mode == 'thin_child':
                    box([100, 150, 450, 168], [240, 170, 180])
                    word('THIN CHILD', (115, 150), 'child0', 12)
                elif mode == 'small_child':
                    box([110, 145, 156, 173], [240, 170, 180])
                    word('ID', (120, 146), 'child0', 15)
                elif mode == 'open_child':
                    box([100, 125, 460, 270], [240, 170, 180], closed=False)
                    word('OPEN CHILD', (135, 170), 'child0')
                else:
                    box([90, 125, 300, 270], [240, 170, 180], 'photo')
                    # A procedural photo-like texture, not an external photograph.
                    rng = np.random.default_rng(1907)
                    texture = rng.integers(60, 220, (110*r, 200*r, 3), dtype=np.uint8)
                    im.paste(Image.fromarray(texture), (95*r, 155*r))
                    box([315, 125, 470, 270], [180, 200, 240], 'icon')
                    draw.ellipse((355*r, 165*r, 430*r, 240*r), fill=(30, 90, 160))
                    word('PHOTO ID', (105, 130), 'child0')
                    word('ICON ID', (325, 130), 'child1')
                if aa != 1:
                    im = im.resize((1000*scale, 600*scale), Image.Resampling.LANCZOS)
                key = f'{mode}-s{scale}-aa{aa}'
                path = out / (key+'.png')
                im.save(path)
                for child in children:
                    child['bbox'] = [v*scale for v in child['bbox']]
                rows.append(dict(id=key, rgb=path.name, sha256=sha(path), mode=mode,
                                 parent_bbox=[v*scale for v in parent], parent_fill=fill,
                                 children=children, words=words))
    (out/'manifest.json').write_text(json.dumps(rows, indent=2))
    lock = dict(count=len(rows), manifest_sha256=sha(out/'manifest.json'),
                builder_sha256=sha(__file__), font_sha256=sha(font_path),
                contract='Synthetic annotations are evaluator-only. Parent must not absorb child words/colors; omission is allowed. Open child is a scope diagnostic. Non-diagram child text is not a parent label.')
    (out/'lock.json').write_text(json.dumps(lock, indent=2))
    print(json.dumps(lock))


def run(fixtures, source, out):
    out.mkdir(parents=True, exist_ok=False)
    lock = json.loads((fixtures/'lock.json').read_text())
    assert sha(fixtures/'manifest.json') == lock['manifest_sha256']
    snapshot = out/'proposal_snapshot.py'
    snapshot.write_bytes(source.read_bytes())
    spec = importlib.util.spec_from_file_location('owner_proposal_snapshot', snapshot)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rows = []
    for case in json.loads((fixtures/'manifest.json').read_text()):
        path = fixtures/case['rgb']
        assert sha(path) == case['sha256']
        rgb = np.array(Image.open(path))
        before = rgb.copy()
        selected, audit = module.propose(rgb)  # No annotations supplied.
        assert np.array_equal(before, rgb)
        boxes = [p['bbox'] for p in selected]
        x0, y0, x1, y1 = case['parent_bbox']
        mask = np.zeros(rgb.shape[:2], dtype=bool)
        mask[y0+4:y1-4, x0+4:x1-4] = True
        naive = np.median(rgb[mask], axis=0).tolist()
        child_records = []
        for child in case['children']:
            a, b, c, d = child['bbox']
            mask[max(0,b-4):d+4, max(0,a-4):c+4] = False
            s = rgb.shape[0]/360
            w, h = c-a, d-b
            reasons = []
            if w < 32*s: reasons.append('width')
            if h < 16*s: reasons.append('height')
            if not 1.15 <= w/h <= 15: reasons.append('aspect')
            overlap = max([module._iou(child['bbox'], box) for box in boxes], default=0)
            child_records.append(dict(**child, nominal_filter_failures=reasons,
                                      best_selected_iou=overlap))
        owner_median = np.median(rgb[mask], axis=0).tolist()
        rows.append(dict(id=case['id'], selected_boxes=boxes, children=child_records,
                         naive_parent_median=naive, annotation_excluded_parent_median=owner_median,
                         expected_parent_fill=case['parent_fill'], words=case['words'],
                         audit=audit))
    report = dict(source_sha256=sha(snapshot), fixture_lock_sha256=sha(fixtures/'lock.json'),
                  runner_sha256=sha(__file__), rows=rows,
                  scope='Geometry and synthetic contamination diagnostic only; no OCR or owner-exclusion implementation tested.')
    (out/'results.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!='rows'}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['build', 'run'])
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--fixtures', type=Path)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--font', type=Path, default=Path('C:/Windows/Fonts/arial.ttf'))
    args = parser.parse_args()
    if args.mode == 'build':
        build(args.out, args.font)
    else:
        run(args.fixtures, args.source, args.out)
