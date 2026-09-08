"""Hash-bound replay of the consumed complex cohort, preserving frozen v0.2."""
import argparse
from pathlib import Path
from validate_complex_regions import freeze,run,review

def main():
    p=argparse.ArgumentParser(); p.add_argument('mode',choices=['freeze','run','review'])
    p.add_argument('--revision',type=int,default=1)
    args=p.parse_args(); root=Path(__file__).resolve().parents[1]
    manifest=root/f'benchmarks/region_complex_r5_inputs_v{args.revision}.json'
    base=root/('artifacts/region-complex-r5/final' if args.revision==1 else f'artifacts/region-complex-r5/final-v{args.revision}')
    if args.mode=='freeze': freeze(root,manifest)
    elif args.mode=='run': run(root,manifest,base/'run')
    else: review(root,manifest,base/'run',base/'renders',base/'review',native_label='Native PowerPoint R5')

if __name__=='__main__': main()
