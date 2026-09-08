"""Independent Pillow RGB controls; build expectations before observer execution."""
import argparse
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageDraw


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fixture(mode, angle, scale, size, aa):
    resolution = scale * aa
    im = Image.new('RGB', (round(360*resolution),)*2, 'white')
    draw = ImageDraw.Draw(im)
    theta = np.deg2rad(angle)
    u = np.array([np.cos(theta), np.sin(theta)])
    v = np.array([-u[1], u[0]])
    def p(x, y=0):
        return tuple((np.array([180,180])+x*u+y*v)*resolution)
    def line(points, width=2):
        draw.line([p(*q) for q in points], fill='black', width=max(1,round(width*resolution)))
    def polygon(points):
        draw.polygon([p(*q) for q in points], fill='black')
    if mode != 'parallel':
        line([(-100,0),(100,0)])
    if mode in ('arrow','crossing','branch','contact','double'):
        polygon([(100,0),(92,5),(92,-5)])
    if mode == 'double':
        polygon([(-100,0),(-92,5),(-92,-5)])
    if mode in ('dot','detached_dot'):
        # Polygonized circle supports the same independent rotation transform.
        cx = 100 if mode == 'dot' else 100+size+3
        polygon([(cx+size*np.cos(t),size*np.sin(t)) for t in np.linspace(0,2*np.pi,97)])
    if mode == 'bar':
        line([(100,-size),(100,size)], 2)
    if mode == 'rectangle':
        polygon([(100-size,-size),(100+size,-size),(100+size,size),(100-size,size)])
    if mode == 'parallel':
        for offset in [-size,size]:
            line([(-100,offset),(100,offset)])
    if mode == 'crossing':
        line([(0,-25),(0,25)])
    if mode == 'branch':
        line([(75,0),(75-size,20)])
    if mode == 'contact':
        line([(94,0),(94,20)])
    if aa != 1:
        im = im.resize((round(360*scale),)*2, Image.Resampling.LANCZOS)
    boxes=[]
    for t in [-112,112]:
        c=(np.array([180,180])+t*u)*scale
        boxes.append([*(c-8*scale),*(c+8*scale)])
    return im, boxes


def build(out):
    out.mkdir(parents=True, exist_ok=False)
    records=[]
    for mode,angle,scale,size,aa in itertools.product(
        ['line','arrow','dot','detached_dot','bar','rectangle','parallel','crossing','branch','contact','double'],
        [0,30,60,90,135], [.75,1,1.5], [3,5,8], [1,4]):
        im,boxes=fixture(mode,angle,scale,size,aa)
        key=f'{mode}-a{angle}-s{scale}-r{size}-aa{aa}'
        path=out/(key+'.png'); im.save(path)
        # Contact/crossing are intentionally ambiguous even with a visible tip.
        records.append(dict(id=key, mode=mode, scale=scale, boxes=boxes,
                            rgb=path.name, sha256=sha(path), expected='forward' if mode=='arrow' else 'abstain'))
    (out/'manifest.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
    lock=dict(count=len(records), manifest_sha256=sha(out/'manifest.json'), builder_sha256=sha(__file__),
              rationale='RGB-only synthetic geometry. No OCR, GT, owner semantics or observer-derived expected verdicts.')
    (out/'lock.json').write_text(json.dumps(lock,indent=2),encoding='utf-8')
    print(json.dumps(lock))


def run(fixtures, source, out):
    out.mkdir(parents=True, exist_ok=False)
    lock=json.loads((fixtures/'lock.json').read_text())
    assert sha(fixtures/'manifest.json') == lock['manifest_sha256']
    # Snapshot before imports/execution: root may continue editing its file.
    data=source.read_bytes(); snapshot=out/'source_rays_snapshot.py'; snapshot.write_bytes(data)
    sys.path.insert(0,str(source.parents[2]))
    spec=importlib.util.spec_from_file_location('independent_source_rays_snapshot',snapshot)
    observer=importlib.util.module_from_spec(spec); spec.loader.exec_module(observer)
    rows=[]
    for case in json.loads((fixtures/'manifest.json').read_text()):
        path=fixtures/case['rgb']; assert sha(path)==case['sha256']
        rgb=np.array(Image.open(path).convert('RGB'))
        # Exact luminance >=80 contrast. No morphological joining or repair.
        y=rgb.astype(np.int64) @ np.array([2126,7152,722],dtype=np.int64)
        yy,xx=np.where(y <= 175*10000)
        pixels=np.column_stack([xx,yy])
        for swap in [False,True]:
            boxes=case['boxes'][::-1] if swap else case['boxes']
            result,audit=observer.observe_pair(pixels,boxes,scale=case['scale'])
            passed=(result is None) if case['expected']=='abstain' else (result is not None and audit['reversed']==swap)
            rows.append(dict(id=case['id'],mode=case['mode'],swap=swap,expected=case['expected'],passed=passed,audit=audit))
    summary=dict(count=len(rows),passed=sum(r['passed'] for r in rows),
                 false_direction=sum(not r['passed'] and r['expected']=='abstain' for r in rows),
                 positive_failure=sum(not r['passed'] and r['expected']=='forward' for r in rows),
                 source_sha256=sha(snapshot), fixture_lock_sha256=sha(fixtures/'lock.json'),
                 runner_sha256=sha(__file__))
    (out/'results.json').write_text(json.dumps(dict(summary=summary,rows=rows),indent=2),encoding='utf-8')
    print(json.dumps(summary))


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('mode',choices=['build','run'])
    parser.add_argument('--out',type=Path,required=True); parser.add_argument('--fixtures',type=Path)
    parser.add_argument('--source',type=Path)
    args=parser.parse_args()
    if args.mode=='build': build(args.out)
    else: run(args.fixtures,args.source,args.out)
