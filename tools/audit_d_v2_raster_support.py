"""Offline diagnostic of final fixture pixels; no observer invocation or relabeling."""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image
from run_region_rgb_baseline import ROOT, digest, save


def main(args):
    manifest=args.fixtures/'manifest.json'
    rows=json.loads(manifest.read_text())
    unique={r['geometry_group']:r for r in rows if r['population']=='v2_new'}
    records=[]
    for key,row in unique.items():
        if not (row['base'].startswith(('bright','punct','speck')) or row['base'].startswith('bbox_shift')):
            continue
        suffix=key[len('v2-'+row['base']):]
        reference=unique['v2-row_clean'+suffix]
        for r in (reference,row):
            assert digest(r['rgb'])==r['rgb_sha256']
        actual=np.array(Image.open(row['rgb']).convert('RGB'),dtype=float)
        control=np.array(Image.open(reference['rgb']).convert('RGB'),dtype=float)
        assert actual.shape==control.shape
        delta=(control-actual)@np.array([.2126,.7152,.0722])
        changed=np.any(actual!=control,axis=2)
        owners=json.loads(Path(row['owners']).read_text())
        tight=next(o['bbox_xyxy'] for o in owners if o['id']=='tight')
        yy,xx=np.indices(delta.shape);xx=xx+.5;yy=yy+.5
        outside=~((xx>=tight[0])&(xx<tight[2])&(yy>=tight[1])&(yy<tight[3]))
        lost=(delta>0)&outside
        # Contrast is measured from the actual white fixture background, not from a label.
        contrast=255-actual@np.array([.2126,.7152,.0722])
        records.append(dict(id=key,base=row['base'],source_sha256=row['rgb_sha256'],
            reference_sha256=reference['rgb_sha256'],identical_to_clean=not bool(changed.any()),
            changed_pixels=int(changed.sum()),added_dark_pixels_outside_tight=int(lost.sum()),
            max_added_darkening_outside_tight=float(delta[lost].max()) if lost.any() else 0.,
            actual_max_contrast_at_added_pixels=float(contrast[lost].max()) if lost.any() else 0.,
            added_pixels_reaching_weak12=int((lost&(contrast>=12)).sum()),
            note='pixel differences do not prove human-readable semantic content'))
    args.output.mkdir(parents=True,exist_ok=False)
    save(args.output/'audit.json',dict(purpose='post-lock fixture raster diagnostic, no expectations changed',
        manifest_sha256=digest(manifest),script_sha256=digest(Path(__file__)),records=records))
    print(json.dumps(records))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--fixtures',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);main(p.parse_args())
