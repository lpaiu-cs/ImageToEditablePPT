"""Read actual ink-row bands inside an observed closed owner, without DB boxes."""
import cv2
import numpy as np


def observe_rows(rgb,candidate,owned,engine):
    x0,y0,x1,y1=candidate['bbox'];scale=rgb.shape[0]/360
    core=cv2.erode(owned,np.ones((max(3,round(2*scale))|1,)*2,np.uint8))
    pixels=rgb[core!=0]
    if len(pixels)<12:return None,dict(accepted=[],bands=[],reason='empty_owned_region')
    background=np.median(pixels,axis=0)
    ink=(np.max(abs(rgb.astype(float)-background),axis=2)>64)&(core!=0)
    crop_ink=ink[y0:y1,x0:x1]
    active=np.flatnonzero(crop_ink.sum(axis=1)>=max(2,.01*(x1-x0)))
    bands=[]
    for row in active:
        if not bands or row>bands[-1][-1]+2:bands.append([int(row)])
        else:bands[-1].append(int(row))
    records=[];accepted=[]
    for band in bands:
        top,bottom=band[0],band[-1]+1
        xs=np.flatnonzero(crop_ink[top:bottom].any(axis=0))
        if bottom-top<max(5,3*scale) or not len(xs):continue
        left,right=int(xs.min()),int(xs.max()+1)
        box=[left,top,right,bottom]
        reason='candidate_source_row'
        if bottom-top>.5*(y1-y0) or right-left<max(8,6*scale):reason='non_text_row_geometry'
        observations=[]
        if reason=='candidate_source_row':
            # Padding is source pixels, clipped to the actual owner bbox.
            pad=2
            a,b=max(x0,x0+left-pad),max(y0,y0+top-pad)
            c,d=min(x1,x0+right+pad),min(y1,y0+bottom+pad)
            for size in (1.,1.5,2.25):
                row=cv2.resize(rgb[b:d,a:c],None,fx=size,fy=size,interpolation=cv2.INTER_CUBIC)
                result,_=engine(row,use_det=False,use_cls=False,use_rec=True)
                observations.append(dict(text=result[0][0].strip(),confidence=float(result[0][1]))
                    if result and len(result)==1 and len(result[0])==2 else dict(text='',confidence=0.))
            if not observations[0]['text'] or any(o['confidence']<.98 or o['text']!=observations[0]['text'] for o in observations):
                reason='unstable_or_untrusted_source_row'
            else:reason='stable_source_row'
        records.append(dict(bbox=box,reason=reason,observations=observations))
    for record in records:
        if record['reason']!='stable_source_row':break
        text=record['observations'][0]['text'];confidence=min(o['confidence'] for o in record['observations'])
        accepted.append(dict(text=text,bbox=record['bbox'],confidence=confidence,
            words=[dict(text=text,bbox=record['bbox'],confidence=confidence)]))
    return '\n'.join(l['text'] for l in accepted) or None,dict(accepted=accepted,bands=records,
        policy='raw owned ink rows; whole-row recognition agreement; stable complete prefix')
