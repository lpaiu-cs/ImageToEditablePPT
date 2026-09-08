"""Build and lock R9-D controls before any observer execution. Never runs the 15-image arm."""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import platform

import numpy as np
from PIL import Image, ImageDraw, ImageFont, __version__ as pillow_version


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def owner(key, box, score=.9):
    return dict(id=key, semantic_kind='label_anchor', bbox_xyxy=list(box), confidence=score)


def expand(b, x, y=None):
    y=x if y is None else y
    return [b[0]-x,b[1]-y,b[2]+x,b[3]+y]


def build_base(name, font, shaft_shift):
    im=Image.new('RGB',(640,360),'white'); draw=ImageDraw.Draw(im)
    expect=dict(mode='preserve', required_clean_positive=False)
    def text(word,xy):
        draw.text(xy,word,font=font,fill='black')
        return list(draw.textbbox(xy,word,font=font))
    def bitmap(x=300,y=160):
        # Connected E atom, 7x11, intentionally not isotropic.
        draw.rectangle((x,y,x+1,y+10),fill='black')
        for offset in (0,5,10): draw.rectangle((x,y+offset,x+6,y+offset),fill='black')
        return [x,y,x+7,y+11]
    if name in ('positive_bitmap','positive_font','positive_shaft','tie','tradeoff','blank','gray_background',
                'color_background','gradient','texture','rotation_m15','rotation_p15','rotation_90','vertical'):
        b=text('PP',(300,156)) if name=='positive_font' else bitmap()
        owners=[owner('a',expand(b,2),.4),owner('b',expand(b,6,9),.99)]
        if name.startswith('positive'):
            expect=dict(mode='select_or_abstain', allowed_keep='a', required_clean_positive=name=='positive_bitmap')
        if name=='positive_shaft':
            draw.line((303,b[3]+3+shaft_shift,303,240),fill='black',width=2)
        if name=='tie': owners[1]['bbox_xyxy']=owners[0]['bbox_xyxy'].copy()
        if name=='tradeoff':
            owners=[owner('a',[b[0]-1,b[1]-1,b[2]+1,b[3]+7]),owner('b',expand(b,5))]
        if name=='blank': im=Image.new('RGB',im.size,'white')
        if name in ('gray_background','color_background','gradient','texture'):
            a=np.asarray(im).copy(); white=(a==255).all(axis=2)
            if name=='gray_background': a[white]=180
            elif name=='color_background': a[white]=[180,220,170]
            elif name=='gradient':
                ramp=np.tile(np.linspace(80,250,640,dtype=np.uint8),(360,1)); a[white]=np.repeat(ramp[:,:,None],3,axis=2)[white]
            else:
                rng=np.random.default_rng(901); a[white]=rng.integers(40,240,size=a.shape,dtype=np.uint8)[white]
            im=Image.fromarray(a)
        if name.startswith('rotation_') or name=='vertical':
            angle={'rotation_m15':-15,'rotation_p15':15,'rotation_90':90,'vertical':90}[name]
            # Rotate pixels and bbox corners together, so clipping is not a hidden abstention shortcut.
            center=((b[0]+b[2])/2,(b[1]+b[3])/2)
            im=im.rotate(angle,resample=Image.Resampling.NEAREST,center=center,fillcolor='white')
            theta=np.deg2rad(-angle); matrix=np.array([[np.cos(theta),-np.sin(theta)],[np.sin(theta),np.cos(theta)]])
            for o in owners:
                x0,y0,x1,y1=o['bbox_xyxy']; pts=np.array([[x0,y0],[x1,y0],[x1,y1],[x0,y1]])
                pts=(pts-center)@matrix.T+center
                o['bbox_xyxy']=[*pts.min(axis=0),*pts.max(axis=0)]
    elif name in ('near_same','near_different'):
        # Distinct bitmap glyph cores, overlapping padding: IoU=13/27.
        bitmap(299,160); bitmap(318,160)
        if name=='near_different': draw.rectangle((319,164,324,166),fill='white')
        owners=[owner('a',[298,158,318,174]),owner('b',[305,158,325,174])]
    elif name.startswith('repeat_'):
        word=name.split('_',1)[1]; count=3 if word=='cat' else 2
        owners=[]
        for i in range(count):
            b=text(word,(150+i*110,160)); owners.append(owner(str(i),expand(b,3)))
            draw.line(((b[0]+b[2])/2,b[3]+4+shaft_shift,(b[0]+b[2])/2,240),fill='black',width=2)
    elif name in ('partial_root','partial_il','punctuation','superscript'):
        word='ROOT' if name=='partial_root' else 'Il' if name=='partial_il' else 'A'
        b=text(word,(300,156)); owners=[owner('a',expand(b,2))]
        if name=='partial_root': owners.append(owner('b',[b[0]+8,b[1]-1,b[2]-6,b[3]+1]))
        elif name=='partial_il': owners.append(owner('b',[b[0]-1,b[1]-1,(b[0]+b[2])/2,b[3]+1]))
        elif name=='punctuation':
            draw.point((b[2]+2,b[3]-1),fill='black'); owners.append(owner('b',expand(b,6)))
        else:
            c=text('2',(b[2]+1,148)); owners.append(owner('b',[b[0]-2,c[1]-2,c[2]+2,b[3]+2]))
    elif name.startswith('baseline_'):
        gap=int(name.split('_')[1]); b=text('CP',(300,156)); c=text('PP',(300,b[3]+gap-3))
        owners=[owner('a',expand(b,5)),owner('b',expand(c,5))]
    elif name.startswith('contact_') or name in ('underline','parallel_i','joined_labels'):
        gap=int(name.split('_')[1]) if name.startswith('contact_') else 0
        b=text('I' if name=='parallel_i' else 'CP',(300,156)); c=text('PP',(322,156))
        owners=[owner('a',expand(b,5)),owner('b',expand(c,5))]
        if name=='underline': draw.line((b[0],b[3]+shaft_shift,c[2],b[3]+shaft_shift),fill='black',width=2)
        elif name=='parallel_i': draw.line((b[2]+1+shaft_shift,b[1],b[2]+1+shaft_shift,b[3]+55),fill='black',width=2)
        elif name=='joined_labels': draw.line((b[2]-1,b[1]+5,c[0]+1,c[1]+5),fill='black',width=2)
        else: draw.line((b[0]+3,b[3]+gap+shaft_shift,b[0]+3,240),fill='black',width=2)
    elif name=='chain':
        for x in (285,306,327): bitmap(x,160)
        owners=[owner('a',[283,158,309,174]),owner('b',[301,158,322,174]),owner('c',[316,158,336,174])]
    elif name=='fanout':
        owners=[]
        for key,word,xy in [('hub','VP',(310,90)),('left','Det',(250,220)),('right','dog',(365,220))]:
            b=text(word,xy); owners.append(owner(key,expand(b,2)))
        start=(320,110+shaft_shift)
        for end in ((263,215),(377,215)):
            draw.line((start,end),fill='black',width=3)
            direction=np.array(end)-start; direction=direction/np.linalg.norm(direction); normal=np.array([-direction[1],direction[0]])
            draw.polygon([end,tuple(np.array(end)-9*direction+4*normal),tuple(np.array(end)-9*direction-4*normal)],fill='black')
    elif name=='clipped':
        b=text('PP',(4,10)); owners=[owner('a',expand(b,1)),owner('b',[1,5,b[2]+7,b[3]+7])]
    else: raise ValueError(name)
    return im,owners,expect


BASES=['positive_bitmap','positive_font','positive_shaft','tie','tradeoff','blank',
 'gray_background','color_background','gradient','texture','rotation_m15','rotation_p15','rotation_90','vertical',
 'near_same','near_different','repeat_CP','repeat_PP','repeat_cat','repeat_runs',
 'partial_root','partial_il','punctuation','superscript','baseline_2','baseline_4','baseline_8',
 'contact_0','contact_1','contact_3','underline','parallel_i','joined_labels','chain','fanout','clipped']


def build(args):
    out=args.out
    out.mkdir(parents=True,exist_ok=False)
    for folder in ('rgb','owners'): (out/folder).mkdir()
    font_path=Path('C:/Windows/Fonts/arial.ttf'); font=ImageFont.truetype(str(font_path),14)
    records=[]; expected=[]
    for name,scale,shift,color,aa in itertools.product(BASES,[.75,1.,1.5],[0,1],[0,100],[False,True]):
        im,owners,expect=build_base(name,font,shift)
        if color:
            a=np.asarray(im).copy(); a[(a==0).all(axis=2)]=color; im=Image.fromarray(a)
        if aa:
            # Explicit deterministic supersampling roundtrip, not a claim of native font AA.
            im=im.resize((1280,720),Image.Resampling.BICUBIC).resize(im.size,Image.Resampling.LANCZOS)
        if scale!=1:
            im=im.resize((round(640*scale),round(360*scale)),Image.Resampling.LANCZOS if aa else Image.Resampling.NEAREST)
        owners=[dict(o,bbox_xyxy=[float(v*scale) for v in o['bbox_xyxy']]) for o in owners]
        rgb_key=f'{name}-s{scale}-g{shift}-c{color}-aa{int(aa)}'
        rgb_path=out/'rgb'/f'{rgb_key}.png'; im.save(rgb_path)
        permutations=list(itertools.permutations(range(3))) if name=='chain' else [tuple(range(len(owners))),tuple(reversed(range(len(owners))))]
        for order_index,order in enumerate(permutations):
            for swap in (False,True):
                ordered=[dict(owners[i]) for i in order]
                if swap:
                    scores=[o['confidence'] for o in ordered][::-1]
                    ordered=[dict(o,confidence=scores[i]) for i,o in enumerate(ordered)]
                key=f'{rgb_key}-o{order_index}-swap{int(swap)}'
                op=out/'owners'/f'{key}.json';save(op,ordered)
                records.append(dict(id=key,base=name,rgb=str(rgb_path.resolve()),rgb_sha256=sha(rgb_path),
                    owners=str(op.resolve()),owners_sha256=sha(op),geometry_group=rgb_key,order=order_index,score_swap=swap))
                expected.append({**expect,'id':key,'required_clean_positive':bool(expect['required_clean_positive'] and scale==1 and shift==0 and color==0 and not aa)})
    # R8 PP is the only actual-image fixture; this is not the 15-image D-O/D-S arm.
    source=Path('artifacts/ml-image-only-v1/rgb/tree_1302_00149.png')
    handoff=json.loads(Path('artifacts/ml-image-only-v2/baseline.handoff.final.json').read_text())['payload']
    sample=next(s for s in handoff['samples'] if s['source_record_id']=='tree_1302_00149')
    original=Image.open(source).convert('RGB')
    for crop_name,region in [('full',[0,0,640,360]),('crop',[300,110,420,250])]:
        im=original.crop(region);rp=out/'rgb'/f'pp-real-{crop_name}.png'; im.save(rp)
        os=[owner('det'+str(o['source_detection_index']),[v-region[i%2] for i,v in enumerate(o['bbox_xyxy'])],o['confidence'])
            for o in sample['objects'] if o['source_detection_index'] in (9,11)]
        for reverse,swap in itertools.product((False,True),repeat=2):
            ordered=os[::-1] if reverse else os.copy()
            if swap: ordered=[dict(o,confidence=ordered[1-i]['confidence']) for i,o in enumerate(ordered)]
            key=f'pp-real-{crop_name}-o{int(reverse)}-swap{int(swap)}';op=out/'owners'/f'{key}.json';save(op,ordered)
            records.append(dict(id=key,base='pp_real',rgb=str(rp.resolve()),rgb_sha256=sha(rp),owners=str(op.resolve()),owners_sha256=sha(op),geometry_group=f'pp-real-{crop_name}',order=int(reverse),score_swap=swap))
            expected.append(dict(id=key,mode='select_or_abstain',allowed_keep='det11',required_clean_positive=False))
    save(out/'expectations.json',expected)
    save(out/'manifest.json',records)
    lock=dict(schema='r9_d_fixture_lock_v1',phase='generated_before_observer_execution',seed=901,random_noise_applied=False,
        count=len(records),unique_rgb=len({r['rgb'] for r in records}),base_count=len(BASES),base_names=BASES,
        font_path=str(font_path),font_sha256=sha(font_path),font_size=14,pillow=pillow_version,python=platform.python_version(),
        builder_sha256=sha(__file__),spec_sha256=sha('docs/r9_duplicate_owner_experiment_spec.md'),
        observer_sha256=sha('src/image_to_editable_ppt/research/duplicate_owner_observations.py'),
        manifest_sha256=sha(out/'manifest.json'),expectations_sha256=sha(out/'expectations.json'),
        actual_pp_source_sha256=sha(source),combinations='36 bases x 3 scales x 2 shaft shifts x 2 colors x 2 AA x (2 orders x 2 scores); chain uses all 6 orders; plus 8 PP actual records')
    save(out/'lock.json',lock)
    print(json.dumps(lock,ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True)
    build(parser.parse_args())
