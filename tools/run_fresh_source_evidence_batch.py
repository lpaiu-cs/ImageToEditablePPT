"""Fresh detector plus all stages on the locked 15-RGB development manifest."""
import argparse
from pathlib import Path
import subprocess
import sys

from convert_source_evidence import write_handoff
from run_region_rgb_baseline import ROOT
from run_source_evidence_pipeline import run


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--inputs',type=Path,required=True)
    p.add_argument('--checkpoint',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--closed-nodes',action='store_true');p.add_argument('--box-centerlines',action='store_true');p.add_argument('--box-terminals',action='store_true')
    a=p.parse_args()
    if a.box_terminals and not a.box_centerlines:p.error('terminals require B evidence')
    output=a.output.resolve();output.mkdir(parents=True,exist_ok=False);detector=output/'detector'
    subprocess.run([sys.executable,str(ROOT/'tools/run_fresh_rgb_detector.py'),'--inputs',str(a.inputs.resolve()),
        '--checkpoint',str(a.checkpoint.resolve()),'--out',str(detector)],cwd=ROOT,check=True)
    handoff=write_handoff(detector,output/'handoff.json')
    run(handoff,output/'native',closed_nodes=a.closed_nodes,box_centerlines=a.box_centerlines,box_terminals=a.box_terminals)
