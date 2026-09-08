"""Freeze RGB-only integration inputs and source files; assess saved PPT XML."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import zipfile
from xml.etree import ElementTree as ET
from PIL import Image
import numpy as np
from r10_owner_region_p2_audit import sha


def prepare(root,pilot,out):
    out.mkdir(parents=True,exist_ok=False);(out/'source-snapshot').mkdir();(out/'rgb').mkdir();seen={};records=[]
    lock=json.loads((pilot/'preregister.json').read_text())
    receipts={}
    for name in ['native-renders','derived-renders']:
        manifest=json.loads((pilot/name/'powerpoint_render_manifest.json').read_text(encoding='utf-8-sig'))
        receipts.update({r['id']:r for r in manifest['records']})
    for r in lock['records']:
        receipt=receipts[r['id']];path=Path(receipt['render_path']);digest=sha(path);assert digest==receipt['render_sha256']
        if digest in seen:seen[digest]['aliases'].append(r['id']);continue
        with Image.open(path) as im:
            assert 'transparency' not in im.info
            original_mode=im.mode;rgb=im.convert('RGB');pixels=np.array(rgb);converted=out/'rgb'/f"{r['id']}.png";rgb.save(converted)
        assert np.array_equal(pixels,np.array(Image.open(converted)))
        item=dict(id=r['id'],input=str(converted.resolve()),sha256=sha(converted),original_path=str(path),original_sha256=digest,
                  original_mode=original_mode,pixel_equivalent_rgb=True,semantic=r['label'],variant=r['variant'],aliases=[])
        seen[digest]=item;records.append(item)
    files=list((root/'src').rglob('*.py'))+list((root/'tools').glob('*.py'))+list((root/'tools').glob('*.ps1'))
    files+=list((root/'docs').glob('r10*.md'))
    hashes={str(f):sha(f) for f in files}
    for f in files:
        target=out/'source-snapshot'/f.relative_to(root);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(f,target)
    result=dict(root=str(root),root_head=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip(),
                dirty_status=subprocess.check_output(['git','-C',str(root),'status','--short'],text=True),code_sha256=hashes,
                records=records,contract='convert_closed_native fixed options, RGB only; roles evaluator-only; no classifier; all exact duplicate full RGB aliases frozen.')
    (out/'lock.json').write_text(json.dumps(result,indent=2));print(len(records),sha(out/'lock.json'))


def run(out):
    lock=json.loads((out/'lock.json').read_text());root=Path(lock['root']);results=[]
    def verify():
        assert all(sha(Path(p))==v for p,v in lock['code_sha256'].items())
    verify();(out/'pptx-for-render').mkdir(exist_ok=False)
    for r in lock['records']:
        assert sha(Path(r['input']))==r['sha256'];target=out/'runs'/r['id']
        cmd=['C:/vs/ImageToEditablePPT/.venv/Scripts/python.exe',str(root/'tools/convert_closed_native.py'),'--image',r['input'],'--output',str(target.resolve())]
        process=subprocess.run(cmd,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=120)
        target.mkdir(parents=True,exist_ok=True);(target/'stdout.txt').write_text(process.stdout);(target/'stderr.txt').write_text(process.stderr)
        result=dict(**r,exit=process.returncode,command=cmd)
        if process.returncode==0:
            h=json.loads((target/'handoff.json').read_text());native=json.loads((target/'native/result.json').read_text());pptx=Path(h['pptx'])
            with zipfile.ZipFile(pptx) as z:e=ET.fromstring(z.read('ppt/slides/slide1.xml'))
            ns={'p':'http://schemas.openxmlformats.org/presentationml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main'}
            result.update(nodes=h['nodes'],labels=h['labels'],edges=h['native_edges'],pictures=len(e.findall('.//p:pic',ns)),
                          xml_shapes=len(e.findall('.//p:sp',ns)),xml_edges=len(e.findall('.//p:cxnSp',ns)),
                          texts=[v.text for v in e.findall('.//a:t',ns)],pptx_sha256=sha(pptx),native_lock_sha256=sha(target/'native/lock.json'))
            shutil.copyfile(pptx,out/'pptx-for-render'/f"{r['id']}.pptx")
        results.append(result);print(r['id'],result.get('nodes'),result.get('texts'),flush=True)
        verify()
    (out/'results.json').write_text(json.dumps(results,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','run']);p.add_argument('--out',type=Path,required=True);p.add_argument('--root',type=Path);p.add_argument('--pilot',type=Path);a=p.parse_args()
    if a.mode=='prepare':prepare(a.root,a.pilot,a.out)
    else:run(a.out)
