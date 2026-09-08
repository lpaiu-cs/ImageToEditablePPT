"""Snapshot content gate audit; synthetic word observations and real OCR separated."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
from PIL import Image
from r10_owner_region_p2_audit import snapshot, sha


def run(source, out, geometry, owners, real_ocr):
    out.mkdir(parents=True, exist_ok=False)
    p, ps = snapshot(source/'closed_rect_proposals.py', out, 'proposal_snapshot')
    m, ms = snapshot(source/'closed_owner_regions.py', out, 'owner_snapshot')
    g, gs = snapshot(source/'closed_content_gate.py', out, 'gate_snapshot')
    rows=[]
    for fixtures in [geometry, owners]:
        lock=json.loads((fixtures/'lock.json').read_text())
        assert sha(fixtures/'manifest.json')==lock['manifest_sha256']
        for case in json.loads((fixtures/'manifest.json').read_text()):
            path=fixtures/case['rgb']; assert sha(path)==case['sha256']
            rgb=np.array(Image.open(path)); before=rgb.copy()
            selected,_=p.propose(rgb,inner_boundaries=True)
            regions=m.closed_regions(rgb)
            observations=[]
            for candidate in selected:
                own,excluded,fill,_=m.owner_region(rgb,candidate,regions)
                x,y,c,d=candidate['bbox']; words=[]
                for word in case.get('words',[]):
                    a,b,e,f=word['bbox']
                    if x<=a<e<=c and y<=b<f<=d and not excluded[int(b):int(np.ceil(f)),int(a):int(np.ceil(e))].any():
                        words.append(dict(text=word['text'],bbox=[a-x,b-y,e-x,f-y]))
                audit=dict(accepted=[dict(words=words)] if words else [])
                observations.append(dict(bbox=candidate['bbox'],empty_ocr=g.inspect_content(rgb,candidate,own,dict(accepted=[])),
                                         synthetic_words=[w['text'] for w in words],
                                         synthetic_ocr=g.inspect_content(rgb,candidate,own,audit)))
            assert np.array_equal(rgb,before)
            rows.append(dict(id=case['id'],suite=fixtures.name,observations=observations))
    # Pure admission contract, not source tracing or native emitter validation.
    shapes=[NS(id='label',label='A'),NS(id='blank',label=None),NS(id='isolated',label=None),NS(id='bad',label='B')]
    content={s.id:dict(eligible=s.id!='bad') for s in shapes}
    admission=[]
    for name,edges in [('isolated',[]),('label_blank',[('label','blank')]),('bad_blank',[('bad','blank')]),('blank_blank',[('blank','isolated')])]:
        scene=NS(shapes=shapes,connectors=[NS(source_owner_id=a,target_owner_id=b) for a,b in edges])
        admission.append(dict(name=name,admitted=sorted(g.admitted_ids(scene,content))))
    result=dict(proposal_sha256=ps,owner_sha256=ms,gate_sha256=gs,runner_sha256=sha(__file__),
                fixture_locks={f.name:sha(f/'lock.json') for f in [geometry,owners]},
                rows=rows,admission=admission,real_ocr=[])
    (out/'results.json').write_text(json.dumps(result,indent=2))
    if real_ocr:
        from rapidocr_onnxruntime import RapidOCR
        engine=RapidOCR()
        cases=json.loads((owners/'manifest.json').read_text())
        for key in ['two_children-s1-aa4','small_child-s1-aa4']:
            case=next(c for c in cases if c['id']==key)
            rgb=np.array(Image.open(owners/case['rgb']))
            selected,_=p.propose(rgb,inner_boundaries=True)
            parent=max(selected,key=lambda c:p._iou(c['bbox'],case['parent_bbox']))
            own,excluded,_,_=m.owner_region(rgb,parent,m.closed_regions(rgb))
            text,audit=p.observe_text(rgb,parent['bbox'],engine,excluded=excluded)
            result['real_ocr'].append(dict(id=key,text=text,audit=audit,content=g.inspect_content(rgb,parent,own,audit)))
        (out/'results.json').write_text(json.dumps(result,indent=2))
    print(json.dumps({k:v for k,v in result.items() if k not in ['rows','real_ocr']}))
    print(json.dumps(result['real_ocr']))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ['source','out','geometry','owners']:p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--real-ocr',action='store_true');a=p.parse_args()
    run(a.source,a.out,a.geometry,a.owners,a.real_ocr)
