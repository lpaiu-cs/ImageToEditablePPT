"""Four preregistered source-PPT fanout controls; no runtime inference."""
import argparse
import json
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
from pptx.util import Emu, Pt
from pptx.enum.shapes import MSO_CONNECTOR
from pptx.dml.color import RGBColor
from pptx.oxml.xmlchemy import OxmlElement
from r10_classifier_pilot import deck, rect, label, EMU
from r10_owner_region_p2_audit import sha


def build(out):
    out.mkdir(parents=True,exist_ok=False)
    (out/'pptx').mkdir()
    nodes=[dict(id='hub',label='Read',bbox=[40,195,160,255])]+[
        dict(id=f'leaf{i}',label=text,bbox=[640,y-30,760,y+30])
        for i,(text,y) in enumerate(zip(['Build','Check','Write'],[95,225,355]))]
    records=[]
    for mode in ['straight','undirected','partial-arrow','bent']:
        edges=[]
        for i,y in enumerate([95,225,355]):
            points=[[160,225],[640,y]]
            if mode=='bent' and y!=225:points=[[160,225],[400,225],[400,y],[640,y]]
            edges.append(dict(source='hub',target=f'leaf{i}',points=points,
                arrow=mode not in ['undirected','partial-arrow'] or (mode=='partial-arrow' and i==0)))
        records.append(dict(id=mode,nodes=nodes,source_relations=edges,
            expected_directed_pairs=[['hub',f'leaf{i}'] for i in range(3)] if mode=='straight' else [],
            expected_branch_abstention=mode!='straight'))
    lock=dict(records=records,builder_sha256=sha(__file__),
        helper_sha256=sha(Path(__file__).with_name('r10_classifier_pilot.py')),
        contract='Four exposed causal/regression controls, one template lineage, not independent generalization or calibration/eval. Source logical relations include unsupported bent/mixed structures; empty expected pairs are conservative arm policy, not absence of source relations. RGB-only inference after root freeze. No gaps arm, photos, training or downloads.')
    (out/'preregister.json').write_text(json.dumps(lock,indent=2))
    receipts=[]
    ns={'p':'http://schemas.openxmlformats.org/presentationml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main'}
    for r in records:
        p,s=deck()
        for node in r['nodes']:
            b=node['bbox'];rect(s,b,(225,235,245),node['id'])
            label(s,node['label'],b[0]+12,b[1]+15,b[2]-b[0]-20)
        segments=0
        for i,e in enumerate(r['source_relations']):
            for j,(a,b) in enumerate(zip(e['points'],e['points'][1:])):
                c=s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT,Emu(a[0]*EMU),Emu(a[1]*EMU),Emu(b[0]*EMU),Emu(b[1]*EMU))
                c.name=f'relation{i}:{e["source"]}->{e["target"]}:segment{j}'
                c.line.color.rgb=RGBColor(0,0,0);c.line.width=Pt(2)
                if e['arrow'] and j==len(e['points'])-2:
                    end=OxmlElement('a:tailEnd');end.set('type','triangle');end.set('w','lg');end.set('len','lg')
                    c._element.spPr.get_or_add_ln().append(end)
                segments+=1
        path=out/'pptx'/f'{r["id"]}.pptx';p.save(path)
        with zipfile.ZipFile(path) as z:xml=ET.fromstring(z.read('ppt/slides/slide1.xml'))
        assert not xml.findall('.//p:pic',ns)
        assert len(xml.findall('.//p:cxnSp',ns))==segments
        assert len(xml.findall('.//a:tailEnd',ns))==sum(e['arrow'] for e in r['source_relations'])
        assert len(xml.findall('.//p:sp',ns))==8
        receipts.append(dict(id=r['id'],pptx=str(path.resolve()),pptx_sha256=sha(path),
            source_relations=r['source_relations'],xml_connector_segments=segments,
            objects=[dict(id=v.get('id'),name=v.get('name')) for v in xml.findall('.//p:cNvPr',ns)]))
    (out/'source-receipts.json').write_text(json.dumps(receipts,indent=2))
    print('4 source controls; preregister SHA',sha(out/'preregister.json'))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    build(p.parse_args().out)
