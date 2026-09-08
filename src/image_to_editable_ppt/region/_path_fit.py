"""Bounded native preset fitting, derived from frozen R3-E1."""
import math
import numpy as np

def samples(path):
    pieces=[]
    for a,b in zip(path,path[1:]):
        a,b=np.asarray(a,float),np.asarray(b,float)
        pieces.append(np.linspace(a,b,max(2,math.ceil(np.linalg.norm(b-a)/.25)+1)))
    return np.concatenate(pieces)


def distance(points,path):
    distances=[]
    for a,b in zip(path,path[1:]):
        a,b=np.asarray(a,float),np.asarray(b,float); v=b-a
        t=np.clip((points-a)@v/max(float(v@v),1e-12),0,1)
        distances.append(np.linalg.norm(points-(a+t[:,None]*v),axis=1))
    return float(np.min(distances,axis=0).max())


def fit_path(points):
    source=[(p.x,p.y) for p in points]
    a,b=source[0],source[-1]
    candidates=[('line',None,[a,b])]
    if abs(b[0]-a[0])>1e-6 and abs(b[1]-a[1])>1e-6:
        xs=[a[0],b[0],(a[0]+b[0])/2,*[p[0] for p in source[1:-1]]]
        for x in xs:
            if min(a[0],b[0])<=x<=max(a[0],b[0]):
                candidates.append(('bentConnector3',(x-a[0])/(b[0]-a[0]),[a,(x,a[1]),(x,b[1]),b]))
    scores=[]
    for preset,adj,route in candidates:
        error=max(distance(samples(source),route),distance(samples(route),source))
        scores.append((error,preset,adj,route))
    best=min(scores,key=lambda r:r[0])
    if best[0]>4: raise ValueError(f'no supported preset within 4px: {best[0]}')
    return dict(error_px=best[0],preset=best[1],adj=best[2],route_px=best[3])
