"""Execute frozen R2.1 local arms without rerunning recognition. Never overwrite evidence."""
import argparse
import json
from pathlib import Path
import subprocess

import numpy as np
from PIL import Image,ImageDraw,ImageFont,ImageOps

from image_to_editable_ppt.research.local_select import ARMS,select_local as select_scene
from image_to_editable_ppt.research.candidate_select import bounds
from image_to_editable_ppt.research.native_emit import load_scene,normalize_scene
from image_to_editable_ppt.research.region_first import digest,evaluate,inspect_pptx,pixel_box,serialize_scene
from image_to_editable_ppt.v3.emit import sample_shape_styles,write_pptx


def overlay(image,scene,audit,roi,path):
    im=image.copy()
    draw=ImageDraw.Draw(im)
    width=max(2,round(min(image.size)/200))
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',max(12,round(min(image.size)/35)))
    for s in scene.shapes:
        color='red' if s.id in audit['removed'] else '#00a000'
        draw.rectangle(bounds(s),outline=color,width=width)
        draw.text((s.bbox.x0+3,s.bbox.y0+3),s.id.replace(':r0:',':'),font=font,fill=color,stroke_width=1,stroke_fill='white')
    im.crop(pixel_box(roi,image.size)).save(path)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',required=True)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    manifest=root/'benchmarks/region_first_r2_inputs_v1.json'
    data=json.loads(manifest.read_text())
    targets=root/'benchmarks/region_first_r0_v1.json'
    if digest(targets)!=data['target_manifest_sha256']:
        raise ValueError('target manifest drift')
    samples={s['id']:s for s in json.loads(targets.read_text())['samples']}
    for item in data['inputs']:
        for kind in ('scene','source'):
            if digest(root/item[kind+'_path'])!=item[kind+'_sha256']:
                raise ValueError('input drift')
    output=root/args.output_dir
    output.mkdir(parents=True,exist_ok=False)
    code_paths=('src/image_to_editable_ppt/research/candidate_select.py','tools/run_local_selection.py','src/image_to_editable_ppt/research/local_select.py','docs/region_first_r21_protocol.md',
        'src/image_to_editable_ppt/research/region_first.py','src/image_to_editable_ppt/research/native_emit.py',
        'src/image_to_editable_ppt/v3/emit/pptx_writer.py','src/image_to_editable_ppt/v3/emit/style.py')
    results=dict(status='r21_development_diagnostic_not_acceptance',manifest_sha256=digest(manifest),
        git_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        git_status=subprocess.check_output(['git','status','--porcelain'],text=True).strip(),
        code_sha256={p:digest(root/p) for p in code_paths},records=[])
    for item in data['inputs']:
        scene=load_scene(root/item['scene_path'])
        with Image.open(root/item['source_path']) as img:
            image=img.convert('RGB')
        rgb=np.asarray(image)
        styles=sample_shape_styles(rgb,scene)
        for arm in ARMS:
            selected,audit=select_scene(scene,rgb,item['roi'],arm)
            assert all(s in scene.shapes for s in selected.shapes)
            assert all(c in scene.connectors for c in selected.connectors)
            name=f"{item['sample']}--{arm}"
            sp=output/f'{name}.json'
            sp.write_text(json.dumps(serialize_scene(selected),indent=2,ensure_ascii=False),encoding='utf-8')
            pp=output/f'{name}.pptx'
            write_pptx(normalize_scene(selected),pp,styles=styles)
            op=output/f'{name}-selection.png'
            overlay(image,scene,audit,item['roi'],op)
            metrics=evaluate(selected,samples[item['sample']])
            results['records'].append(dict(sample=item['sample'],arm=arm,input_sha256=item['scene_sha256'],
                scene_path=str(sp.relative_to(root)),scene_sha256=digest(sp),pptx_path=str(pp.relative_to(root)),pptx_sha256=digest(pp),
                overlay_path=str(op.relative_to(root)),overlay_sha256=digest(op),selection=audit,metrics=metrics,native=inspect_pptx(pp)))
            (output/'results.json').write_text(json.dumps(results,indent=2,ensure_ascii=False),encoding='utf-8')
            print(name,metrics['matched_objects'], '/',metrics['target_objects'],'extra',len(metrics['unmatched_local_objects']),
                'edges',metrics['matched_directed_edges'],'removed',[(k,v['reason']) for k,v in audit['removed'].items()],flush=True)


if __name__=='__main__':
    main()
