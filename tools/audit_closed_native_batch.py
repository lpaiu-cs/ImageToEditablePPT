"""Bind image-only native PPT, actual COM renders and source locks; no GT input."""
import argparse
import json
from pathlib import Path
import zipfile
from xml.etree import ElementTree as ET
from PIL import Image,ImageDraw,ImageFont
from run_region_rgb_baseline import digest,save


def audit(root,output):
    output.mkdir(parents=True,exist_ok=False)
    rows=[];font=ImageFont.truetype('C:/Windows/Fonts/malgun.ttf',22)
    directories=sorted(p.parent for p in root.rglob('result.json') if p.with_name('lock.json').is_file())
    if not directories:raise ValueError('No bound native results to audit')
    for directory in directories:
        identity=directory.parent.name if directory.name=='native' else directory.name
        result=json.loads((directory/'result.json').read_text(encoding='utf-8'))
        lock=json.loads((directory/'lock.json').read_text(encoding='utf-8'))
        pptx=directory/'result.pptx';source=Path(lock['source_path'])
        assert digest(pptx)==result['pptx_sha256']
        assert digest(source)==result['source_sha256']==lock['source_sha256']
        with zipfile.ZipFile(pptx) as archive:
            xml=ET.fromstring(archive.read('ppt/slides/slide1.xml'))
            media=[name for name in archive.namelist() if name.startswith('ppt/media/')]
        ns={'p':'http://schemas.openxmlformats.org/presentationml/2006/main',
            'a':'http://schemas.openxmlformats.org/drawingml/2006/main'}
        nodes=xml.findall('.//p:sp',ns);edges=xml.findall('.//p:cxnSp',ns)
        assert not xml.findall('.//p:pic',ns) and not media
        expected={s['id']:s for s in result['emitted_scene']['shapes']}
        assert len(nodes)==len(expected)
        native_ids={}
        for shape in nodes:
            nonvisual=shape.find('p:nvSpPr/p:cNvPr',ns);key=nonvisual.attrib['name']
            assert key in expected
            native_ids[key]=nonvisual.attrib['id']
            paragraphs=shape.findall('p:txBody/a:p',ns)
            text='\n'.join(''.join(t.text or '' for t in p.findall('.//a:t',ns)) for p in paragraphs)
            assert text==(expected[key]['label'] or '')
            xfrm=shape.find('p:spPr/a:xfrm',ns);box=expected[key]['bbox']
            off=xfrm.find('a:off',ns);ext=xfrm.find('a:ext',ns)
            measured=[int(off.get('x')),int(off.get('y')),int(ext.get('cx')),int(ext.get('cy'))]
            target=[box['x0']*9525,box['y0']*9525,(box['x1']-box['x0'])*9525,(box['y1']-box['y0'])*9525]
            assert all(abs(a-b)<=1 for a,b in zip(measured,target)),(key,measured,target)
        expected_edges={e['id']:e for e in result['emitted_scene']['connectors']}
        assert len(edges)==len(expected_edges)
        for edge in edges:
            key=edge.find('p:nvCxnSpPr/p:cNvPr',ns).get('name')
            semantic=expected_edges[key]
            start=edge.find('p:nvCxnSpPr/p:cNvCxnSpPr/a:stCxn',ns)
            end=edge.find('p:nvCxnSpPr/p:cNvCxnSpPr/a:endCxn',ns)
            assert start is not None and end is not None
            assert start.get('id')==native_ids[semantic['source_owner_id']]
            assert end.get('id')==native_ids[semantic['target_owner_id']]
        manifest=directory/'renders/powerpoint_render_manifest.json'
        rendered=json.loads(manifest.read_text(encoding='utf-8-sig'))
        entries=rendered.get('records',rendered.get('renders',[])) if isinstance(rendered,dict) else rendered
        assert len(entries)==1,rendered
        entry=entries[0];assert entry['pptx_sha256']==digest(pptx)
        rendered_path=Path(entry['render_path'])
        assert digest(rendered_path)==entry['render_sha256']
        width=900
        with Image.open(source) as im:source_im=im.convert('RGB')
        with Image.open(rendered_path) as im:native_im=im.convert('RGB')
        height=round(width*source_im.height/source_im.width)
        board=Image.new('RGB',(width*2+30,height+60),'white');draw=ImageDraw.Draw(board)
        draw.text((10,10),f'{identity} 원본 RGB',font=font,fill='black')
        draw.text((width+20,10),'이미지 단독 추론 → native PPT',font=font,fill='black')
        board.paste(source_im.resize((width,height)),(0,50));board.paste(native_im.resize((width,height)),(width+30,50))
        comparison=output/(identity+'.png')
        if comparison.exists():raise ValueError('Duplicate audit case identity')
        board.save(comparison)
        rows.append(dict(id=identity,nodes=len(nodes),labels=sum(bool(s['label']) for s in expected.values()),
            native_edges=len(edges),pictures=0,source_sha256=digest(source),pptx_sha256=digest(pptx),
            result_sha256=digest(directory/'result.json'),lock_sha256=digest(directory/'lock.json'),
            render_manifest_sha256=digest(manifest),render_sha256=digest(rendered_path),
            pptx=str(pptx.resolve()),comparison=str(comparison.resolve())))
    save(output/'audit.json',dict(rows=rows,runner_sha256=digest(Path(__file__)),
        scope='Native editability and artifact binding checks only. Counts are not correctness metrics. No GT input.'))
    print(json.dumps(rows,ensure_ascii=False,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();audit(a.run,a.output)
