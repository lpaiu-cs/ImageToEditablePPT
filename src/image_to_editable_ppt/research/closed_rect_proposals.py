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


def pixel_cell_agreement(a,b):
    """Absolute original-pixel boundary uncertainty, independent of box area."""
    return bool(np.max(abs(np.asarray(a,dtype=float)-np.asarray(b,dtype=float)))<=1)


def propose(rgb,*,inner_boundaries=False,dark_boundaries=False,portrait_boxes=False,pixel_agreement=False,compact_boxes=False):
    if rgb.dtype!=np.uint8 or rgb.ndim!=3 or rgb.shape[2]!=3:raise ValueError('uint8 RGB required')
    gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY);s=rgb.shape[0]/360
    arms=[]
    for index,(low,high) in enumerate([(20,60),(40,100)]):
        raw=(gray<[130,170][index]).astype(np.uint8) if dark_boundaries else cv2.Canny(gray,low,high)
        contours,hierarchy=cv2.findContours(raw,cv2.RETR_CCOMP,cv2.CHAIN_APPROX_NONE)
        candidates=[]
        if hierarchy is not None:
            for contour,h in zip(contours,hierarchy[0]):
                if h[3]<0:continue
                x,y,w,height=cv2.boundingRect(contour)
                area=cv2.contourArea(contour)
                dimensions=(w>=32*s and height>=16*s and 1.15<=w/height<=15) or (
                    portrait_boxes and height>=32*s and w>=16*s and 1.15<=height/w<=15) or (
                    compact_boxes and min(w,height)>=32*s and 1/1.15<=w/height<=1.15)
                if not (dimensions and .90*w*height<=area<=.25*gray.size):continue
                points=contour[:,0,:]
                distance=np.minimum(np.minimum(points[:,0]-x,x+w-1-points[:,0])/w,
                                    np.minimum(points[:,1]-y,y+height-1-points[:,1])/height)
                if np.percentile(distance,95)>.12:continue
                candidates.append(dict(bbox=[x,y,x+w,y+height],contour=contour,area=float(area)))
        arms.append(candidates)
    selected=[];records=[]
    for candidate in arms[0]:
        box=candidate['bbox']
        matches=[c for c in arms[1] if (pixel_cell_agreement(box,c['bbox'])
            if pixel_agreement else _iou(box,c['bbox'])>=.98)]
        competing=[c for c in arms[0] if c is not candidate and _iou(box,c['bbox'])>=.85]
        same_outer=[c for c in competing if _same_ink_band(rgb,candidate,c,s)]
        stable=any(np.max(abs(np.array(box)-c['bbox']))<=1 for c in matches)
        unambiguous=not competing or (len(competing)==1 and len(same_outer)==1)
        if inner_boundaries and competing:
            # Keep an actual inner boundary; do not merge nearby outlines or
            # infer whether their outer siblings were borders or shadows.
            stable_competing=[c for c in competing if any((pixel_agreement or _iou(c['bbox'],other['bbox'])>=.98)
                and pixel_cell_agreement(c['bbox'],other['bbox']) for other in arms[1])]
            unambiguous=all(c['bbox'][0]<=box[0] and c['bbox'][1]<=box[1]
                and c['bbox'][2]>=box[2] and c['bbox'][3]>=box[3]
                and c['bbox']!=box for c in stable_competing)
        reason='closed_rectangle_agreement' if stable and unambiguous else 'ambiguous_or_threshold_unstable_boundary'
        records.append(dict(bbox=box,reason=reason))
        if reason=='closed_rectangle_agreement':selected.append(candidate)
    return selected,dict(thresholds=[130,170] if dark_boundaries else [[20,60],[40,100]],dark_boundaries=dark_boundaries,portrait_boxes=portrait_boxes,inner_boundaries=inner_boundaries,pixel_agreement=pixel_agreement,compact_boxes=compact_boxes,candidates=records)


def propose_union(rgb,*,portrait_boxes=False,pixel_agreement=False,compact_boxes=False):
    """Union independently closed boundaries; suppress duplicates, never fit a new box."""
    canny,canny_audit=propose(rgb,inner_boundaries=True,portrait_boxes=portrait_boxes,pixel_agreement=pixel_agreement,compact_boxes=compact_boxes)
    dark,dark_audit=propose(rgb,dark_boundaries=True,portrait_boxes=portrait_boxes,pixel_agreement=pixel_agreement,compact_boxes=compact_boxes)
    ordered=sorted([dict(c,method=method) for method,items in [('canny',canny),('dark',dark)] for c in items],
                   key=lambda c:((c['bbox'][2]-c['bbox'][0])*(c['bbox'][3]-c['bbox'][1]),c['method']))
    selected=[];duplicates=[]
    for candidate in ordered:
        matching=[c for c in selected if _iou(c['bbox'],candidate['bbox'])>=.85]
        if matching:
            duplicates.append(dict(bbox=candidate['bbox'],method=candidate['method'],retained=matching[0]['bbox']))
        else:selected.append(candidate)
    return selected,dict(mode='union_of_individually_verified_closed_boundaries',
        canny=canny_audit,dark=dark_audit,suppressed=duplicates,
        selected=[dict(bbox=c['bbox'],method=c['method']) for c in selected])


def observe_text(rgb,box,engine,*,excluded=None,whole_lines=False):
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
            if excluded is not None:
                a,c=int(np.floor(b[0]))+x0,int(np.ceil(b[2]))+x0
                d,e=int(np.floor(b[1]))+y0,int(np.ceil(b[3]))+y0
                if excluded[d:e,a:c].any():continue
            found.append(dict(text=text.strip(),confidence=float(confidence),bbox=b))
        arms.append(found)
    lines=[]
    for arm_index,words in enumerate(arms):
        groups=[]
        for word in sorted(words,key=lambda w:(w['bbox'][1],w['bbox'][0])):
            b=word['bbox']
            matching=[g for g in groups if min(b[3],g['bbox'][3])-max(b[1],g['bbox'][1])>=.5*min(b[3]-b[1],g['bbox'][3]-g['bbox'][1])]
            if len(matching)==1:
                g=matching[0];g['words'].append(word)
                g['bbox']=[min(g['bbox'][0],b[0]),min(g['bbox'][1],b[1]),max(g['bbox'][2],b[2]),max(g['bbox'][3],b[3])]
            else:groups.append(dict(words=[word],bbox=list(b)))
        for g in groups:
            ordered=sorted(g['words'],key=lambda w:w['bbox'][0])
            g['text']=' '.join(w['text'] for w in ordered)
            g['confidence']=min(w['confidence'] for w in g['words'])
            g['overlapping_words']=any(a['bbox'][2]-b['bbox'][0] > max(2,.1*min(
                a['bbox'][2]-a['bbox'][0],b['bbox'][2]-b['bbox'][0])) for a,b in zip(ordered,ordered[1:]))
            # Three agreeing OCR passes can repeat one glyph in overlapping
            # recognition windows. Do not concatenate those windows into text.
            if g['overlapping_words']:g['confidence']=0.
            if whole_lines and g['overlapping_words']:
                # Re-read the observed complete source row in one recognition
                # window; do not repair strings by deduplicating guessed glyphs.
                a,b,c,d=g['bbox'];pad=2
                a=max(0,int(np.floor(a))-pad);b=max(0,int(np.floor(b))-pad)
                c=min(crop.shape[1],int(np.ceil(c))+pad);d=min(crop.shape[0],int(np.ceil(d))+pad)
                g['whole_line_observation']=None
                if excluded is None or not excluded[y0+b:y0+d,x0+a:x0+c].any():
                    size=[1.,1.5,2.25][arm_index]
                    row=cv2.resize(crop[b:d,a:c],None,fx=size,fy=size,interpolation=cv2.INTER_CUBIC)
                    observed,_=engine(row,use_det=False,use_cls=False,use_rec=True)
                    if observed and len(observed)==1 and len(observed[0])==2:
                        text,confidence=observed[0]
                        g['whole_line_observation']=dict(text=text,confidence=float(confidence),source_bbox=[a,b,c,d])
                        g['text']=text.strip();g['confidence']=float(confidence) if confidence>=.98 else 0.
                    else:g['confidence']=0.
                else:g['confidence']=0.
        lines.append(sorted(groups,key=lambda g:g['bbox'][1]))
    accepted=[]
    for index,line in enumerate(lines[0]):
        if any(index>=len(arm) for arm in lines[1:]):break
        others=[arm[index] for arm in lines[1:]]
        if line['confidence']<.95 or any(other['confidence']<.95 or line['text']!=other['text'] or _iou(line['bbox'],other['bbox'])<.8 for other in others):break
        accepted.append(line)
    return '\n'.join(w['text'] for w in accepted) or None,dict(arms=arms,lines=lines,accepted=accepted,whole_lines=whole_lines,policy='complete stable prefix lines only')
