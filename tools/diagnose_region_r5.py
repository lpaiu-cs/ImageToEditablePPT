"""Read-only R5 OCR diagnostics; no target text enters the recognition call."""
import json
import sys
import cv2
import numpy as np
from PIL import Image
from image_to_editable_ppt.v3.text.ocr import _load_engine
from image_to_editable_ppt.region.text import recognize_consistent

def main():
    if '--fanout' in sys.argv:
        from image_to_editable_ppt.region import tracing
        from image_to_editable_ppt.region.geometry import detect_scene
        original=tracing.straight_fanout
        def inspect(component,contacts,tolerance):
            print('CONTACTS',[(s.id,p) for s,p in contacts], 'tolerance',tolerance)
            for i,(s,p) in enumerate(contacts):
                for t,q in contacts[i+1:]:
                    path=tracing.shortest(component,p,q)
                    pts=np.asarray(path); d=pts[-1]-pts[0]
                    residual=np.abs((pts[:,0]-pts[0,0])*d[1]-(pts[:,1]-pts[0,1])*d[0])/max(1,np.linalg.norm(d))
                    middle=pts[20:-20].astype(np.float32)
                    vx,vy,cx,cy=cv2.fitLine(middle,cv2.DIST_L2,0,.01,.01).reshape(-1)
                    mr=np.abs((middle[:,0]-cx)*vy-(middle[:,1]-cy)*vx)
                    print(s.id,t.id,'residual',float(residual.max()),'shaft_residual',float(mr.max()),'arrow',tracing.direction(component,path[len(path)//3:]))
            return original(component,contacts,tolerance)
        tracing.straight_fanout=inspect
        rgb=np.asarray(Image.open('data/phase16_dev_v1/phase16-dev-p034.png').convert('RGB'))
        tracing.trace_scene(detect_scene(rgb,(0,0,1,1)),rgb,(0,0,1,1))
        return
    report=json.load(open('artifacts/region-complex-r5/step1/reasoning-full.region.json'))
    rgb=np.asarray(Image.open('data/phase16_dev_v1/phase16-dev-p034.png').convert('RGB'))
    engine=_load_engine()
    for s in report['source_scene']['shapes']:
        b=s['bbox']; x0,y0,x1,y1=[b[k] for k in ('x0','y0','x1','y1')]
        crop=rgb[y0+3:y1-3,x0+3:x1-3]
        color=np.median(crop.reshape(-1,3),axis=0).tolist()
        padded=cv2.copyMakeBorder(crop,16,16,16,16,cv2.BORDER_CONSTANT,value=color)
        print(s['id'],s['label'],'padded',recognize_consistent(engine,padded),flush=True)

if __name__=='__main__': main()
