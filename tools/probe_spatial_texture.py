"""Diagnostic texture-only replay; existing RGB-derived OCR is explicitly cached."""
import argparse
import json
from pathlib import Path
import numpy as np
from PIL import Image
from run_region_rgb_baseline import digest,save
from image_to_editable_ppt.research.closed_rect_proposals import propose_union
from image_to_editable_ppt.research.spatial_texture_guard import inspect_spatial_texture


def run(root,output):
    output.mkdir(parents=True,exist_ok=False);rows=[]
    for path in sorted(root.rglob('result.json')):
        lock_path=path.with_name('lock.json')
        if not lock_path.is_file():continue
        result=json.loads(path.read_text(encoding='utf-8'));lock=json.loads(lock_path.read_text(encoding='utf-8'))
        source=Path(lock['source_path']);assert digest(source)==result['source_sha256']
        rgb=np.array(Image.open(source));candidates,_=propose_union(rgb,portrait_boxes=True,pixel_agreement=True)
        records={f'closed:{i}':inspect_spatial_texture(rgb,c,result['text_audit'].get(f'closed:{i}')) for i,c in enumerate(candidates)}
        old=[s['id'] for s in result['source_scene']['shapes']]
        lost=[key for key in old if not records[key]['eligible']]
        row=dict(id=path.parent.parent.name if path.parent.name=='native' else path.parent.name,source_sha256=digest(source),
            cached_result_sha256=digest(path),old_owners=old,would_veto=lost,measurements=records)
        rows.append(row);print(row['id'],'old',len(old),'veto',lost,[(k,round(v['textured_fraction'],3)) for k,v in records.items() if k in old],flush=True)
    save(output/'results.json',dict(rows=rows,runner_sha256=digest(Path(__file__)),
        scope='Texture diagnostic only, explicitly cached image-derived OCR; no fresh native inference or GT input.'))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.run,a.output)
