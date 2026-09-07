from dataclasses import replace
import cv2
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from image_to_editable_ppt.research.local_select import select_local
from image_to_editable_ppt.v3.core.enums import NodeKind,PortOwnerKind
from image_to_editable_ppt.v3.core.types import BBox,ImageSize
from image_to_editable_ppt.v3.emit.models import EmitScene,EmitShapePrimitive


def owner(name,box):
    return EmitShapePrimitive(name,PortOwnerKind.NODE,NodeKind.BOX,BBox(*box),.9,
        label='Unchanged OCR',source='visual_geometry:closed_outline')


def run(rgb,shapes,arm='guarded_scatter'):
    scene=EmitScene(image_size=ImageSize(rgb.shape[1],rgb.shape[0]),shapes=tuple(shapes))
    return select_local(scene,rgb,(0,0,1,1),arm)


def text_image(color,background):
    im=Image.new('RGB',(1200,600),background)
    d=ImageDraw.Draw(im)
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',64)
    d.text((80,150),'Circle Cross Attention',font=font,fill=color)
    d.text((80,310),'Image grounded encoder',font=font,fill=color)
    return np.asarray(im.resize((600,300),Image.Resampling.LANCZOS))


def test_colored_title_preserved():
    rgb=text_image((235,40,30),'white')
    s=owner('title',(10,10,590,290))
    out,a=run(rgb,[s])
    assert out.shapes==(s,)
    assert a['features']['title']['flags']['local_scatter']


def test_antialiased_dark_text_on_colored_fill_preserved():
    rgb=text_image((15,15,15),(202,238,251))
    s=owner('text',(10,10,590,290))
    out,_=run(rgb,[s])
    assert out.shapes==(s,)


def test_true_scatter_rejected_but_nested_child_survives():
    rgb=np.full((400,600,3),255,np.uint8)
    rng=np.random.default_rng(721)
    for x,y in rng.integers([25,25],[400,370],size=(150,2)):
        cv2.circle(rgb,(int(x),int(y)),2,(255,0,0),-1)
    cv2.rectangle(rgb,(440,150),(570,250),(0,0,0),2)
    parent=owner('parent',(10,10,590,390))
    child=owner('child',(440,150,570,250))
    for arm in ('local_scatter','guarded_scatter'):
        out,a=run(rgb,[parent,child],arm)
        assert out.shapes==(child,)
        assert a['removed']['parent']['evidence_owner']=='parent'


def test_blank_node_and_labels_survive_combined():
    rgb=np.full((200,300,3),255,np.uint8)
    cv2.rectangle(rgb,(20,20),(280,180),(0,0,0),2)
    s=owner('blank',(20,20,280,180))
    out,_=run(rgb,[s],'combined')
    assert out.shapes==(s,)
    renamed=replace(s,id='not-a-target',label='Different irrelevant text')
    out,_=run(rgb,[renamed],'combined')
    assert out.shapes==(renamed,)
