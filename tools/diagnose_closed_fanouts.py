"""Record why existing source-ray fanout abstains; no runtime behavior changes."""
import argparse
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
from run_region_rgb_baseline import digest,save
from image_to_editable_ppt.region import tracing
from image_to_editable_ppt.research.closed_rect_proposals import propose_union
from image_to_editable_ppt.research.source_evidence_pipeline import detector_scene


def run(image,output):
    output.mkdir(parents=True,exist_ok=False)
    rgb=np.array(Image.open(image));proposals,_=propose_union(rgb,portrait_boxes=True,pixel_agreement=True)
    scene=detector_scene(rgb,[dict(id=f'closed:{i}',role='node',semantic_kind='box',bbox_xyxy=c['bbox'],confidence=.9) for i,c in enumerate(proposals)])
    records=[];original=tracing.straight_fanout
    def inspect(component,contacts,tolerance):
        rows=[]
        for i,(a,p) in enumerate(contacts):
            for b,q in contacts[i+1:]:
                path=tracing.shortest(component,p,q)
                if len(path)<60:continue
                points=np.asarray(path,np.float32);shaft=points[20:-20]
                vx,vy,cx,cy=cv2.fitLine(shaft,cv2.DIST_L2,0,.01,.01).reshape(-1)
                residual=abs((points[:,0]-cx)*vy-(points[:,1]-cy)*vx)
                rows.append(dict(pair=[a.id,b.id],length=len(path),shaft_residual=float(residual[20:-20].max()),
                    endpoint_residual=max(float(residual[0]),float(residual[-1])),
                    forward=tracing.direction(component,path[len(path)//3:]),
                    backward=tracing.direction(component,list(reversed(path[:len(path)*2//3])))))
        selected=original(component,contacts,tolerance)
        records.append(dict(contacts=[dict(id=s.id,point=p) for s,p in contacts],area=int(np.count_nonzero(component)),tolerance=tolerance,pairs=rows,approved=selected is not None))
        print(records[-1],flush=True)
        return selected
    tracing.straight_fanout=inspect
    try:tracing.trace_scene(scene,rgb,(0,0,1,1),transparent_gaps=True)
    finally:tracing.straight_fanout=original
    save(output/'diagnosis.json',dict(source_sha256=digest(image),runner_sha256=digest(Path(__file__)),rows=records,
        scope='Fresh source proposals, no OCR/GT/old scene input; diagnostic observer delegates unchanged frozen function.'))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--image',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.image,a.output)
