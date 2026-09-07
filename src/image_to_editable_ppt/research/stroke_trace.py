"""R3 source-connected paths. Research only; ambiguous components are omitted."""
from collections import deque
from dataclasses import replace
import cv2
import numpy as np
from image_to_editable_ppt.research.candidate_select import bounds,gap_owners,source_features
from image_to_editable_ppt.research.region_first import pixel_box
from image_to_editable_ppt.v3.core.enums import PortOwnerKind,ConnectorKind
from image_to_editable_ppt.v3.core.types import Point
from image_to_editable_ppt.v3.emit.models import EmitConnectorPrimitive


def project(x,y,b):
    options=[(abs(x-b.x0),(b.x0,min(b.y1,max(b.y0,y)))),
        (abs(x-b.x1),(b.x1,min(b.y1,max(b.y0,y)))),
        (abs(y-b.y0),(min(b.x1,max(b.x0,x)),b.y0)),
        (abs(y-b.y1),(min(b.x1,max(b.x0,x)),b.y1))]
    return min(options,key=lambda a:a[0])[1]


def shortest(mask,start,end):
    h,w=mask.shape
    queue=deque([start])
    previous={start:None}
    while queue:
        p=queue.popleft()
        if p==end:
            route=[]
            while p is not None:
                route.append(p); p=previous[p]
            return list(reversed(route))
        x,y=p
        for dx,dy in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)):
            q=(x+dx,y+dy)
            if 0<=q[0]<w and 0<=q[1]<h and mask[q[1],q[0]] and q not in previous:
                previous[q]=p; queue.append(q)
    return []


def direction(mask,path):
    widths=[]
    for i,(x,y) in enumerate(path):
        a=path[max(0,i-3)]; b=path[min(len(path)-1,i+3)]
        horizontal=abs(b[0]-a[0])>=abs(b[1]-a[1])
        values=mask[max(0,y-20):min(mask.shape[0],y+21),x] if horizontal else mask[y,max(0,x-20):min(mask.shape[1],x+21)]
        widths.append(float(np.count_nonzero(values)))
    if len(widths)<6: return 0,dict(reason='short_path')
    shaft=float(np.percentile(widths,25))
    band=max(2,round(len(widths)*.35))
    first,last=max(widths[:band]),max(widths[-band:])
    def head(a,b): return a>=1.6*shaft and a>=shaft+2 and a>=1.35*b
    result=1 if head(last,first) else (-1 if head(first,last) else 0)
    return result,dict(shaft_width=shaft,start_max_width=first,end_max_width=last)


def trace_scene(scene,rgb,roi,*,transparent_gaps=False):
    scope=pixel_box(roi,(scene.image_size.width,scene.image_size.height))
    x0,y0,x1,y1=scope
    crop=rgb[y0:y1,x0:x1]
    h,w=crop.shape[:2]
    p=max(2,round(.005*min(h,w)))
    raw=(cv2.cvtColor(crop,cv2.COLOR_RGB2GRAY)<110).astype('uint8')
    mask=raw.copy()
    eligible=[]; transparent=[]
    for s in scene.shapes:
        if s.owner_kind is PortOwnerKind.NODE:
            f=source_features(rgb,s,scope)
            if transparent_gaps and gap_owners(s,scene.shapes) and min(f['interior_median'])>=225 and f['interior_uniform_fraction']>=.95:
                transparent.append(s.id); continue
            eligible.append(s)
        a,b,c,d=[round(z) for z in bounds(s)]
        a,b,c,d=a-x0,b-y0,c-x0,d-y0
        if s.owner_kind is PortOwnerKind.NODE:
            mask[max(0,b-p):min(h,d+p+1),max(0,a-p):min(w,c+p+1)]=0
        else:
            for left,top,right,bottom in ((a-p,b-p,c+p,b+p),(a-p,d-p,c+p,d+p),
                (a-p,b-p,a+p,d+p),(c-p,b-p,c+p,d+p)):
                mask[max(0,top):min(h,bottom+1),max(0,left):min(w,right+1)]=0
    k=min(9,2*p+3)
    mask=np.maximum(cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((1,k),'uint8')),
        cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((k,1),'uint8')))
    mask=cv2.dilate(mask,np.ones((3,3),'uint8'))
    count,labels,stats,_=cv2.connectedComponentsWithStats(mask,connectivity=8)
    tolerance=max(5,3*p)
    records=[]; edges=[]
    for index in range(1,count):
        bx,by,bw,bh,area=map(int,stats[index])
        if area<6: continue
        ys,xs=np.where(labels[by:by+bh,bx:bx+bw]==index)
        xs,ys=xs+bx,ys+by
        gx,gy=xs+x0,ys+y0
        contacts=[]
        for s in eligible:
            b=s.bbox
            dx=np.maximum(np.maximum(b.x0-gx,gx-b.x1),0)
            dy=np.maximum(np.maximum(b.y0-gy,gy-b.y1),0)
            distance=np.hypot(dx,dy)
            near=np.where(distance<=tolerance)[0]
            if not len(near): continue
            best=near[distance[near]<=float(distance[near].min())+.1]
            center=np.median(np.column_stack((xs[best],ys[best])),axis=0)
            chosen=best[np.argmin((xs[best]-center[0])**2+(ys[best]-center[1])**2)]
            contacts.append((s,(int(xs[chosen])-bx,int(ys[chosen])-by)))
        if len(contacts)<2: continue
        r=dict(component=index,owners=[s.id for s,_ in contacts],pixel_area=area)
        if len(contacts)!=2:
            r['rejected']='ambiguous_multi_owner'; records.append(r); continue
        component=labels[by:by+bh,bx:bx+bw]==index
        path=shortest(component,contacts[0][1],contacts[1][1])
        if len(path)<6:
            r['rejected']='short'; records.append(r); continue
        sign,arrow=direction(component,path)
        r['arrow']=arrow
        a,b=contacts[0][0],contacts[1][0]
        simplified=cv2.approxPolyDP(np.asarray(path,np.float32).reshape(-1,1,2),max(1,.002*min(h,w)),False)[:,0,:]
        points=[(float(x+bx+x0),float(y+by+y0)) for x,y in simplified]
        points[0]=project(*points[0],a.bbox)
        points[-1]=project(*points[-1],b.bbox)
        if sign<0:
            a,b=b,a; points.reverse()
        cid=f'connector:r3:{len(edges)}'
        edge=EmitConnectorPrimitive(cid,ConnectorKind.ARROW if sign else ConnectorKind.LINE,.8,
            a.id,a.owner_kind,b.id,b.owner_kind,cid+':start',cid+':end',
            path_points=tuple(Point(*q) for q in points),arrowhead_end=bool(sign),source='r3_stroke_trace',
            provenance=('r3:continuous_component','r3:bounded_mask_gap_repair'))
        edges.append(edge)
        r.update(connector_id=cid,directed=bool(sign),path_points=points,raw_path_length=len(path))
        records.append(r)
    return replace(scene,connectors=tuple(edges)),dict(transparent_owners=transparent,mask_pad=p,
        attachment_tolerance=tolerance,components=records),mask
