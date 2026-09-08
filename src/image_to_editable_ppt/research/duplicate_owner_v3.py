"""D-v3 shared numeric/contact/support mechanisms; no OCR, files, or owner inference.

Revision history lives in Git. Callers supply image-derived masks, never GT masks.
These helpers do not decide that two owners are the same semantic entity.
"""
import math
import cv2
import numpy as np


LUMA_SCALE = 10000
CONTRAST_SCALE = 20000  # Twice luminance preserves the exact median of an even ring.


def luminance_numerator(rgb):
    if not isinstance(rgb,np.ndarray) or rgb.dtype!=np.uint8 or rgb.ndim<1 or rgb.shape[-1]!=3:
        raise ValueError('uint8 RGB with last dimension 3 required')
    x=rgb.astype(np.int64)
    return 2126*x[...,0]+7152*x[...,1]+722*x[...,2]


def integer_contrast(rgb,ring=None,*,background_luminance2=None):
    """Return exact integer contrast and masks. No epsilon or floating subtraction."""
    lum=luminance_numerator(rgb)
    if background_luminance2 is None:
        if ring is None or ring.shape!=lum.shape or ring.dtype!=bool or not ring.any():
            raise ValueError('nonempty boolean background ring required')
        values=np.sort(lum[ring])
        background_luminance2=int(values[(len(values)-1)//2])+int(values[len(values)//2])
    if not isinstance(background_luminance2,(int,np.integer)) or not 0<=background_luminance2<=510*LUMA_SCALE:
        raise ValueError('background luminance2 out of range')
    contrast=np.maximum(0,int(background_luminance2)-2*lum)
    return dict(luminance=lum,background_luminance2=int(background_luminance2),contrast2=contrast,
                core=contrast>=80*CONTRAST_SCALE,weak=contrast>=12*CONTRAST_SCALE,
                residual=(contrast>0)&(contrast<12*CONTRAST_SCALE))


def _mask(mask,shape=None):
    if not isinstance(mask,np.ndarray) or mask.dtype!=bool or mask.ndim!=2 or (shape is not None and mask.shape!=shape):
        raise ValueError('equal-size 2D boolean masks required')


def box_pixel_mask(shape,box,origin=(0,0)):
    if len(box)!=4 or not all(isinstance(v,(int,float)) and math.isfinite(v) for v in box) or box[0]>=box[2] or box[1]>=box[3]:
        raise ValueError('finite positive bbox required')
    yy,xx=np.indices(shape);xx=xx+origin[0]+.5;yy=yy+origin[1]+.5
    return (xx>=box[0])&(xx<box[2])&(yy>=box[1])&(yy<box[3])


def _near(mask):
    # Neighbour query only. It never changes the source mask or evidence.
    return cv2.dilate(mask.astype('uint8'),np.ones((3,3),'uint8')).astype(bool)


def shaft_glyph_contact_guard(shaft,glyph,*,original_ink=None,owner_mask=None):
    """Detect explicit contact and unresolved owner-boundary mixed components.

    Boundary ink can be shaft itself; the result is uncertainty, not proof of glyph.
    A caller must not silently discard this guard because a TLS line fit looks good.
    """
    _mask(shaft);_mask(glyph,shaft.shape)
    touching=_near(shaft)&glyph
    overlap=shaft&glyph
    reasons=[]
    if touching.any() or overlap.any():reasons.append('shaft_glyph_contact')
    mixed=[]
    if (original_ink is None)!=(owner_mask is None):raise ValueError('original ink and owner mask must be provided together')
    if original_ink is not None:
        _mask(original_ink,shaft.shape);_mask(owner_mask,shaft.shape)
        if np.any((shaft|glyph)&~original_ink):raise ValueError('candidate masks must come from original ink')
        count,labels=cv2.connectedComponents(original_ink.astype('uint8'),connectivity=8)
        for i in range(1,count):
            component=labels==i
            internal=component&owner_mask;external=component&~owner_mask
            if not (component&shaft).any() or not internal.any() or not external.any():continue
            contact=_near(internal)&external
            if contact.any():mixed.append(dict(component=i,inside_pixels=int(internal.sum()),outside_pixels=int(external.sum()),boundary_contacts=int(contact.sum())))
        if mixed:reasons.append('shaft_glyph_boundary_uncertain')
    return dict(safe=not reasons,reasons=reasons,neighbour_contact_pixels=int(touching.sum()),
                overlap_pixels=int(overlap.sum()),mixed_components=mixed)


def candidate_support_check(core,weak,residual,box,*,origin=(0,0),ignored=None):
    """Single eligibility rule for whole support, fringe, and negative padding.

    Pixel centers define ownership. Cell-edge padding may be negative without any
    center being lost. Partial same-component fringe is allowed only with core
    coverage >= .98, weak >= .95 and <= 1 original-pixel distance to the box.
    Whole atoms and partially lost core-free orphans are vetoed.
    """
    _mask(core);_mask(weak,core.shape);_mask(residual,core.shape)
    if np.any(core&~weak) or np.any(weak&residual):raise ValueError('core subset weak; residual disjoint required')
    if ignored is None:ignored=np.zeros_like(core)
    _mask(ignored,core.shape)
    if np.any(ignored&core):raise ValueError('core cannot be ignored')
    support=(weak|residual)&~ignored
    own=box_pixel_mask(core.shape,box,origin)
    count,labels=cv2.connectedComponents(support.astype('uint8'),connectivity=8)
    records=[];veto=[];boundary=[]
    ys_all,xs_all=np.where(support)
    padding=None
    if len(xs_all):
        bounds=[int(xs_all.min())+origin[0],int(ys_all.min())+origin[1],int(xs_all.max())+1+origin[0],int(ys_all.max())+1+origin[1]]
        padding=[bounds[0]-box[0],bounds[1]-box[1],box[2]-bounds[2],box[3]-bounds[3]]
    for i in range(1,count):
        atom=labels==i;lost=atom&~own;total=int(atom.sum());retained=int((atom&own).sum())
        nc=int((atom&core).sum());nw=int((atom&weak).sum())
        cc=float((atom&core&own).sum()/nc) if nc else None
        wc=float((atom&weak&own).sum()/nw) if nw else None
        row=dict(component=i,pixels=total,retained=retained,core_pixels=nc,weak_pixels=nw,
                 core_coverage=cc,weak_coverage=wc,classification='fully_retained')
        if lost.any():
            yy,xx=np.where(lost);xx=xx+origin[0]+.5;yy=yy+origin[1]+.5
            distances=np.hypot(np.maximum(np.maximum(box[0]-xx,xx-box[2]),0),np.maximum(np.maximum(box[1]-yy,yy-box[3]),0))
            row['lost_max_distance_original_px']=float(distances.max())
            if retained==0:row['classification']='whole_component_loss'
            elif not nc:row['classification']='orphan_support_unresolved'
            elif cc<.98 or (wc is not None and wc<.95):row['classification']='partial_support_loss'
            elif float(distances.max())>1:row['classification']='outside_boundary_band'
            else:row['classification']='boundary_quantization_difference';boundary.append(i)
            if row['classification']!='boundary_quantization_difference':veto.append(i)
        records.append(row)
    return dict(eligible=bool(records) and not veto,veto_components=veto,boundary_components=boundary,
                raw_cell_padding=padding,negative_padding=bool(padding is not None and min(padding)<0),
                negative_padding_is_not_a_separate_gate=True,empty_support=not records,components=records)


def background_speck_mask(core,support,contrast2,glyph_box,glyph_height,*,scale=1,origin=(0,0)):
    """Explicit narrow noise exception; proximity ambiguity remains protected."""
    _mask(core);_mask(support,core.shape)
    if contrast2.shape!=core.shape or not np.issubdtype(contrast2.dtype,np.integer):raise ValueError('integer contrast array required')
    if not math.isfinite(glyph_height) or glyph_height<=0 or scale<=0:raise ValueError('positive glyph height and scale required')
    ignored=np.zeros_like(core);records=[]
    count,labels=cv2.connectedComponents(support.astype('uint8'),connectivity=8)
    for i in range(1,count):
        atom=labels==i;yy,xx=np.where(atom)
        b=[xx.min()+origin[0],yy.min()+origin[1],xx.max()+1+origin[0],yy.max()+1+origin[1]]
        dx=max(glyph_box[0]-b[2],b[0]-glyph_box[2],0);dy=max(glyph_box[1]-b[3],b[1]-glyph_box[3],0)
        outside=b[2]<glyph_box[0]-2*glyph_height or b[0]>glyph_box[2]+2*glyph_height or b[3]<glyph_box[1]-2*glyph_height or b[1]>glyph_box[3]+2*glyph_height
        accept=bool(not (atom&core).any() and atom.sum()<=max(1,scale*scale) and contrast2[atom].max()<=24*CONTRAST_SCALE and math.hypot(dx,dy)>2*glyph_height and outside)
        if accept:ignored|=atom
        records.append(dict(component=i,ignored_as_background_speck=accept,pixels=int(atom.sum()),max_contrast2=int(contrast2[atom].max())))
    return ignored,records
