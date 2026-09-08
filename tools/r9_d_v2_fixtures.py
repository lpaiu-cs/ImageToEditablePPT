"""Lock the unchanged v1 replay and new D-v2 controls without importing the observer."""
import argparse
from copy import deepcopy
import itertools
import json
from pathlib import Path

import numpy as np
from PIL import Image,ImageDraw

from r9_duplicate_owner_fixtures import owner,save,sha,expand


BASES=['row_clean','row_font_binary','row_font_aa','row_m15','row_p15','row_90',
       'individual_rotated','individual_rotated_loss','speck_far','speck_near','punct1','punct2','punct4',
       'bbox_shift_safe','bbox_shift_loss','independent','two_rows','chain','tie','crop_full','crop_context','crop_short',
       'bright12_separate','bright24_separate','bright32_separate','bright64_separate',
       'bright12_touch','bright24_touch','bright32_touch','bright64_touch']


def base(name):
    im=Image.new('RGB',(640,360),'white');draw=ImageDraw.Draw(im)
    for x in (300,311,322,333):
        draw.rectangle((x,160,x+1,170),fill='black')
        for dy in (0,5,10):draw.rectangle((x,160+dy,x+6,160+dy),fill='black')
    glyph=[300,160,340,171]
    owners=[owner('tight',expand(glyph,2),.55),owner('loose',expand(glyph,6,9),.99)]
    expect=dict(mode='select_or_abstain',allowed_keep='tight',category='content',new_clean=False)
    frame=None
    if name in ('row_clean','speck_far'):expect['new_clean']=True
    if name in ('row_font_binary','row_font_aa'):
        from PIL import ImageFont
        font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',14)
        im=Image.new('RGB',(640,360),'white');d=ImageDraw.Draw(im);d.text((300,155),'E E E E',font=font,fill='black')
        glyph=list(d.textbbox((300,155),'E E E E',font=font));owners=[owner('tight',expand(glyph,2),.55),owner('loose',expand(glyph,6,9),.99)]
        if name=='row_font_binary':im=Image.fromarray(np.where(np.array(im)<128,0,255).astype('uint8'))
    if name in ('row_m15','row_p15','row_90'):
        angle={'row_m15':-15,'row_p15':15,'row_90':90}[name];center=(320,165.5)
        im=im.rotate(angle,Image.Resampling.NEAREST,center=center,fillcolor='white')
        theta=np.deg2rad(-angle);matrix=np.array([[np.cos(theta),-np.sin(theta)],[np.sin(theta),np.cos(theta)]])
        for o in owners:
            a,b,c,d=o['bbox_xyxy'];pts=np.array([[a,b],[c,b],[c,d],[a,d]])
            pts=(pts-center)@matrix.T+center;o['bbox_xyxy']=[*pts.min(axis=0),*pts.max(axis=0)]
        expect.update(mode='preserve',category='scope')
    elif name.startswith('individual_rotated'):
        im=Image.new('RGB',(640,360),'white')
        for x in (300,313,326,339):
            patch=Image.new('RGB',(11,11),'white');d=ImageDraw.Draw(patch)
            d.rectangle((2,0,3,10),fill='black')
            for dy in (0,5,10):d.rectangle((2,dy,8,dy),fill='black')
            im.paste(patch.rotate(90),(x,160))
        owners=[owner('tight',[299,159,351,172],.55),owner('loose',[294,154,356,180],.99)]
        if name.endswith('loss'):
            owners[0]['bbox_xyxy'][2]=343;expect.update(mode='preserve')
        expect['pose_unverified']=True
    elif name.startswith('bright'):
        value=int(name.split('_')[0][6:]);touch=name.endswith('touch')
        x=340 if touch else 344
        draw.line((x,161,x,169),fill=(255-value,)*3,width=1)
        owners[1]['bbox_xyxy'][2]=349;expect.update(mode='preserve')
    elif name.startswith('punct'):
        size=int(name[5:]);draw.rectangle((343,169,343+size-1,169+size-1),fill='black')
        owners[1]['bbox_xyxy'][2]=351;expect.update(mode='preserve')
    elif name.startswith('speck'):
        xy=(320,198) if name=='speck_far' else (343,169)
        draw.point(xy,fill=(235,235,235));owners[1]['bbox_xyxy']=[294,154,348,200] if name=='speck_far' else [294,154,348,180]
        if name=='speck_near':expect.update(mode='preserve')
    elif name=='bbox_shift_safe':
        owners[1]['bbox_xyxy']=[v+(1 if i%2==0 else 0) for i,v in enumerate(owners[0]['bbox_xyxy'])]
        expect.update(mode='preserve_or_either',category='geometry_only')
    elif name=='bbox_shift_loss':
        draw.point((342,169),fill='black');owners[0]['bbox_xyxy'][2]=342;owners[1]['bbox_xyxy'][2]=343
        expect.update(mode='preserve')
    elif name=='independent':
        owners=[owner('left',[298,158,325,173]),owner('right',[320,158,342,173])];expect.update(mode='preserve',category='structure')
    elif name=='two_rows':
        im.paste(im.crop((300,160,340,171)),(300,180));owners=[owner('a',[298,156,342,183]),owner('b',[298,168,342,195])];expect.update(mode='preserve',category='structure')
    elif name=='chain':
        owners=[owner('a',[298,158,318,174]),owner('b',[314,158,332,174]),owner('c',[328,158,345,174])];expect.update(mode='preserve',category='structure')
    elif name=='tie':
        owners[1]['bbox_xyxy']=owners[0]['bbox_xyxy'].copy();expect.update(mode='preserve')
    elif name.startswith('crop'):
        if name=='crop_context':
            region=(200,80,450,280);source=__import__('hashlib').sha256(np.array(im).tobytes()).hexdigest()
            im=im.crop(region);frame=dict(origin_xy=[200,80],full_size=[640,360],source_sha256=source)
        elif name=='crop_short':
            region=(290,150,355,182);source=__import__('hashlib').sha256(np.array(im).tobytes()).hexdigest()
            im=im.crop(region);frame=dict(origin_xy=[290,150],full_size=[640,360],source_sha256=source);expect.update(mode='preserve',category='context')
    return im,owners,expect,frame


def build(args):
    args.out.mkdir(parents=True,exist_ok=False);(args.out/'rgb').mkdir();(args.out/'owners').mkdir()
    old=Path('artifacts/r9-d-v1-fixtures-build2');old_rows=json.loads((old/'manifest.json').read_text());old_e={r['id']:r for r in json.loads((old/'expectations.json').read_text())}
    rows=[];expectations=[]
    for r in old_rows:
        rows.append(dict(r,population='v1_replay',frame=None))
        e=deepcopy(old_e[r['id']]);e['historical_positive']=e['mode']=='select_or_abstain' and r['base'].startswith('positive')
        e.update(category='scope' if r['base'].startswith('rotation') or r['base']=='vertical' else 'content',new_clean=False)
        expectations.append(e)
    for name in BASES:
        scales=[1.] if name.startswith('crop') else [.75,1.,1.5]
        for scale,aa in itertools.product(scales,[False,True]):
            im,owners,e,frame=base(name)
            if aa:im=im.resize((im.width*2,im.height*2),Image.Resampling.BICUBIC).resize(im.size,Image.Resampling.LANCZOS)
            if frame is not None:
                # Transform the full frame first; the crop must be its exact pixel subset.
                full,_,_,_=base('crop_full')
                if aa:full=full.resize((1280,720),Image.Resampling.BICUBIC).resize(full.size,Image.Resampling.LANCZOS)
                ox,oy=frame['origin_xy'];im=full.crop((ox,oy,ox+im.width,oy+im.height))
                frame['source_sha256']=__import__('hashlib').sha256(np.array(full).tobytes()).hexdigest()
            if scale!=1:
                im=im.resize((round(im.width*scale),round(im.height*scale)),Image.Resampling.BOX if aa else Image.Resampling.NEAREST)
                owners=[dict(o,bbox_xyxy=[float(v*scale) for v in o['bbox_xyxy']]) for o in owners]
            key=f'v2-{name}-s{scale}-aa{int(aa)}';rp=args.out/'rgb'/f'{key}.png';im.save(rp)
            for reverse,swap in itertools.product((False,True),repeat=2):
                os=deepcopy(owners[::-1] if reverse else owners)
                if swap:
                    scores=[o['confidence'] for o in os][::-1]
                    for o,score in zip(os,scores):o['confidence']=score
                name_id=f'{key}-o{int(reverse)}-swap{int(swap)}';op=args.out/'owners'/f'{name_id}.json';save(op,os)
                rows.append(dict(id=name_id,base=name,population='v2_new',rgb=str(rp.resolve()),rgb_sha256=sha(rp),owners=str(op.resolve()),owners_sha256=sha(op),
                    frame=frame,geometry_group=key,order=int(reverse),score_swap=swap))
                expectations.append(dict(e,id=name_id,historical_positive=False,new_clean=bool(e['new_clean'] and scale==1 and not aa)))
    save(args.out/'manifest.json',rows);save(args.out/'expectations.json',expectations)
    lock=dict(schema='r9_d_v2_fixture_lock',phase='before_geometry_execution',v1_replay=len(old_rows),v2_new=len(rows)-len(old_rows),total=len(rows),
        new_base_count=len(BASES),new_bases=BASES,seed=901,noise_applied=False,
        font_sha256=sha('C:/Windows/Fonts/arial.ttf'),builder_sha256=sha(__file__),
        v1_lock_sha256=sha(old/'lock.json'),observer_sha256=sha('src/image_to_editable_ppt/research/duplicate_owner_v2.py'),
        helper_sha256=sha('src/image_to_editable_ppt/research/duplicate_owner_observations.py'),
        spec_sha256=sha('docs/r9_duplicate_owner_v2_spec.md'),manifest_sha256=sha(args.out/'manifest.json'),expectations_sha256=sha(args.out/'expectations.json'))
    save(args.out/'lock.json',lock);print(json.dumps(lock))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);build(p.parse_args())
