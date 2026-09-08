"""Observe native text direction from the same owner pixels, never from GT."""
from copy import deepcopy
import cv2
import numpy as np
from image_to_editable_ppt.research.closed_rect_proposals import observe_text


def physical_bbox(box,width,height,orientation):
    a,b,c,d=box
    if orientation=='clockwise':return [width-d,a,width-b,c]
    if orientation=='counterclockwise':return [b,height-c,d,height-a]
    raise ValueError('unknown text orientation')


def observe_portrait(rgb,box,excluded,engine):
    x0,y0,x1,y1=box
    if y1-y0<3*(x1-x0):return None,dict(reason='outside_portrait_scope',arms=[])
    crop=rgb[y0:y1,x0:x1];mask=excluded[y0:y1,x0:x1];arms=[]
    for name,rotation in [('clockwise',cv2.ROTATE_90_COUNTERCLOCKWISE),('counterclockwise',cv2.ROTATE_90_CLOCKWISE)]:
        patch=cv2.rotate(crop,rotation);omitted=cv2.rotate(mask,rotation)
        label,audit=observe_text(patch,[0,0,patch.shape[1],patch.shape[0]],engine,excluded=omitted,whole_lines=True)
        rereads=[];approved=False
        if label and len(audit['accepted'])==1 and len(audit['lines'][0])==1:
            a,b,c,d=audit['accepted'][0]['bbox']
            a=max(0,int(np.floor(a))-2);b=max(0,int(np.floor(b))-2)
            c=min(patch.shape[1],int(np.ceil(c))+2);d=min(patch.shape[0],int(np.ceil(d))+2)
            if not omitted[b:d,a:c].any():
                for size in (1.,1.5,2.25):
                    result,_=engine(cv2.resize(patch[b:d,a:c],None,fx=size,fy=size,interpolation=cv2.INTER_CUBIC),use_det=False,use_cls=False,use_rec=True)
                    rereads.append(dict(text=result[0][0].strip(),confidence=float(result[0][1]))
                        if result and len(result)==1 and len(result[0])==2 else dict(text='',confidence=0.))
                approved=all(r['text']==label and r['confidence']>=.98 for r in rereads)
        arms.append(dict(orientation=name,label=label,approved=approved,rereads=rereads,spatial=audit))
    accepted=[a for a in arms if a['approved']]
    return (accepted[0] if len(accepted)==1 else None),dict(arms=arms,reason='unique_source_orientation' if len(accepted)==1 else 'ambiguous_or_untrusted_orientation')


def source_line(selected,width,height):
    line=deepcopy(selected['spatial']['accepted'][0])
    line['bbox']=physical_bbox(line['bbox'],width,height,selected['orientation'])
    for word in line['words']:word['bbox']=physical_bbox(word['bbox'],width,height,selected['orientation'])
    return line


def place_portrait(shape,line,width,height,orientation,scale):
    from PIL import ImageFont
    from pptx.enum.text import MSO_ANCHOR,MSO_AUTO_SIZE,PP_ALIGN
    from pptx.dml.color import RGBColor
    from pptx.util import Emu,Pt
    a,b,c,d=line['bbox']
    if orientation not in ('clockwise','counterclockwise'):raise ValueError('unknown text orientation')
    if not (0<=a<c<=width and 0<=b<d<=height):raise ValueError('text outside owner')
    frame=shape.text_frame;frame.text=line['text']
    frame._txBody.bodyPr.set('vert','vert' if orientation=='clockwise' else 'vert270')
    emu=lambda v:Emu(round(v*scale*9525))
    frame.margin_left=emu(a);frame.margin_right=emu(width-c)
    frame.margin_top=emu(b);frame.margin_bottom=emu(height-d)
    frame.vertical_anchor=MSO_ANCHOR.MIDDLE;frame.auto_size=MSO_AUTO_SIZE.NONE;frame.word_wrap=False
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',100)
    size=min((c-a)*.85,(d-b)*95/max(1,font.getlength(line['text'])))*scale*.75
    paragraph=frame.paragraphs[0];paragraph.alignment=PP_ALIGN.CENTER
    paragraph.space_before=Pt(0);paragraph.space_after=Pt(0)
    fill=shape.fill.fore_color.rgb
    dark=sum(float(v)*w for v,w in zip(fill,(.2126,.7152,.0722)))<128
    for run in paragraph.runs:
        run.font.name='Arial';run.font.size=Pt(max(1,size))
        run.font.color.rgb=RGBColor(255,255,255) if dark else RGBColor(31,41,55)
    return dict(owner=shape.name,source_text_bbox=line['bbox'],native_text=frame.text,orientation=orientation,font_size_pt=size)
