"""Read-only RGB/path diagnosis; fit raw observed stroke without emitting a candidate."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

from run_region_rgb_baseline import ROOT, digest, save
from image_to_editable_ppt.research.native_emit import load_scene
from image_to_editable_ppt.region.tracing import trace_scene
from image_to_editable_ppt.region.strokes import stroke_mask


def intersections(origin, vector, box):
    hits = []
    for axis in (0, 1):
        if abs(vector[axis]) < 1e-8:
            continue
        for boundary in (box[axis], box[axis+2]):
            point = origin + vector * ((boundary-origin[axis])/vector[axis])
            other = 1-axis
            if box[other]-1e-6 <= point[other] <= box[other+2]+1e-6:
                hits.append(point)
    return hits


def run(out):
    index = json.loads((ROOT / 'benchmarks/region_r8a_attachment.json').read_text())['arms']['t']
    base = ROOT / index['artifact_root']
    assert digest(base / 'results.json') == index['files']['results.json']
    result = json.loads((base / 'results.json').read_text(encoding='utf-8'))['records'][13]
    assert result['slot'] == '013' and result['id'] == 'tree_1302_00079'
    image = base / 'rgb/013.png'
    assert digest(image) == result['source_sha256']
    out.mkdir(parents=True, exist_ok=False)
    save(out / 'fixed_scene.json', result['report']['source_scene'])
    scene = load_scene(out / 'fixed_scene.json')
    rgb = np.asarray(Image.open(image).convert('RGB'))
    cv2.setNumThreads(1)
    traced, audit, mask = trace_scene(scene, rgb, (0, 0, 1, 1), transparent_gaps=True)
    actual = json.loads(json.dumps(asdict(traced)))
    assert actual['connectors'] == result['report']['source_scene']['connectors']
    _, labels = cv2.connectedComponents(mask, connectivity=8)
    raw = stroke_mask(rgb)
    owners = {s.id: s for s in scene.shapes}
    by_id = {c['connector_id']: c for c in audit['components'] if 'connector_id' in c}
    records, panels = [], []
    font = ImageFont.truetype('C:/Windows/Fonts/malgun.ttf', 14)
    for connector in traced.connectors:
        component_id = by_id[connector.id]['component']
        observed = (labels == component_id) & (raw > 0)
        yy, xx = np.where(observed)
        pixels = np.column_stack([xx, yy]).astype(np.float32)
        vx, vy, cx, cy = cv2.fitLine(pixels, cv2.DIST_L2, 0, .01, .01).reshape(-1)
        vector, origin = np.array([vx, vy], float), np.array([cx, cy], float)
        residual = np.abs((pixels[:, 0]-cx)*vy-(pixels[:, 1]-cy)*vx)
        path = np.array([(p.x, p.y) for p in connector.path_points])
        path_residual = np.abs((path[:, 0]-cx)*vy-(path[:, 1]-cy)*vx)
        endpoints = []
        for owner_id, current in [(connector.source_owner_id, path[0]), (connector.target_owner_id, path[-1])]:
            b = owners[owner_id].bbox
            hits = intersections(origin, vector, [b.x0, b.y0, b.x1, b.y1])
            proposed = min(hits, key=lambda p: float(np.linalg.norm(p-current))) if hits else None
            endpoints.append(dict(owner_id=owner_id, current=current.tolist(),
                raw_line_intersects_owner=bool(hits), intersection=proposed.tolist() if proposed is not None else None,
                endpoint_displacement=float(np.linalg.norm(proposed-current)) if proposed is not None else None))
        row = dict(id=connector.id, source_label=owners[connector.source_owner_id].label,
            target_label=owners[connector.target_owner_id].label, component=component_id,
            raw_ink_pixels=len(pixels), raw_ink_perpendicular_p95=float(np.percentile(residual, 95)),
            raw_ink_perpendicular_max=float(residual.max()),
            traced_vertex_perpendicular_max=float(path_residual.max()),
            traced_vertex_residuals=path_residual.tolist(), endpoints=endpoints,
            native_rejection=result['report']['emission']['rejected_connectors'].get(connector.id),
            observation='Raw stroke TLS line only; no candidate path replacement or PPT emission')
        records.append(row)
        if row['native_rejection'] is None:
            continue
        x0, y0 = np.maximum(0, np.floor(path.min(axis=0)-20)).astype(int)
        x1, y1 = np.minimum([rgb.shape[1], rgb.shape[0]], np.ceil(path.max(axis=0)+20)).astype(int)
        panel = Image.new('RGB', (940, 280), '#edf1f5')
        draw = ImageDraw.Draw(panel)
        for j, mode in enumerate(('현재 추적 경로', '원본 잉크 TLS 직선: 진단용')):
            overlay = Image.fromarray(rgb.copy())
            painter = ImageDraw.Draw(overlay)
            for endpoint in endpoints:
                b = owners[endpoint['owner_id']].bbox
                painter.rectangle([b.x0, b.y0, b.x1, b.y1], outline=(30, 170, 70), width=1)
            if j == 0:
                painter.line([tuple(p) for p in path], fill=(230, 40, 50), width=2)
                for x, y in path:
                    painter.ellipse((x-2, y-2, x+2, y+2), fill=(230, 40, 50))
            elif all(e['intersection'] is not None for e in endpoints):
                painter.line([tuple(e['intersection']) for e in endpoints], fill=(0, 150, 230), width=2)
            draw.text((j*470+8, 6), connector.id+' '+mode, font=font, fill='black')
            draw.text((j*470+8, 27),
                f"trace max={row['traced_vertex_perpendicular_max']:.2f}px / ink p95={row['raw_ink_perpendicular_p95']:.2f}px",
                font=font, fill='black')
            panel.paste(ImageOps.contain(overlay.crop((x0, y0, x1, y1)), (452, 224)), (j*470+8, 51))
        panel.save(out / (connector.id.replace(':', '-')+'.png'))
        panels.append(panel)
    contact = Image.new('RGB', (940, 280*len(panels)), 'white')
    for i, panel in enumerate(panels):
        contact.paste(panel, (0, i*280))
    contact.save(out / 'contact.png')
    save(out / 'diagnosis.json', dict(source_results_sha256=digest(base / 'results.json'),
        source_rgb_sha256=digest(image), runner_sha256=digest(__file__),
        trace_code_sha256=digest(ROOT / 'src/image_to_editable_ppt/region/tracing.py'),
        fit_code_sha256=digest(ROOT / 'src/image_to_editable_ppt/region/_path_fit.py'),
        unit='original RGB pixels; native gate applies after 1.2x normalization',
        original_trace_reproduced_exactly=True, ground_truth_read=False, records=records))
    print(json.dumps(records, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args().output)
