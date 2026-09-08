"""Reuse native-PPT staging and inspect R18's larger source/render comparison."""
import argparse
import json
from pathlib import Path
from PIL import Image,ImageDraw
from r16_primitive_visual_audit import run as stage_pptx
from r18_candidate_validity import digest,save,geometry,summary


def review(manifest,evaluation,output):
    records={r['id']:r for r in json.loads(manifest.read_text())['records'] if r['split']=='eval'}
    results=json.loads((evaluation/'results.json').read_text());assert results['manifest_sha256']==digest(manifest)
    inputs=json.loads((output/'inputs.json').read_text());assert inputs['results_sha256']==digest(evaluation/'results.json')
    receipts=json.loads((output/'renders/powerpoint_render_manifest.json').read_text(encoding='utf-8-sig'))['records']
    receipts={r['id']:r for r in receipts};assert len(receipts)==len(inputs['rows'])==64
    for row in inputs['rows']:
        receipt=receipts[row['id']];assert row['pptx_sha256']==receipt['pptx_sha256']==digest(receipt['pptx_path'])
        assert digest(receipt['render_path'])==receipt['render_sha256']
    boards=[]
    for identity,record in records.items():
        board=Image.new('RGB',(1600,240),'white');draw=ImageDraw.Draw(board)
        with Image.open(record['image']) as im:board.paste(im.convert('RGB').resize((320,200)),(0,40))
        draw.text((4,4),identity+' source',fill='black')
        for col,(arm,result) in enumerate(results['arms'].items(),1):
            row=next(r for r in result['rows'] if r['id']==identity);receipt=receipts[f'{arm}--{identity}']
            with Image.open(receipt['render_path']) as im:
                assert im.size==(640,400);board.paste(im.convert('RGB').resize((320,200)),(col*320,40))
            draw.text((col*320+4,4),arm,fill='black');draw.text((col*320+4,19),f'TP {row["tp"]} FP {row["fp"]} FN {row["fn"]}',fill='black')
        path=output/(identity+'.png');assert not path.exists();board.save(path);boards.append(dict(id=identity,path=str(path.resolve()),sha256=digest(path)))
    by_role={};by_family={}
    for arm,result in results['arms'].items():
        by_role[arm]={};by_family[arm]={f:summary([r['coverage'] for r in result['rows'] if r['family']==f]) for f in sorted({r['family'] for r in result['rows']})}
        for role in ('node','container'):
            expected_total=0;candidate_tp=0;validity_tp=0;final_tp=0
            for row in result['rows']:
                expected=[g for g in records[row['id']]['objects'] if (g['id']=='container')==(role=='container')];expected_total+=len(expected)
                candidate_tp+=geometry(row['all_candidates'],expected)['tp']
                kept=[o for o in row['all_candidates'] if arm.endswith('_raw') or o['validity']>=result['calibration']['threshold']]
                validity_tp+=geometry(kept,expected)['tp'];final_tp+=geometry(row['objects'],expected)['tp']
            by_role[arm][role]=dict(expected=expected_total,candidate_tp=candidate_tp,validity_geometry_tp=validity_tp,final_geometry_tp=final_tp)
    save(output/'audit.json',dict(boards=boards,checked_pptx=64,native_shape_count=sum(r['shape_count'] for r in inputs['rows']),
        by_role=by_role,candidate_by_family=by_family,results_sha256=digest(evaluation/'results.json'),
        receipt_sha256=digest(output/'renders/powerpoint_render_manifest.json'),code_sha256=digest(__file__)))
    print(json.dumps(dict(by_role=by_role,candidate_by_family=by_family),indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','review'])
    for name in ('manifest','evaluation','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    if a.mode=='prepare':stage_pptx(a.manifest,a.evaluation,a.output,'prepare')
    else:review(a.manifest,a.evaluation,a.output)
