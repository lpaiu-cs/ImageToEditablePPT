"""Post-evaluation diagnosis only: no training, selection or new output thresholds."""
import argparse
import json
from pathlib import Path
import numpy as np
from r16_primitive_pretraining import load_model, infer_probabilities, load_sample, digest, save


def run(manifest,trained,evaluation,output):
    output.mkdir(parents=True,exist_ok=False)
    records=json.loads(manifest.read_text())['records'];results=json.loads((evaluation/'results.json').read_text())
    lock=json.loads((trained/'lock.json').read_text())
    assert digest(manifest)==results['manifest_sha256']==lock['manifest_sha256']
    assert all(digest(p)==sha for p,sha in {**lock['code_sha256'],**lock['input_sha256']}.items())
    report={}
    for arm,result in results['arms'].items():
        checkpoint=trained/(arm+'.pt');assert digest(checkpoint)==result['checkpoint_sha256']
        model=load_model(checkpoint);groups={}
        for stage,split in [('primitive','train'),('scene','train'),('scene','eval')]:
            confusion=np.zeros((7,7),np.int64)
            for record in records:
                if (record['stage'],record['split'])!=(stage,split):continue
                prob,_=infer_probabilities(model,record['image']);target=load_sample(record)[1].numpy();valid=target!=255
                confusion+=np.bincount((target[valid]*7+prob.argmax(0)[valid]).ravel(),minlength=49).reshape(7,7)
            den=confusion.sum(0)+confusion.sum(1)-confusion.diagonal()
            iou=np.divide(confusion.diagonal(),den,out=np.zeros(7),where=den>0)
            foreground=confusion[1:,1:].sum();gt_foreground=confusion[1:].sum()
            groups[f'{stage}/{split}']=dict(confusion=confusion.tolist(),
                foreground_occupancy_iou=float(foreground/max(1,confusion.sum()-confusion[0,0])),
                foreground_recall=float(foreground/max(1,gt_foreground)),
                foreground_kind_accuracy=float(confusion.diagonal()[1:].sum()/max(1,gt_foreground)),
                per_kind_iou=iou[1:].tolist(),macro_kind_iou=float(iou[1:].mean()))
        report[arm]=groups
    isolated=json.loads((evaluation.parent/'primitive-rgb-only-v1/result.json').read_text())
    expected=next(r for r in results['arms']['pretrain80_scene80']['rows'] if r['id']=='scene-eval-000')
    assert isolated['objects']==expected['objects'] and isolated['source_sha256']==expected['source_sha256']
    save(output/'diagnosis.json',dict(arms=report,rgb_only_prediction_equal=True,
        source_results_sha256=digest(evaluation/'results.json'),code_sha256=digest(__file__),
        scope='Post-result argmax occupancy versus class diagnosis; not an alternative production result.'))
    print(json.dumps({a:{g:{k:v for k,v in r.items() if k not in ('confusion','per_kind_iou')} for g,r in groups.items()} for a,groups in report.items()},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('manifest','trained','evaluation','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();run(a.manifest,a.trained,a.evaluation,a.output)
