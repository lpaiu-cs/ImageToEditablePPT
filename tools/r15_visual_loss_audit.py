"""Bind manually observed loss counts to saved RGB and actual native COM output."""
import argparse
import json
from pathlib import Path
from collections import Counter
from PIL import Image,ImageDraw,ImageFont
from run_region_rgb_baseline import ROOT,digest,save


def run(output):
    output.mkdir(parents=True,exist_ok=False)
    ledger_path=ROOT/'docs/r15_visual_loss_ledger.json'
    ledger=json.loads(ledger_path.read_text(encoding='utf-8'))
    native=ROOT/'artifacts/region-image-only-r14/cli-v4/original/native'
    result=json.loads((native/'result.json').read_text())
    lock=json.loads((native/'lock.json').read_text())
    source=Path(lock['source_path']);render=native/'renders/result.png'
    baseline=json.loads((ROOT/'artifacts/region-image-only-r14/cli-v4-review/audit.json').read_text())
    receipt=next(r for r in baseline['rows'] if r['id']=='original')
    assert digest(source)==receipt['source_sha256']==lock['source_sha256']
    assert digest(render)==receipt['render_sha256']
    assert digest(native/'result.pptx')==receipt['pptx_sha256']==result['pptx_sha256']
    nodes=ledger['nodes'];by_id={n['id']:n for n in nodes}
    assert len(by_id)==len(nodes)
    assert {n['output'] for n in nodes if n['output']}=={s['id'] for s in result['emitted_scene']['shapes']}
    observed={(e['source_owner_id'],e['target_owner_id']) for e in result['emitted_scene']['connectors']}
    for edge in ledger['connections']:
        pair=(by_id[edge['from']]['output'],by_id[edge['to']]['output'])
        assert (pair in observed)==edge['retained'],edge
    summary=dict(nodes_total=len(nodes),nodes_retained=sum(bool(n['output']) for n in nodes),
        text=Counter(n['text'] for n in nodes),loss_stage=Counter(n['stage'] for n in nodes),
        connections_reviewed=len(ledger['connections']),connections_retained=sum(e['retained'] for e in ledger['connections']),
        scope=ledger['scope'],connections_scope=ledger['connections_scope'],
        ledger_sha256=digest(ledger_path),runner_sha256=digest(Path(__file__)),artifact_receipt=receipt)
    save(output/'summary.json',summary)
    width=1400;src=Image.open(source).convert('RGB');height=round(width*src.height/src.width)
    board=Image.new('RGB',(2*width+30,height+100),'white');draw=ImageDraw.Draw(board)
    font=ImageFont.truetype('C:/Windows/Fonts/malgun.ttf',23)
    draw.text((10,8),'원본: 빨강=노드 없음 / 주황=설명 누락 / 회색=정책상 빈 카드 / 초록=내용 유지',font=font,fill='black')
    draw.text((width+40,8),'실제 PowerPoint 결과: 핵심 노드 8/17, 확인 연결 4/20',font=font,fill='black')
    board.paste(src.resize((width,height)),(0,80))
    board.paste(Image.open(render).convert('RGB').resize((width,height)),(width+30,80))
    colors={'complete':'#16803c','partial':'#bb6400','policy_blank':'#626b78','absent':'#d02030'}
    for node in nodes:
        x0,y0,x1,y1=node['box'];sx=width/ledger['source_display_size'][0];sy=height/ledger['source_display_size'][1]
        box=(round(x0*sx),round(y0*sy)+80,round(x1*sx),round(y1*sy)+80);color=colors[node['text']]
        draw.rectangle(box,outline=color,width=3)
        tx,ty=box[0],max(45,box[1]-28)
        draw.rectangle((tx,ty,tx+53,ty+27),fill=color);draw.text((tx+2,ty),node['id'],font=font,fill='white')
    board.save(output/'original-loss-map.png')
    rejected=result['emission']['rejected_connectors']
    tiles=[]
    for edge in result['proposed_scene']['connectors']:
        if edge['id'] not in rejected:continue
        tile=Image.new('RGB',(1000,650),'white');td=ImageDraw.Draw(tile)
        tile.paste(src.resize((1000,round(1000*src.height/src.width))),(0,85))
        td.text((5,5),edge['id']+' '+edge['source_owner_id']+' -> '+edge['target_owner_id'],font=font,fill='black')
        td.text((5,35),'거부된 추적 후보 (정답 경로 아님)',font=font,fill='black')
        pts=[(p['x']*1000/src.width,p['y']*1000/src.width+85) for p in edge['path_points']]
        td.line(pts,fill='#b000d0',width=5)
        for label,(x,y) in [('S',pts[0]),('E',pts[-1])]:
            td.ellipse((x-7,y-7,x+7,y+7),fill='#b000d0');td.text((x+9,y-16),label,font=font,fill='#b000d0')
        tiles.append(tile)
    paths=Image.new('RGB',(1000*len(tiles),650),'white')
    for i,tile in enumerate(tiles):paths.paste(tile,(i*1000,0))
    paths.save(output/'rejected-paths.png')
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    run(p.parse_args().output)
