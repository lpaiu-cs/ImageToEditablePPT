"""Read only explicitly train-labelled PPT/RGB pairs; never open val/test payloads."""
import argparse
import collections
import hashlib
import json
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
from PIL import Image


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def run(root,out):
    out.mkdir(parents=True,exist_ok=False)
    ns={'p':'http://schemas.openxmlformats.org/presentationml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main'}
    datasets=[]
    for name in ['ds-v13-pil','ds-v13-soffice','ds-v13b-pil','ds-v13b-soffice','ds-v13-mixed','ds-v13-extended']:
        base=root/'workbench-ml'/name;mp=base/'dataset_manifest.json';m=json.loads(mp.read_text());records=[]
        for s in m['samples']:
            if s['split']!='train' or not s.get('pptx') or m['generator']['renderer']=='mixed':continue
            paths={k:(base/s[k]).resolve() for k in ['pptx','image','annotation']}
            assert all(p.parent.name=='train' for p in paths.values())
            a=json.loads(paths['annotation'].read_text());nodes=a['primitive_scene']['nodes'];containers=a['primitive_scene']['containers']
            with zipfile.ZipFile(paths['pptx']) as z:
                slides=[n for n in z.namelist() if n.startswith('ppt/slides/slide') and n.endswith('.xml')]
                elems=[ET.fromstring(z.read(n)) for n in slides]
                pp=ET.fromstring(z.read('ppt/presentation.xml'));sz=pp.find('p:sldSz',ns)
                shapes=[v for e in elems for v in e.findall('.//p:sp',ns)]
                names={v.find('p:nvSpPr/p:cNvPr',ns).get('name'):v for v in shapes}
                presets=collections.Counter(v.get('prst') for e in elems for v in e.findall('.//a:prstGeom',ns))
                counts={tag:sum(len(e.findall('.//p:'+tag,ns)) for e in elems) for tag in ['sp','pic','cxnSp','graphicFrame','grpSp']}
                blips=sum(len(e.findall('.//a:blip',ns)) for e in elems)
                media=[n for n in z.namelist() if n.startswith('ppt/media/')]
            with Image.open(paths['image']) as im:size=list(im.size)
            records.append(dict(id=s['id'],paths={k:str(v) for k,v in paths.items()},sha256={k:sha(v) for k,v in paths.items()},
                                image_size=size,slide_emu=dict(sz.attrib),slides=len(slides),counts=counts,presets=dict(presets),blips=blips,media_count=len(media),
                                annotation_keys=list(a),annotation_metadata=a.get('metadata'),node_count=len(nodes),container_count=len(containers),
                                node_names_matched=sum(n['id'] in names for n in nodes),container_names_matched=sum(n['id'] in names for n in containers)))
        summary=dict(name=name,manifest_path=str(mp),manifest_sha256=sha(mp),generator=m['generator'],split_counts=m['split_counts'],
                     audited_train_pairs=len(records),total_nodes=sum(r['node_count'] for r in records),
                     total_containers=sum(r['container_count'] for r in records),
                     xml_counts={k:sum(r['counts'][k] for r in records) for k in ['sp','pic','cxnSp','graphicFrame','grpSp']},
                     blips=sum(r['blips'] for r in records),media_count=sum(r['media_count'] for r in records),
                     node_name_matches=sum(r['node_names_matched'] for r in records),container_name_matches=sum(r['container_names_matched'] for r in records))
        datasets.append(dict(summary=summary,records=records));print(json.dumps(summary))
    result=dict(policy='Manifest metadata only for val/test; payload reads exclusively original soffice train. Mixed aliases not double counted.',datasets=datasets)
    (out/'results.json').write_text(json.dumps(result,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.root,a.out)
