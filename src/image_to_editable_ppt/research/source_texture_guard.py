"""P texture diagnostic: inspect original descendants too, never inpaint them away."""
import cv2
import numpy as np


def inspect_texture(rgb,candidate,text_audit=None):
    x0,y0,x1,y1=candidate['bbox'];scale=rgb.shape[0]/360
    mask=np.zeros(rgb.shape[:2],np.uint8)
    cv2.drawContours(mask,[candidate['contour']],-1,1,cv2.FILLED)
    mask=cv2.erode(mask,np.ones((3,3),np.uint8))
    # Verified text is explained structure, not photographic texture. Never
    # remove an entire descendant: the PHOTOID caption counterexample relies
    # on leaving its photographic child available to this veto.
    for line in (text_audit or {}).get('observed_accepted',(text_audit or {}).get('accepted',[])):
        for word in line['words']:
            a,b,c,d=word['bbox'];pad=max(1,round(scale))
            mask[max(0,y0+int(b)-pad):y0+int(np.ceil(d))+pad,
                 max(0,x0+int(a)-pad):x0+int(np.ceil(c))+pad]=0
    step=max(12,round(16*scale));observed=0;textured=0;tiles=[]
    for y in range(y0,y1,step):
        for x in range(x0,x1,step):
            local=mask[y:min(y+step,y1),x:min(x+step,x1)]
            if local.size<step*step*.5 or local.mean()<.8:continue
            pixels=rgb[y:min(y+step,y1),x:min(x+step,x1)][local!=0]
            colors=len(np.unique(pixels//8,axis=0))
            variation=float(np.std(pixels.astype(float),axis=0).mean())
            covariance=np.cov(pixels.astype(float),rowvar=False)
            eigenvalues=np.linalg.eigvalsh(covariance)
            chromatic_rank=float(eigenvalues[-2]/max(1,eigenvalues[-1]))
            # Antialiased two-color text and a simple gradient are nearly a
            # line in RGB space. Many quantized colors alone are not texture.
            dense=colors>=48 and variation>=6 and chromatic_rank>=.05
            observed+=len(pixels);textured+=len(pixels)*int(dense)
            if dense:tiles.append([x,y,min(x+step,x1),min(y+step,y1)])
    fraction=textured/max(1,observed)
    return dict(eligible=fraction<=.2,reason='dense_source_texture' if fraction>.2 else 'no_dense_texture_veto',
                textured_fraction=fraction,observed_pixels=observed,textured_tiles=tiles,
                scope='texture veto only; absence is not a semantic diagram classification')
