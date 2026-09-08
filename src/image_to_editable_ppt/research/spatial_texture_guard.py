"""R11 opt-in texture veto from original spatial luminance variation."""
import cv2
import numpy as np
from image_to_editable_ppt.research.source_texture_guard import inspect_texture
from image_to_editable_ppt.research.closed_rect_proposals import _iou


def stable_texture_words(audit):
    """High-confidence later observations are text even when not exported."""
    result=[];db=(audit or {}).get('spatial_ocr',{});arms=db.get('arms',[])
    if len(arms)==3:
        for word in arms[0]:
            if word['confidence']<.98 or not word['text'].strip():continue
            if all(any(other['text']==word['text'] and other['confidence']>=.98 and
                _iou(word['bbox'],other['bbox'])>=.8 for other in arm) for arm in arms[1:]):
                result.append(dict(**word,texture_evidence='three_spatial_word_observations'))
    for row in (audit or {}).get('source_rows',{}).get('bands',[]):
        obs=row.get('observations',[])
        if row.get('reason')=='stable_source_row' and len(obs)==3 and obs[0]['text'] and all(
            o['confidence']>=.98 and o['text']==obs[0]['text'] for o in obs):
            result.append(dict(text=obs[0]['text'],bbox=row['bbox'],confidence=min(o['confidence'] for o in obs),texture_evidence='three_source_row_observations'))
    return result


def spatial_tile(rgb,mask,lag,*,palette_guard=False):
    luminance=(rgb.astype(np.int64)@np.array([2126,7152,722]))/10000
    pixels=luminance[mask!=0]
    if len(pixels)<12:return dict(dense=False,reason='insufficient_pixels')
    deviation=float(np.std(pixels));bins=pixels.astype(np.uint8)//8;levels=len(np.unique(bins))
    counts=np.bincount(bins,minlength=32)
    two_tone_fraction=float(np.sort(counts)[-2:].sum()/len(pixels))
    horizontal=(mask[:,lag:]!=0)&(mask[:,:-lag]!=0)
    vertical=(mask[lag:]!=0)&(mask[:-lag]!=0)
    dx=float(np.mean(abs(luminance[:,lag:]-luminance[:,:-lag])[horizontal])) if horizontal.any() else 0.
    dy=float(np.mean(abs(luminance[lag:]-luminance[:-lag])[vertical])) if vertical.any() else 0.
    roughness=(dx+dy)/(2*max(1,deviation));axis_ratio=min(dx,dy)/max(1e-9,dx,dy)
    dense=bool(levels>=12 and deviation>=8 and roughness>=.15 and axis_ratio>=.1)
    return dict(dense=dense and not (palette_guard and two_tone_fraction>=.75),
        gray_levels=levels,two_tone_fraction=two_tone_fraction,palette_guard=palette_guard,
        deviation=deviation,roughness=roughness,axis_ratio=axis_ratio,mean_dx=dx,mean_dy=dy)


def inspect_spatial_texture(rgb,candidate,text_audit=None,*,palette_guard=False,all_text_regions=False):
    additional=stable_texture_words(text_audit) if all_text_regions else []
    audit=text_audit or {}
    if additional:
        lines=audit.get('observed_accepted',audit.get('accepted',[]))
        audit=dict(audit,observed_accepted=[*lines,dict(words=additional)])
    old=inspect_texture(rgb,candidate,audit);x0,y0,x1,y1=candidate['bbox'];scale=rgb.shape[0]/360
    mask=np.zeros(rgb.shape[:2],np.uint8)
    cv2.drawContours(mask,[candidate['contour']],-1,1,cv2.FILLED)
    mask=cv2.erode(mask,np.ones((3,3),np.uint8))
    for line in audit.get('observed_accepted',audit.get('accepted',[])):
        for word in line['words']:
            a,b,c,d=word['bbox'];pad=max(1,round(scale))
            mask[max(0,y0+int(b)-pad):y0+int(np.ceil(d))+pad,max(0,x0+int(a)-pad):x0+int(np.ceil(c))+pad]=0
    step=max(12,round(16*scale));lag=max(1,round(scale));observed=0;textured=0;tiles=[];records=[]
    old_tiles={tuple(t) for t in old['textured_tiles']}
    for y in range(y0,y1,step):
        for x in range(x0,x1,step):
            right=min(x+step,x1);bottom=min(y+step,y1);local=mask[y:bottom,x:right]
            if local.size<step*step*.5 or local.mean()<.8:continue
            measured=spatial_tile(rgb[y:bottom,x:right],local,lag,palette_guard=palette_guard);box=[x,y,right,bottom]
            dense=measured['dense'] or tuple(box) in old_tiles;count=int(np.count_nonzero(local))
            observed+=count;textured+=count*int(dense)
            if dense:tiles.append(box)
            records.append(dict(bbox=box,**measured))
    fraction=textured/max(1,observed)
    return dict(eligible=fraction<=.2,reason='dense_spatial_or_color_texture' if fraction>.2 else 'no_spatial_texture_veto',
        textured_fraction=fraction,observed_pixels=observed,textured_tiles=tiles,spatial_tiles=records,legacy=old,palette_guard=palette_guard,
        all_text_regions=all_text_regions,additional_text_regions=additional,
        scope='opt-in texture veto only, not general semantic classification')
