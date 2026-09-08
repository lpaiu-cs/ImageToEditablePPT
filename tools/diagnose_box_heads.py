"""Read-only raw terminal profiles of emitted straight undirected candidates."""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

from image_to_editable_ppt.research.source_rays import _head


def observe(rgb,points,boxes):
    a,b=np.array(points,dtype=float);delta=b-a;length=np.linalg.norm(delta);u=delta/length;v=np.array([-u[1],u[0]])
    raw=rgb.astype(np.int64)@np.array([2126,7152,722])<1300000
    y,x=np.where(raw);p=np.column_stack([x,y]);t=(p-a)@u;q=(p-a)@v;s=rgb.shape[0]/360
    select=(t>=0)&(t<=length)&(abs(q)<=8*s)
    for x0,y0,x1,y1 in boxes:
        select&=~((x>=x0-2*s)&(x<=x1+2*s)&(y>=y0-2*s)&(y<=y1+2*s))
    t,q=t[select],q[select]
    if not len(t):return dict(reason='empty')
    mid=(t>=16*s)&(t<=length-16*s)
    width=mid.sum()/max(1,length-32*s)
    end,ea=_head(t,q,length,width,s,abs(u).sum())
    start,sa=_head(t,-q,length,width,s,abs(u).sum(),reverse=True)
    return dict(start=start,end=end,start_audit=sa,end_audit=ea,width=width,extensions=[float(t.min()),float(length-t.max())])


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);a=p.parse_args()
    rows=json.loads((a.source/'results.json').read_text())['records']
    for r in rows:
        rgb=np.asarray(Image.open(a.source/'rgb'/(r['slot']+'.png')))
        scene=r['report']['emitted_scene'];scale=r['report']['normalization_scale']
        shapes={s['id']:s for s in r['report']['source_scene']['shapes']}
        for edge in scene['connectors']:
            if edge['arrowhead_start'] or edge['arrowhead_end'] or len(edge['path_points'])!=2:continue
            owners=[shapes[edge[k]] for k in ('source_owner_id','target_owner_id')]
            if any(s['shape_kind']=='label_anchor' for s in owners):continue
            result=observe(rgb,[[p['x']/scale,p['y']/scale] for p in edge['path_points']],[[s['bbox'][k] for k in ('x0','y0','x1','y1')] for s in owners])
            print(r['slot'],[s['label'] for s in owners],json.dumps(result))
