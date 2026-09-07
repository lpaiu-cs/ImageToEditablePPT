import argparse
import json
from pathlib import Path
import subprocess
import numpy as np
from PIL import Image,ImageDraw
from image_to_editable_ppt.research.stroke_trace import trace_scene
from image_to_editable_ppt.research.native_emit import load_scene,normalize_scene
from image_to_editable_ppt.research.region_first import digest,evaluate,inspect_pptx,serialize_scene,pixel_box
from image_to_editable_ppt.v3.emit import sample_shape_styles,write_pptx


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--output-dir',required=True)
    args=p.parse_args()
    root=Path(__file__).resolve().parents[1]
    manifest=root/'benchmarks/region_first_r3_inputs_v1.json'
    data=json.loads(manifest.read_text())
    target=root/'benchmarks/region_first_r0_v1.json'
    assert digest(target)==data['target_manifest_sha256']
    samples={s['id']:s for s in json.loads(target.read_text())['samples']}
    for item in data['inputs']:
        for kind in ('source','selected','oracle'): assert digest(root/item[kind+'_path'])==item[kind+'_sha256']
    output=root/args.output_dir
    output.mkdir(parents=True,exist_ok=False)
    paths=['src/image_to_editable_ppt/research/stroke_trace.py','src/image_to_editable_ppt/research/candidate_select.py',
        'src/image_to_editable_ppt/research/region_first.py','src/image_to_editable_ppt/research/native_emit.py',
        'src/image_to_editable_ppt/v3/emit/pptx_writer.py','src/image_to_editable_ppt/v3/emit/style.py',
        'tools/run_stroke_trace.py','docs/region_first_r3_plan.md']
    result=dict(status='R3_trace_diagnostic_not_product_acceptance',manifest_sha256=digest(manifest),
        git_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        git_status=subprocess.check_output(['git','status','--porcelain'],text=True).strip(),
        code_sha256={p:digest(root/p) for p in paths},records=[])
    for item in data['inputs']:
        with Image.open(root/item['source_path']) as im: image=im.convert('RGB')
        rgb=np.asarray(image)
        for arm in ('baseline','strict_trace','transparent_gap_trace','oracle_trace'):
            kind='oracle' if arm=='oracle_trace' else 'selected'
            original=load_scene(root/item[kind+'_path'])
            audit={}; mask=None
            if arm=='baseline': scene=original
            else: scene,audit,mask=trace_scene(original,rgb,item['roi'],transparent_gaps=arm=='transparent_gap_trace')
            assert scene.shapes==original.shapes
            name=f"{item['sample']}--{arm}"
            sp=output/f'{name}.json'; pp=output/f'{name}.pptx'
            sp.write_text(json.dumps(serialize_scene(scene),indent=2,ensure_ascii=False),encoding='utf-8')
            write_pptx(normalize_scene(scene),pp,styles=sample_shape_styles(rgb,original))
            overlay=image.copy(); draw=ImageDraw.Draw(overlay)
            for c in scene.connectors:
                points=[(q.x,q.y) for q in c.path_points]
                draw.line(points,fill='#ff00ff',width=3)
                x,y=points[-1]; draw.ellipse((x-5,y-5,x+5,y+5),fill='red' if c.arrowhead_end else 'blue')
            op=output/f'{name}-paths.png'; overlay.crop(pixel_box(item['roi'],image.size)).save(op)
            mp=None
            if mask is not None:
                mp=output/f'{name}-mask.png'; Image.fromarray(255-mask*255).save(mp)
            metrics=evaluate(scene,samples[item['sample']])
            result['records'].append(dict(sample=item['sample'],arm=arm,input_scene_sha256=item[kind+'_sha256'],
                scene_path=str(sp.relative_to(root)),scene_sha256=digest(sp),pptx_path=str(pp.relative_to(root)),pptx_sha256=digest(pp),
                overlay_path=str(op.relative_to(root)),overlay_sha256=digest(op),mask_path=str(mp.relative_to(root)) if mp else None,
                mask_sha256=digest(mp) if mp else None,audit=audit,metrics=metrics,native=inspect_pptx(pp)))
            (output/'results.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
            print(name,'correct',metrics['matched_directed_edges'],'/',metrics['target_edges'],'raw',metrics['raw_emitted_edges'],
                'wrong',len(metrics['wrong_or_unresolved_local_edges']),flush=True)


if __name__=='__main__': main()
