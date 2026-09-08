"""Fixed rendered-glyph controls for the separate portrait text observation."""
import argparse
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from observe_portrait_labels import observe_portrait
from run_region_rgb_baseline import digest,save
from image_to_editable_ppt.v3.text.ocr import _load_engine


def run(output):
    output.mkdir(parents=True,exist_ok=False);records=[]
    for size in (1,2):
        for font_name in ('arial','times'):
            for label in ('Input','Encoder','Context Gate'):
                for orientation in ('clockwise','counterclockwise'):
                    patch=Image.new('RGB',(300*size,60*size),'white');draw=ImageDraw.Draw(patch)
                    font=ImageFont.truetype(f'C:/Windows/Fonts/{font_name}.ttf',24*size)
                    draw.text((150*size,30*size),label,font=font,fill='black',anchor='mm')
                    patch=patch.transpose(Image.Transpose.ROTATE_270 if orientation=='clockwise' else Image.Transpose.ROTATE_90)
                    identity=f'{font_name}-{label.replace(" ","_")}-{orientation}-{size}';path=output/(identity+'.png');patch.save(path)
                    records.append(dict(id=identity,path=str(path.resolve()),sha256=digest(path),expected_label=label,expected_orientation=orientation,role='positive'))
        for kind in ('blank','rule','cross','stacked_letters'):
            patch=Image.new('RGB',(60*size,300*size),'white');draw=ImageDraw.Draw(patch)
            if kind=='rule':draw.line((30*size,30*size,30*size,270*size),fill='black',width=3*size)
            if kind=='cross':
                draw.line((10*size,30*size,50*size,270*size),fill='black',width=3*size)
                draw.line((50*size,30*size,10*size,270*size),fill='black',width=3*size)
            if kind=='stacked_letters':
                font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',24*size)
                for i,char in enumerate('STACK'):draw.text((30*size,(60+35*i)*size),char,font=font,fill='black',anchor='mm')
            identity=f'{kind}-{size}';path=output/(identity+'.png');patch.save(path)
            records.append(dict(id=identity,path=str(path.resolve()),sha256=digest(path),expected_label=None,expected_orientation=None,role='negative_scope'))
    save(output/'manifest.json',dict(records=records,runner_sha256=digest(Path(__file__)),observer_sha256=digest(Path(__file__).with_name('observe_portrait_labels.py')),
        population='procedurally rendered glyph controls; no human/generalization claim'))
    engine=_load_engine();results=[]
    for row in records:
        rgb=np.array(Image.open(row['path']));h,w=rgb.shape[:2]
        selected,audit=observe_portrait(rgb,[0,0,w,h],np.zeros((h,w),np.uint8),engine)
        label=selected['label'] if selected else None;orientation=selected['orientation'] if selected else None
        verdict='correct' if label==row['expected_label'] and orientation==row['expected_orientation'] else ('abstain' if selected is None else 'wrong_approval')
        results.append(dict(id=row['id'],role=row['role'],label=label,orientation=orientation,verdict=verdict,audit=audit))
        print(row['id'],verdict,label,orientation,flush=True)
    save(output/'results.json',dict(manifest_sha256=digest(output/'manifest.json'),rows=results))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.output)
