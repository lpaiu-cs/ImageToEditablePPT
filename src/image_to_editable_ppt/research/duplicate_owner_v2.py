"""D-v2: observed horizontal rows, weak support and loss veto. No file IO or OCR."""
from copy import deepcopy
import hashlib
import itertools
import math

import numpy as np

from image_to_editable_ppt.research.duplicate_owner_observations import (
    FIELDS, atoms, components, digest, inside, mask_digest, overlap,
)

PARAMETERS = dict(core_contrast=80,weak_contrast=12,min_row_atoms=3,min_eigen_ratio=4,
    row_angle_degrees=5,row_residual_fraction=.25,row_span_heights=2,
    core_coverage=.98,weak_coverage=.95,background_speck_contrast=24,
    boundary_band_original_px=1,angle_guard='heuristic_not_TLS_error_bound',
    no_worse=[.01,.05,.05],better=[.05,.25,.25])


def _tls(xy):
    center=xy.mean(axis=0); centered=xy-center
    values,vectors=np.linalg.eigh(centered.T@centered/len(xy))
    axis=vectors[:,1]
    if axis[0]<0:axis=-axis
    along=centered@axis; perpendicular=centered@np.array([-axis[1],axis[0]])
    return center,axis,values,along,perpendicular


def _shaft(xy, union, h, s):
    if len(xy)<2:return False,False,{}
    center,axis,values,along,perp=_tls(xy)
    occupied=inside(xy[:,0],xy[:,1],union)
    span=float(np.ptp(along)); outside=float(np.ptp(along[~occupied])) if (~occupied).sum()>1 else 0.
    p95=float(np.percentile(abs(perp),95)); maximum=float(abs(perp).max()); width=float(np.ptp(perp))
    long=span>=3*h
    accepted=bool(long and outside>=h and p95<=1.5*s and maximum<=3*s and width<=6*s)
    uncertain=bool(long and occupied.any() and (~occupied).any() and not accepted)
    return accepted,uncertain,dict(center=center.tolist(),axis=axis.tolist(),eigenvalues=values.tolist(),
        span=span,outside_span=outside,p95=p95,maximum=maximum,width=width)


def _cluster(rgb, group, full_size, origin, masks):
    s=full_size[1]/360
    boxes=[o['bbox_xyxy'] for o in group]
    union=[min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes)]
    h=float(np.median([b[3]-b[1] for b in boxes]));pad=math.ceil(3*h)
    crop=[math.floor(union[0])-pad,math.floor(union[1])-pad,math.ceil(union[2])+pad,math.ceil(union[3])+pad]
    row=dict(ids=[o['id'] for o in group],crop_xyxy=crop,reasons=[],winner=None,
        scope='horizontal_atom_row_only',individual_glyph_pose='unverified',atoms=[],candidate_losses=[])
    x,y,r,b=crop; ox,oy=origin
    if x<ox or y<oy or r>ox+rgb.shape[1] or b>oy+rgb.shape[0]:
        row['reasons']=['insufficient_context'];return row
    if max(r-x,b-y)>256*s:
        row['reasons']=['crop_too_large'];return row
    pixels=rgb[y-oy:b-oy,x-ox:r-ox].astype(float)
    lum=pixels@np.array([.2126,.7152,.0722]);ring=np.ones(lum.shape,bool);n=math.ceil(2*s)
    if min(ring.shape)>2*n:ring[n:-n,n:-n]=False
    bg=float(np.median(lum[ring]));p10,p90=np.percentile(lum[ring],[10,90])
    row['background']=dict(median=bg,p10=float(p10),p90=float(p90),channel_median=np.median(pixels[ring],axis=0).tolist())
    if bg<225 or p90-p10>30:
        row['reasons']=['background_unsupported'];return row
    contrast=np.maximum(0,bg-lum);core=contrast>=80;weak=contrast>=12
    shaft=np.zeros_like(core);unresolved=np.zeros_like(core)
    yy,xx=np.indices(core.shape);xx=xx+x+.5;yy=yy+y+.5
    owns=[inside(xx,yy,box) for box in boxes]
    reasons=set(); supports=[]
    for k,a in enumerate(atoms(weak,(x,y))):
        ys,xs=a['ys'],a['xs'];xy=np.column_stack((xs+x+.5,ys+y+.5))
        yes,uncertain,tls=_shaft(xy,union,h,s)
        c=core[ys,xs]; core_yes,_,_=_shaft(xy[c],union,h,s) if c.any() else (False,False,{})
        if yes!=core_yes and (yes or core_yes):uncertain=True;yes=False
        if yes:shaft[ys,xs]=True
        if uncertain:unresolved[ys,xs]=True
        record={key:value for key,value in a.items() if key not in ('ys','xs')}
        record.update(id=k,core_count=int(c.sum()),contrast_min=float(contrast[ys,xs].min()),
            contrast_max=float(contrast[ys,xs].max()),contrast_median=float(np.median(contrast[ys,xs])),
            tls=tls,shaft_like=yes,unresolved=uncertain,
            weak_coverage=[float(own[ys,xs].mean()) for own in owns],
            core_coverage=[float(own[ys[c],xs[c]].mean()) if c.any() else None for own in owns])
        row['atoms'].append(record)
        if uncertain and any(own[ys,xs].any() for own in owns):reasons.add('shaft_glyph_uncertain')
        if not yes and not uncertain and any(own[ys,xs].any() for own in owns):supports.append((a,record))
    glyph=weak&~shaft&~unresolved
    for key,mask in dict(core=core,weak=weak,shaft=shaft,unresolved=unresolved,glyph=glyph,
                          dark110=lum<=110,dark140=lum<=140,dark170=lum<=170).items():
        sh=mask_digest(mask);masks[sh]=mask.copy();row.setdefault('masks',{})[key]=dict(sha256=sh,count=int(mask.sum()))
    strong=[(a,r) for a,r in supports if r['core_count']>0]
    if not strong:reasons.add('insufficient_core')
    row_atoms=[(a,r) for a,r in strong if a['area']>=2*s*s and 3*s<=a['box'][3]-a['box'][1]<=24*s]
    orientation=dict(atom_count=len(row_atoms),guard='heuristic_not_TLS_error_bound')
    row['orientation']=orientation
    if len(row_atoms)<3:
        reasons.add('orientation_unobservable')
    else:
        centers=np.array([[a['xs'].mean()+x+.5,a['ys'].mean()+y+.5] for a,_ in row_atoms])
        _,axis,eigen,along,perp=_tls(centers);span=float(np.ptp(along))
        mh=float(np.median([a['box'][3]-a['box'][1] for a,_ in row_atoms]))
        angle=abs(math.degrees(math.atan2(axis[1],axis[0])))
        delta=math.degrees(math.atan2(math.sqrt(2),span))
        residual=float(abs(perp).max())
        orientation.update(eigenvalues=eigen.tolist(),span=span,median_height=mh,angle=angle,delta=delta,max_residual=residual)
        if eigen[1]<=0 or eigen[1]<4*max(eigen[0],1e-12):reasons.add('orientation_eigen_gap_insufficient')
        elif span<2*mh:reasons.add('orientation_unobservable')
        elif angle-delta>5:reasons.add('unsupported_orientation')
        elif angle+delta>5 or residual>.25*mh:reasons.add('orientation_ambiguous')
    if strong:
        bglyph=[min(a['box'][0] for a,_ in strong),min(a['box'][1] for a,_ in strong),
                max(a['box'][2] for a,_ in strong),max(a['box'][3] for a,_ in strong)]
        mh=float(np.median([a['box'][3]-a['box'][1] for a,_ in strong]))
        band=[bglyph[0]-2*mh,bglyph[1]-2*mh,bglyph[2]+2*mh,bglyph[3]+2*mh]
        active=[]
        for a,r in supports:
            ab=a['box'];dx=max(bglyph[0]-ab[2],ab[0]-bglyph[2],0);dy=max(bglyph[1]-ab[3],ab[1]-bglyph[3],0)
            outside_band=ab[2]<=band[0] or ab[0]>=band[2] or ab[3]<=band[1] or ab[1]>=band[3]
            ignored=bool(r['core_count']==0 and a['area']<=max(1,s*s) and r['contrast_max']<=24 and math.hypot(dx,dy)>2*mh and outside_band)
            r['isolated_low_contrast_background_speck']=ignored
            if not ignored:active.append((a,r))
        support_mask=np.zeros_like(core)
        for a,r in strong:support_mask[a['ys'],a['xs']]=True
        area_g=(bglyph[2]-bglyph[0])*(bglyph[3]-bglyph[1]);losses=[]
        for i,box in enumerate(boxes):
            veto=[];boundary=[]
            for a,r in active:
                fraction=r['weak_coverage'][i];cc=r['core_coverage'][i]
                if max(r['weak_coverage'])==0:continue
                lost=~owns[i][a['ys'],a['xs']]
                if fraction==0:
                    veto.append(dict(atom=r['id'],reason='whole_component_loss' if r['core_count'] else 'weak_orphan_unresolved'));continue
                if lost.any():
                    px=a['xs'][lost]+x+.5;py=a['ys'][lost]+y+.5
                    distance=np.hypot(np.maximum(np.maximum(box[0]-px,px-box[2]),0),np.maximum(np.maximum(box[1]-py,py-box[3]),0))
                    if (cc is not None and cc<.98) or fraction<.95 or float(distance.max())>1 or r['core_count']==0:
                        veto.append(dict(atom=r['id'],reason='punctuation_or_noise_unresolved' if a['area']<=max(1,2*s*s) else 'possible_information_loss'))
                    else:boundary.append(r['id'])
            padding=[bglyph[0]-box[0],bglyph[1]-box[1],box[2]-bglyph[2],box[3]-bglyph[3]]
            vector=[float((shaft&owns[i]).sum()/max(1,(weak&owns[i]).sum())),
                    max(0,((box[2]-box[0])*(box[3]-box[1])-area_g)/area_g),
                    (abs(padding[0]-padding[2])+abs(padding[1]-padding[3]))/(bglyph[3]-bglyph[1])]
            losses.append(dict(id=group[i]['id'],losses=vector,veto=veto,boundary_quantization_difference=boundary,
                               padding=padding,eligible=not veto))
        row['glyph_bbox']=bglyph;row['candidate_losses']=losses
        # A cluster whose candidates own different actual support is not a duplicate decision.
        if any(item['veto'] for item in losses):reasons.add('possible_information_loss')
        domination=[]
        for i,a in enumerate(losses):
            domination.append([bool(i!=j and a['eligible'] and np.all(np.array(a['losses'])<=np.array(b['losses'])+[.01,.05,.05]) and
                np.any(np.array(a['losses'])<=np.array(b['losses'])-[.05,.25,.25])) for j,b in enumerate(losses)])
        winners=[i for i in range(len(group)) if all(domination[i][j] for j in range(len(group)) if j!=i)]
        row['dominance']=domination
        if len(winners)!=1:reasons.add('representative_ambiguous')
        elif not reasons:row['winner']=group[winners[0]]['id']
    row['reasons']=sorted(reasons)
    return row


def observe_owners_v2(rgb,owners,*,arm='V2-O',frame=None):
    if arm not in ('V2-O','V2-S'):raise ValueError('invalid arm')
    if not isinstance(rgb,np.ndarray) or rgb.dtype!=np.uint8 or rgb.ndim!=3 or rgb.shape[2]!=3 or min(rgb.shape[:2])<1:raise ValueError('invalid RGB')
    if frame is None:origin=(0,0);full_size=(rgb.shape[1],rgb.shape[0])
    else:
        if set(frame)!={'origin_xy','full_size','source_sha256'}:raise ValueError('missing_frame_context')
        origin=tuple(frame['origin_xy']);full_size=tuple(frame['full_size'])
        if len(origin)!=2 or len(full_size)!=2 or any(not isinstance(v,int) for v in (*origin,*full_size)):raise ValueError('invalid frame')
        if min(origin)<0 or min(full_size)<1 or origin[0]+rgb.shape[1]>full_size[0] or origin[1]+rgb.shape[0]>full_size[1]:raise ValueError('invalid frame bounds')
        if not isinstance(frame['source_sha256'],str) or len(frame['source_sha256'])!=64:raise ValueError('invalid source digest')
    ids=set()
    for o in owners:
        if set(o)!=FIELDS:raise ValueError('owner whitelist violation')
        if not isinstance(o['id'],str) or not o['id'] or o['id'] in ids:raise ValueError('duplicate or invalid ID')
        ids.add(o['id']);b=o['bbox_xyxy']
        if len(b)!=4 or not all(isinstance(v,(int,float)) and math.isfinite(v) for v in b):raise ValueError('invalid bbox')
        if not 0<=b[0]<b[2]<=full_size[0] or not 0<=b[1]<b[3]<=full_size[1]:raise ValueError('invalid bbox bounds')
        if not isinstance(o['semantic_kind'],str) or not isinstance(o['confidence'],(int,float)) or not math.isfinite(o['confidence']) or not 0<=o['confidence']<=1:raise ValueError('invalid owner metadata')
    selected=sorted([o for o in owners if o['semantic_kind']=='label_anchor'],key=lambda o:o['id'])
    adj=[set() for _ in selected]
    for i,j in itertools.combinations(range(len(selected)),2):
        if overlap(selected[i]['bbox_xyxy'],selected[j]['bbox_xyxy'])[0]>0:adj[i].add(j);adj[j].add(i)
    rows=[];masks={};suppressed=set()
    for indices in components(adj):
        if len(indices)<2:continue
        group=[selected[i] for i in indices]
        if len(group)>4:r=dict(ids=[o['id'] for o in group],reasons=['cluster_too_large'],winner=None)
        elif any(j not in adj[i] for i,j in itertools.combinations(indices,2)):r=dict(ids=[o['id'] for o in group],reasons=['overlap_chain'],winner=None)
        else:r=_cluster(rgb,group,full_size,origin,masks)
        rows.append(r)
        if r['winner'] is not None:suppressed.update(o['id'] for o in group if o['id']!=r['winner'])
    removed=suppressed if arm=='V2-S' else set()
    output=deepcopy([o for o in owners if o['id'] not in removed])
    return output,dict(schema='r9_duplicate_owner_v2',arm=arm,parameters=deepcopy(PARAMETERS),
        full_size=list(full_size),origin_xy=list(origin),owners_sha256=digest(owners),rgb_sha256=hashlib.sha256(rgb.tobytes()).hexdigest(),
        source_frame_sha256=None if frame is None else frame['source_sha256'],clusters=rows,
        kept_ids=[o['id'] for o in output],proposed_suppressed_ids=sorted(suppressed),suppressed_ids=sorted(removed)),masks
