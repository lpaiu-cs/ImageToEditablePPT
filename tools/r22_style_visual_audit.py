"""Compare paired source styles against two frozen models using actual COM renders."""
import argparse
from collections import Counter
import json
from pathlib import Path
from PIL import Image, ImageDraw
from r19_outcome_audit import digest, save, verify, match_indices
from r22_native_style_transfer import pairs


def review(plain, styled, baseline, candidate, base_com, new_com, output):
    rows = [pair for pair in pairs(plain, styled) if pair[0]['split'] == 'eval']
    models = []
    for evaluation, com in ((baseline, base_com), (candidate, new_com)):
        result = json.loads((evaluation / 'results.json').read_text())
        verify(json.loads((evaluation / 'lock.json').read_text()))
        assert result['manifest_sha256'] == digest(plain)
        assert result['style_manifest_sha256'] == digest(styled)
        inputs = json.loads((com / 'inputs.json').read_text())
        assert inputs['results_sha256'] == digest(evaluation / 'results.json')
        receipts = {r['id']: r for r in json.loads((com / 'renders/powerpoint_render_manifest.json').read_text(encoding='utf-8-sig'))['records']}
        assert len(receipts) == len(inputs['rows']) == 96
        for row in inputs['rows']:
            receipt = receipts[row['id']]
            assert row['pptx_sha256'] == receipt['pptx_sha256'] == digest(receipt['pptx_path'])
            assert receipt['render_sha256'] == digest(receipt['render_path'])
        models.append((result, receipts))
    output.mkdir(parents=True, exist_ok=False)
    roles, boards = {}, []
    for pair in rows:
        identity = pair[0]['id']
        board = Image.new('RGB', (1440, 660), 'white')
        draw = ImageDraw.Draw(board)
        for i, (variant, record) in enumerate(zip(('plain', 'style'), pair)):
            y = i * 330
            with Image.open(record['image']) as im:
                assert digest(record['image']) == record['image_sha256']
                board.paste(im.convert('RGB').resize((480, 300)), (0, y + 30))
            draw.text((4, y + 4), f'{variant} source {identity}', fill='black')
            for col, (name, (result, receipts)) in enumerate(zip(('R19', 'R22'), models), 1):
                row = next(r for r in result['arms'][variant]['rows'] if r['id'] == identity)
                receipt = receipts[f'{variant}--{identity}']
                with Image.open(receipt['render_path']) as im:
                    assert im.size == (960, 600)
                    board.paste(im.convert('RGB').resize((480, 300)), (480 * col, y + 30))
                draw.text((480 * col + 4, y + 4), f'{name} t{result["threshold"]} TP{row["tp"]} FP{row["fp"]} FN{row["fn"]}', fill='black')
                strict = match_indices(row['objects'], record['objects'])
                geom = match_indices(row['objects'], record['objects'], True)
                candidates = match_indices(row['all_candidates'], record['objects'], True)
                counts = roles.setdefault(name + '_' + variant, {r: Counter() for r in ('node', 'container')})
                for j, obj in enumerate(record['objects']):
                    role = 'container' if obj['id'].startswith('container') else 'node'
                    counts[role].update(expected=1, strict_tp=int(j in strict), geometry_tp=int(j in geom), candidate_tp=int(j in candidates))
        path = output / (identity + '.png')
        board.save(path)
        boards.append(dict(path=str(path.resolve()), sha256=digest(path)))
    save(output / 'audit.json', dict(boards=boards, roles=roles, checked_pptx=192,
        files={str(p.resolve()): digest(p) for p in (Path(__file__), plain, styled,
            baseline / 'results.json', candidate / 'results.json', base_com / 'renders/powerpoint_render_manifest.json', new_com / 'renders/powerpoint_render_manifest.json')},
        scope='Exposed matched geometry; global one-to-one matches assigned to roles, no rematching.'))
    print(json.dumps(roles, indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    for name in ('plain', 'styled', 'baseline', 'candidate', 'base-com', 'new-com', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args()
    review(a.plain, a.styled, a.baseline, a.candidate, a.base_com, a.new_com, a.output)
