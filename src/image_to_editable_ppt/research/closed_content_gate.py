"""Conservative P research gate; geometric closure alone is not node evidence."""
import cv2
import numpy as np


def inspect_content(rgb, candidate, owned, text_audit):
    """Measure unexplained interior pixels after owned, stable OCR observations."""
    own=owned.copy()
    scale=rgb.shape[0]/360
    own=cv2.erode(own,np.ones((max(3,round(2*scale))|1,)*2,np.uint8))
    x,y,_,_=candidate['bbox']
    for line in text_audit['accepted']:
        for word in line['words']:
            a,b,c,d=word['bbox'];pad=max(1,round(scale))
            own[max(0,y+int(b)-pad):y+int(np.ceil(d))+pad,
                max(0,x+int(a)-pad):x+int(np.ceil(c))+pad]=0
    pixels=rgb[own!=0]
    if len(pixels)<max(12,.1*int(owned.sum())):
        return dict(eligible=False,reason='insufficient_unexplained_interior',observed_pixels=len(pixels))
    median=np.median(pixels,axis=0)
    fraction=float(np.mean(np.max(abs(pixels.astype(float)-median),axis=1)>24))
    return dict(eligible=fraction<=.05,reason='flat_owned_interior' if fraction<=.05 else 'unexplained_interior_content',
                unexplained_fraction=fraction,observed_pixels=len(pixels),median=median.tolist())


def admitted_ids(scene, content):
    """Unlabelled geometry needs a source-traced link to a labelled owner."""
    eligible={s.id for s in scene.shapes if content[s.id]['eligible']}
    labelled={s.id for s in scene.shapes if s.id in eligible and s.label}
    retained=set(labelled)
    for edge in scene.connectors:
        a,b=edge.source_owner_id,edge.target_owner_id
        if a in eligible and b in eligible and (a in labelled or b in labelled):
            retained.update((a,b))
    return retained
