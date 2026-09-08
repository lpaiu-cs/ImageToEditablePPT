"""Read-only saved-prediction diagnostic: why a straight fan-out abstained."""
import argparse
import json
from pathlib import Path
import sys

import cv2
import numpy as np
from PIL import Image
from run_region_rgb_baseline import ROOT, digest, save
sys.path.insert(0, str(ROOT/'src'))
from image_to_editable_ppt.region import tracing
from image_to_editable_ppt.research.source_evidence_pipeline import detector_scene


def run(directory, output):
    output.mkdir(parents=True, exist_ok=False)
    result=json.loads((directory/'result.json').read_text())
    lock=json.loads((directory/'lock.json').read_text())
    source=Path(lock['source_path'])
    assert digest(source)==result['source_sha256']==lock['source_sha256']
    rgb=np.asarray(Image.open(source).convert('RGB'))
    objects=[dict(id=s['id'],role='node',semantic_kind='box',confidence=.9,
        bbox_xyxy=[s['bbox'][k] for k in ('x0','y0','x1','y1')])
        for s in result['proposed_scene']['shapes']]
    scene=detector_scene(rgb,objects)
    original=tracing.straight_fanout; records=[]
    def inspect(component, contacts, tolerance):
        rows=[]
        for i,(owner,start) in enumerate(contacts):
            for j,(leaf,end) in enumerate(contacts):
                if i==j:continue
                path=tracing.shortest(component,start,end) if i<j else list(reversed(tracing.shortest(component,end,start)))
                row=dict(hub=owner.id,leaf=leaf.id,start=start,end=end,length=len(path))
                if len(path)>=60:
                    points=np.asarray(path,np.float32);shaft=points[20:-20]
                    vx,vy,cx,cy=cv2.fitLine(shaft,cv2.DIST_L2,0,.01,.01).reshape(-1)
                    residual=np.abs((points[:,0]-cx)*vy-(points[:,1]-cy)*vx)
                    sign,arrow=tracing.direction(component,path[len(path)//3:])
                    row.update(residual_max=float(residual[20:-20].max()),
                        terminal_residual=max(float(residual[0]),float(residual[-1])),sign=sign,arrow=arrow)
                rows.append(row)
        records.append(dict(owners=[s.id for s,_ in contacts],tolerance=tolerance,paths=rows))
        return original(component,contacts,tolerance)
    tracing.straight_fanout=inspect
    try:
        _,audit,_=tracing.trace_scene(scene,rgb,(0,0,1,1),transparent_gaps=True)
    finally:tracing.straight_fanout=original
    save(output/'diagnostic.json',dict(source_sha256=digest(source),
        result_sha256=digest(directory/'result.json'),runner_sha256=digest(Path(__file__)),
        scope='saved prediction geometry diagnostic, not fresh RGB inference or ground truth',
        records=records,trace=audit))
    print(json.dumps(records,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.run,a.output)
