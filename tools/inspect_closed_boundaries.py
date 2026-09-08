"""RGB-only diagnostic of contours before the closed-rectangle proposal filters."""
import argparse
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
from run_region_rgb_baseline import digest,save


def run(image,output):
    output.mkdir(parents=True,exist_ok=False)
    rgb=np.asarray(Image.open(image).convert('RGB'));gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY);s=rgb.shape[0]/360
    records=[]
    for name,raw in [('canny-low',cv2.Canny(gray,20,60)),('canny-high',cv2.Canny(gray,40,100)),
            ('dark-low',(gray<130).astype(np.uint8)),('dark-high',(gray<170).astype(np.uint8))]:
        contours,hierarchy=cv2.findContours(raw,cv2.RETR_CCOMP,cv2.CHAIN_APPROX_NONE)
        for i,(c,h) in enumerate(zip(contours,[] if hierarchy is None else hierarchy[0])):
            x,y,w,height=cv2.boundingRect(c);area=cv2.contourArea(c)
            if min(w,height)<16:continue
            p=c[:,0,:];d=np.minimum(np.minimum(p[:,0]-x,x+w-1-p[:,0])/w,np.minimum(p[:,1]-y,y+height-1-p[:,1])/height)
            dimensions=(w>=32*s and height>=16*s and 1.15<=w/height<=15) or (height>=32*s and w>=16*s and 1.15<=height/w<=15) or (min(w,height)>=32*s and 1/1.15<=w/height<=1.15)
            records.append(dict(arm=name,index=i,parent=int(h[3]),bbox=[x,y,x+w,y+height],area=area,
                area_fraction=area/(w*height),dimensions=dimensions,boundary_q95=float(np.percentile(d,95))))
    save(output/'contours.json',dict(source=str(image.resolve()),source_sha256=digest(image),runner_sha256=digest(Path(__file__)),
        scope='RGB contour diagnostic; no annotation input; not a prediction',records=records))
    print(len(records),'contours')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--image',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.image,a.output)
