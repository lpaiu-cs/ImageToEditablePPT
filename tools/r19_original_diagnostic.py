"""Posthoc manual ledger diagnostic on saved RGB-only predictions, never a converter."""
import argparse
from r19_outcome_audit import *


def run(output):
    output.mkdir(parents=True,exist_ok=False);base=ROOT/'artifacts/region-image-only-r19'
    original=base/'original-v1';result=json.loads((original/'result.json').read_text());verify(json.loads((original/'external-guard.json').read_text()))
    source=ROOT/'artifacts/region-image-only-r10/complex-inputs/original-rgb.png';assert digest(source)==result['input_sha256']
    receipt=json.loads((original/'renders/powerpoint_render_manifest.json').read_text(encoding='utf-8-sig'))['records'][0]
    assert digest(original/'result.pptx')==result['pptx_sha256']==receipt['pptx_sha256']
    assert digest(receipt['render_path'])==receipt['render_sha256']
    single=json.loads((base/'rgb-only-v1/result.json').read_text());verify(json.loads((base/'rgb-only-v1/external-guard.json').read_text()))
    evaluation=json.loads((base/'eval-v1/results.json').read_text());row=next(r for r in evaluation['arms']['instance']['rows'] if r['id']=='r19-white_card_color_bg-eval-000')
    assert single['objects']==row['objects'] and single['all_candidates']==row['all_candidates']
    ledger_path=ROOT/'docs/r15_visual_loss_ledger.json';ledger=json.loads(ledger_path.read_text())
    with Image.open(source) as im:image=im.convert('RGB')
    expected=[dict(id=n['id'],name=n['name'],kind=6 if n.get('kind')=='cylinder' else 2,
        bbox=[v*image.size[i%2]/ledger['source_display_size'][i%2] for i,v in enumerate(n['box'])]) for n in ledger['nodes']]
    rows=[];sheet=Image.new('RGB',(4*320,5*210),'white');draw=ImageDraw.Draw(sheet)
    for i,g in enumerate(expected):
        overlaps=[dict(o,iou=_iou(o['bbox'],g['bbox'])) for o in result['all_candidates'] if _iou(o['bbox'],g['bbox'])>=.5]
        best=max(overlaps,key=lambda o:o['iou'],default=None)
        correct=max([o for o in overlaps if o['kind']==g['kind']],key=lambda o:o['confidence'],default=None)
        status='candidate_absent' if not overlaps else 'correct_kind_absent' if correct is None else 'score_rejected' if correct['confidence']<result['threshold'] else 'kept_correct'
        rows.append(dict(**g,status=status,best_geometry=best,best_correct_kind=correct))
        x=i%4*320;y=i//4*210;draw.text((x+4,y+4),g['id']+' '+g['name'],fill='black');draw.text((x+4,y+20),status,fill='black')
        if best:
            crop=image.crop(tuple(round(v) for v in best['bbox']));crop.thumbnail((310,155));sheet.paste(crop,(x+5,y+52))
            draw.text((x+4,y+36),f'predicted ROI k{best["kind"]} score{best["confidence"]:.3f} IoU{best["iou"]:.2f}',fill='black')
    sheet.save(output/'matched-predicted-rois.png')
    board=Image.new('RGB',(1380,406),'white');d=ImageDraw.Draw(board);board.paste(image.resize((690,376)),(0,30))
    with Image.open(receipt['render_path']) as im:board.paste(im.convert('RGB').resize((690,376)),(690,30))
    d.text((4,4),'Exposed original RGB',fill='black');d.text((694,4),'R19 actual native PowerPoint: 9 shapes',fill='black');board.save(output/'original-comparison.png')
    counts={key:dict(geometry=geometry(result[key],expected),kind=object_counts(result[key],expected)) for key in ('all_candidates','objects')}
    save(output/'diagnostic.json',dict(rows=rows,counts=counts,local_status_counts=Counter(r['status'] for r in rows),rgb_only_equal=True,
        prediction_sha256=digest(original/'result.json'),ledger_sha256=digest(ledger_path),code_sha256=digest(__file__),
        scope='Exposed manual 17-node ledger, default visually rounded nodes and two cylinders; not independent GT. Per-node support is local; counts use global matching. Saved candidates are post-NMS: NMS losses cannot be diagnosed. Crops use predicted boxes, not GT boxes.'))
    print(json.dumps(dict(counts=counts,local_status_counts=Counter(r['status'] for r in rows)),indent=2))


if __name__=='__main__':
    # Explicit underscore import: star imports intentionally omit private names.
    from image_to_editable_ppt.research.closed_rect_proposals import _iou
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);run(p.parse_args().output)
