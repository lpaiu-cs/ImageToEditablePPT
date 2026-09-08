"""Prepare twelve role-locked photo caption PPTs; no runtime/classifier execution."""
import argparse
import json
from pathlib import Path
import shutil
from PIL import Image,ImageOps
from pptx.util import Emu
from r10_classifier_pilot import deck,rect,label,BOX,EMU
from r10_owner_region_p2_audit import sha


def build(out):
    out.mkdir(parents=True,exist_ok=False);(out/'pptx').mkdir();(out/'assets').mkdir()
    source=Path('C:/vs/ImageToEditablePPT/.venv/Lib/site-packages/sklearn/datasets/images')
    shutil.copyfile(source/'README.txt',out/'assets/README-source.txt')
    specs=[]
    for asset in ['china','flower']:
        path=source/(asset+'.jpg');shutil.copyfile(path,out/'assets'/path.name)
        for tone in ['color','gray']:
            for caption in ['Input','Photo','Encoder']:
                specs.append(dict(id=f'{asset}-{tone}-{caption.lower()}',asset=asset,asset_sha256=sha(path),tone=tone,
                                  caption=caption,semantic='non_diagram_photo',asset_group=asset,target_bbox=BOX))
    lock=dict(records=specs,builder_sha256=sha(__file__),helper_sha256=sha(Path(__file__).parent/'r10_classifier_pilot.py'),
              contract='New exposed development negatives only; captions and semantic roles never passed to runtime; no training or holdout.')
    (out/'preregister.json').write_text(json.dumps(lock,indent=2))
    receipts=[]
    for r in specs:
        im=Image.open(source/(r['asset']+'.jpg')).convert('RGB')
        if r['tone']=='gray':im=ImageOps.grayscale(im).convert('RGB')
        image=out/'assets'/(r['id']+'.png');im.save(image)
        p,s=deck();rect(s,BOX,name='photo_frame');label(s,r['caption'],200,108,300)
        s.shapes.add_picture(str(image),Emu(182*EMU),Emu(140*EMU),Emu(376*EMU),Emu(178*EMU))
        path=out/'pptx'/(r['id']+'.pptx');p.save(path)
        receipts.append(dict(id=r['id'],pptx=str(path.resolve()),pptx_sha256=sha(path),asset_png_sha256=sha(image)))
    (out/'pptx-receipts.json').write_text(json.dumps(receipts,indent=2));print('prepared',len(receipts),'lock',sha(out/'preregister.json'))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();build(a.out)
