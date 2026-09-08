"""Research spatial OCR plus observed ink; never consume stored labels or GT."""
from dataclasses import replace
import math

import cv2
import numpy as np


def inside(xx,yy,b):
    return (xx>=b[0])&(xx<b[2])&(yy>=b[1])&(yy<b[3])


def envelope(word):
    p=np.asarray(word['polygon']);return [*p.min(0),*p.max(0)]


def intersection(a,b):
    return max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))


def area(b):return (b[2]-b[0])*(b[3]-b[1])


def select_cluster(rgb,cluster):
    audit=dict(decision='unchanged',reason=None)
    def reject(reason):return None,dict(audit,reason=reason)
    observations=cluster['observations']
    if len(observations)!=2:return reject('missing_two_scales')
    major=[[w for w in o['words'] if w['confidence']>=.95] for o in observations]
    if any(len(words)!=1 for words in major):return reject('not_single_confident_word')
    first,second=[ws[0] for ws in major]
    if first['text'].strip()!=second['text'].strip():return reject('text_scale_disagreement')
    a,b=envelope(first),envelope(second);inter=intersection(a,b)
    if inter/max(1e-9,area(a)+area(b)-inter)<.8:return reject('spatial_scale_disagreement')
    box=[min(a[0],b[0]),min(a[1],b[1]),max(a[2],b[2]),max(a[3],b[3])]
    h=box[3]-box[1];s=rgb.shape[0]/360
    if not 3*s<=h<=32*s or not .5<=(box[2]-box[0])/h<=20:return reject('word_size_unsupported')
    for w in (first,second):
        p=np.array(w['polygon']);d=p[1]-p[0]
        if abs(math.degrees(math.atan2(d[1],d[0])))>10:return reject('word_orientation_unsupported')
    # Observe real surrounding background, not the OCR crop's stroke-crossed edge
    # and not its artificial median padding.
    x0,y0,x1,y1=cluster['crop'];pad=math.ceil(3*h)
    x0,y0=max(0,x0-pad),max(0,y0-pad)
    x1,y1=min(rgb.shape[1],x1+pad),min(rgb.shape[0],y1+pad)
    local=rgb[y0:y1,x0:x1].astype(np.int64)
    lum=local@np.array([2126,7152,722],dtype=np.int64)
    ring=np.ones(lum.shape,bool);ring[2:-2,2:-2]=False
    values=np.sort(lum[ring]);n=len(values)
    bg2=int(values[(n-1)//2])+int(values[n//2])
    if bg2<2*225*10000 or np.percentile(values,90)-np.percentile(values,10)>30*10000:
        return reject('background_unsupported')
    full_lum=rgb.astype(np.int64)@np.array([2126,7152,722],dtype=np.int64)
    contrast2=np.maximum(0,bg2-2*full_lum);core=contrast2>=1600000;weak=contrast2>=240000
    yy,xx=np.indices(core.shape);xx=xx+.5;yy=yy+.5;window=inside(xx,yy,box)
    _,labels,stats,_=cv2.connectedComponentsWithStats(core.astype('uint8'),connectivity=8)
    seed=np.zeros_like(core);strokes=np.zeros_like(core);outside_core=np.zeros_like(core)
    stroke_records=[]
    owner_union=np.zeros_like(core)
    for owner in cluster['owners']:owner_union|=inside(xx,yy,owner['bbox'])
    for label in np.unique(labels[window|owner_union]):
        if label==0:continue
        pixels=labels==label
        if not (pixels&~window).any():seed|=pixels;continue
        py,px=np.where(pixels);xy=np.column_stack((px+.5,py+.5));centered=xy-xy.mean(0)
        _,vec=np.linalg.eigh(centered.T@centered/max(1,len(xy)));axis=vec[:,-1]
        along=centered@axis;perp=abs(centered@np.array([-axis[1],axis[0]]))
        span=float(np.ptp(along));p95=float(np.percentile(perp,95))
        if span<3*h or p95>2.5*s:return reject('ambiguous_crossing_component')
        strokes|=pixels;stroke_records.append(dict(label=int(label),span=span,p95=p95))
    # Additional OCR snippets must be explained by a long observed core component.
    for obs in observations:
        for word in obs['words']:
            if word['confidence']>=.95:continue
            snippet=inside(xx,yy,envelope(word))
            for label in np.unique(labels[snippet]):
                if label==0:continue
                pixels=labels==label
                py,px=np.where(pixels);xy=np.column_stack((px+.5,py+.5));centered=xy-xy.mean(0)
                _,vec=np.linalg.eigh(centered.T@centered/max(1,len(xy)));axis=vec[:,-1]
                span=float(np.ptp(centered@axis));p95=float(np.percentile(abs(centered@np.array([-axis[1],axis[0]])),95))
                if span<3*h or p95>2.5*s:return reject('unexplained_extra_snippet')
                strokes|=pixels
            if not (snippet&core).any():return reject('unexplained_extra_snippet')
    if seed.sum()<4:return reject('insufficient_core')
    # A faint arrowhead can enter an owner while its dark shaft stops outside
    # the OCR/owner window. Identify long core strokes in the original frame.
    for label,stat in enumerate(stats):
        if label==0 or max(stat[2:4])<3*h or (labels[seed]==label).any():continue
        pixels=labels==label;py,px=np.where(pixels)
        xy=np.column_stack((px+.5,py+.5));centered=xy-xy.mean(0)
        _,vec=np.linalg.eigh(centered.T@centered/len(xy));axis=vec[:,-1]
        if np.ptp(centered@axis)>=3*h and np.percentile(abs(centered@np.array([-axis[1],axis[0]])),95)<=2.5*s:
            strokes|=pixels
    grown=cv2.dilate(seed.astype('uint8'),np.ones((3,3),np.uint8)).astype(bool)
    if (grown&strokes).any():return reject('shaft_glyph_contact')
    support=grown&weak&window&~strokes
    # Retain separate weak components in the word envelope, including tiny marks.
    _,weak_labels=cv2.connectedComponents(weak.astype('uint8'),connectivity=8)
    for label in np.unique(weak_labels[window]):
        if label and not ((weak_labels==label)&~window).any():support|=weak_labels==label
    coverage=[]
    for owner in cluster['owners']:
        own=inside(xx,yy,owner['bbox'])
        coverage.append(dict(id=owner['id'],core=float((seed&own).sum()/seed.sum()),
            weak=float((support&own).sum()/support.sum()),
            polygon=float(intersection(owner['bbox'],box)/area(box))))
        outside_core|=own&core&~window&~strokes
    explained=cv2.dilate((seed|strokes).astype('uint8'),np.ones((3,3),np.uint8)).astype(bool)
    unexplained_weak=weak&owner_union&~window&~explained
    stroke_weak_ids=np.unique(weak_labels[strokes&weak])
    # Weak connectivity is only used to account for stroke fringe; it never
    # merges owners or changes the word's retained core/support requirements.
    stroke_fringe=np.isin(weak_labels,stroke_weak_ids[stroke_weak_ids!=0])
    unexplained_weak&=~stroke_fringe
    audit.update(text=first['text'],word_box=box,core_pixels=int(seed.sum()),weak_pixels=int(support.sum()),
                 coverage=coverage,strokes=stroke_records,background_luminance_x2=bg2,
                 weak_orphan_pixels_xy=np.column_stack(np.where(unexplained_weak)[::-1]).tolist())
    if outside_core.any():return reject('independent_core_outside_word')
    if unexplained_weak.any():return reject('weak_orphan_outside_word')
    if any(r['polygon']<.5 for r in coverage):return reject('insufficient_shared_location')
    if any(r['core']<.8 for r in coverage):return reject('partial_word_owner')
    winners=[r['id'] for r in coverage if r['core']==1. and r['weak']>=.98]
    if len(winners)!=1:return reject('no_unique_complete_owner')
    return winners[0],dict(audit,decision='select',reason='unique_complete_spatial_word',winner=winners[0])


def apply_observations(scene,rgb,observations):
    removed=set();audit=[]
    for cluster in observations:
        winner,record=select_cluster(rgb,cluster)
        audit.append(dict(record,owners=[o['id'] for o in cluster['owners']]))
        if winner is not None:removed.update(o['id'] for o in cluster['owners'] if o['id']!=winner)
    # Trace must be recomputed; never carry or alias connectors after suppression.
    return replace(scene,shapes=tuple(s for s in scene.shapes if s.id not in removed),connectors=()),audit
