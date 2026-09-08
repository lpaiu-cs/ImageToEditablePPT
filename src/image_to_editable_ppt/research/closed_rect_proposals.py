"""Conservative source-only closed rectangular owners for complex diagrams."""
import cv2
import numpy as np


def _iou(a,b):
    intersection=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
    return intersection/max(1,(a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-intersection)


def _same_ink_band(rgb,inner,outer,scale):
    a=np.array(inner['bbox']);b=np.array(outer['bbox'])
    if not np.all(a[:2]>=b[:2]) or not np.all(a[2:]<=b[2:]) or np.max(abs(a-b))>max(2,3*scale):return False
    outer_mask=np.zeros(rgb.shape[:2],np.uint8);inner_mask=np.zeros_like(outer_mask)
    cv2.drawContours(outer_mask,[outer['contour']],-1,1,cv2.FILLED)
    cv2.drawContours(inner_mask,[inner['contour']],-1,1,cv2.FILLED)
    band=cv2.erode(outer_mask,np.ones((3,3),np.uint8)) & (1-inner_mask)
    core=cv2.erode(inner_mask,np.ones((5,5),np.uint8))
    if not band.any() or not core.any():return False
    fill=np.median(rgb[core!=0],axis=0)
    contrast=np.max(abs(rgb[band!=0].astype(float)-fill),axis=1)
    return bool(np.mean(contrast>=24)>=.90)


def propose(rgb):
    if rgb.dtype!=np.uint8 or rgb.ndim!=3 or rgb.shape[2]!=3:raise ValueError('uint8 RGB required')
    gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY);s=rgb.shape[0]/360
    arms=[]
    for low,high in [(20,60),(40,100)]:
        contours,hierarchy=cv2.findContours(cv2.Canny(gray,low,high),cv2.RETR_CCOMP,cv2.CHAIN_APPROX_NONE)
        candidates=[]
        if hierarchy is not None:
            for contour,h in zip(contours,hierarchy[0]):
                if h[3]<0:continue
                x,y,w,height=cv2.boundingRect(contour)
                area=cv2.contourArea(contour)
                if not (w>=32*s and height>=16*s and 1.15<=w/height<=15 and .90*w*height<=area<=.25*gray.size):continue
                points=contour[:,0,:]
                distance=np.minimum(np.minimum(points[:,0]-x,x+w-1-points[:,0])/w,
                                    np.minimum(points[:,1]-y,y+height-1-points[:,1])/height)
                if np.percentile(distance,95)>.12:continue
                candidates.append(dict(bbox=[x,y,x+w,y+height],contour=contour,area=float(area)))
        arms.append(candidates)
    selected=[];records=[]
    for candidate in arms[0]:
        box=candidate['bbox']
        matches=[c for c in arms[1] if _iou(box,c['bbox'])>=.98]
        competing=[c for c in arms[0] if c is not candidate and _iou(box,c['bbox'])>=.85]
        same_outer=[c for c in competing if _same_ink_band(rgb,candidate,c,s)]
        stable=any(np.max(abs(np.array(box)-c['bbox']))<=1 for c in matches)
        unambiguous=not competing or (len(competing)==1 and len(same_outer)==1)
        reason='closed_rectangle_agreement' if stable and unambiguous else 'ambiguous_or_threshold_unstable_boundary'
        records.append(dict(bbox=box,reason=reason))
        if reason=='closed_rectangle_agreement':selected.append(candidate)
    return selected,dict(thresholds=[[20,60],[40,100]],candidates=records)


def observe_text(rgb,box,engine):
    x0,y0,x1,y1=box
    crop=rgb[y0:y1,x0:x1]
    arms=[]
    for scale in [1.,1.5,2.25]:
        image=cv2.resize(crop,None,fx=scale,fy=scale,interpolation=cv2.INTER_CUBIC)
        words,_=engine(image,use_cls=False)
        found=[]
        for polygon,text,confidence in words or []:
            if not text.strip():continue
            p=np.asarray(polygon)/scale
            b=[float(p[:,0].min()),float(p[:,1].min()),float(p[:,0].max()),float(p[:,1].max())]
            if b[0]<0 or b[1]<0 or b[2]>crop.shape[1] or b[3]>crop.shape[0]:continue
            found.append(dict(text=text.strip(),confidence=float(confidence),bbox=b))
        arms.append(found)
    lines=[]
    for words in arms:
        groups=[]
        for word in sorted(words,key=lambda w:(w['bbox'][1],w['bbox'][0])):
            b=word['bbox']
            matching=[g for g in groups if min(b[3],g['bbox'][3])-max(b[1],g['bbox'][1])>=.5*min(b[3]-b[1],g['bbox'][3]-g['bbox'][1])]
            if len(matching)==1:
                g=matching[0];g['words'].append(word)
                g['bbox']=[min(g['bbox'][0],b[0]),min(g['bbox'][1],b[1]),max(g['bbox'][2],b[2]),max(g['bbox'][3],b[3])]
            else:groups.append(dict(words=[word],bbox=list(b)))
        for g in groups:
            g['text']=' '.join(w['text'] for w in sorted(g['words'],key=lambda w:w['bbox'][0]))
            g['confidence']=min(w['confidence'] for w in g['words'])
        lines.append(sorted(groups,key=lambda g:g['bbox'][1]))
    accepted=[]
    for index,line in enumerate(lines[0]):
        if any(index>=len(arm) for arm in lines[1:]):break
        others=[arm[index] for arm in lines[1:]]
        if line['confidence']<.95 or any(other['confidence']<.95 or line['text']!=other['text'] or _iou(line['bbox'],other['bbox'])<.8 for other in others):break
        accepted.append(line)
    return '\n'.join(w['text'] for w in accepted) or None,dict(arms=arms,lines=lines,accepted=accepted,policy='complete stable prefix lines only')
