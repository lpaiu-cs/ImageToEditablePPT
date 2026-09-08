"""Conservative crop OCR: stable geometric order and agreement, never semantic repair."""
from dataclasses import replace
import cv2
from image_to_editable_ppt.v3.core.enums import PortOwnerKind
from image_to_editable_ppt.v3.text.ocr import _load_engine


def ordered_text(result):
    entries=[]
    for box,text,score in result or []:
        if not str(text).strip(): continue
        if float(score)<.90: return None,'low_confidence'
        xs,ys=zip(*box)
        entries.append((min(xs),min(ys),max(xs),max(ys),str(text).strip()))
    if not entries: return None,'empty'
    lines=[]
    for item in sorted(entries,key=lambda a:(a[1],a[0])):
        matches=[line for line in lines if min(line[0][3],item[3])-max(line[0][1],item[1])>.5*min(line[0][3]-line[0][1],item[3]-item[1])]
        if len(matches)>1: return None,'ambiguous_reading_order'
        if matches: matches[0].append(item)
        else: lines.append([item])
    # Within-line order must use x, not tiny y jitter from the OCR detector.
    for line in lines:
        line.sort(key=lambda a:a[0])
        if any(a[2]>b[0]+.2*min(a[2]-a[0],b[2]-b[0]) for a,b in zip(line,line[1:])):
            return None,'overlapping_snippets'
    return '\n'.join(' '.join(a[4] for a in line) for line in lines),'recognized'


def recognize_consistent(engine,crop):
    if engine is None: return None,dict(reason='backend_unavailable')
    try:
        first,_=engine(crop)
        second,_=engine(cv2.resize(crop,None,fx=1.5,fy=1.5,interpolation=cv2.INTER_CUBIC))
        a,ra=ordered_text(first); b,rb=ordered_text(second)
    except Exception as error:
        return None,dict(reason='backend_error',error_type=type(error).__name__)
    if a is None or b is None: return None,dict(reason=ra if a is None else rb)
    if ' '.join(a.split())!=' '.join(b.split()): return None,dict(reason='scale_disagreement')
    return a,dict(reason='two_scale_agreement',confidence_floor=.90)


def recover_labels(scene,rgb,*,enabled=True):
    engine=_load_engine() if enabled else None
    h,w=rgb.shape[:2]; shapes=[]; audit={}
    for s in scene.shapes:
        if s.owner_kind is not PortOwnerKind.NODE:
            shapes.append(s); continue
        b=s.bbox
        x0,y0=max(0,round(b.x0)+3),max(0,round(b.y0)+3)
        x1,y1=min(w,round(b.x1)-3),min(h,round(b.y1)-3)
        label=None; record=dict(reason='disabled' if not enabled else 'too_small')
        if enabled and x1-x0>=8 and y1-y0>=8:
            label,record=recognize_consistent(engine,rgb[y0:y1,x0:x1])
        shapes.append(replace(s,label=label)); audit[s.id]=record
    return replace(scene,shapes=tuple(shapes)),audit
