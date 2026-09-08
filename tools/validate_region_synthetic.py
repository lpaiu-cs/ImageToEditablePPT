"""Fixed synthetic contract and counterexamples, not real-image generalization."""
import argparse
import json
import subprocess
import sys
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
from image_to_editable_ppt.research.region_first import digest


def cases():
    base=np.full((300,720,3),255,np.uint8)
    for x in (30,290,550): cv2.rectangle(base,(x,100),(x+140,200),(0,0,0),2)
    for x in (170,430): cv2.arrowedLine(base,(x,150),(x+120,150),(0,0,0),2,tipLength=.15)
    for scale in (.75,1,1.5):
        yield f'chain-{scale}',cv2.resize(base,None,fx=scale,fy=scale),3,2
    yield 'chain-vertical',cv2.rotate(base,cv2.ROTATE_90_CLOCKWISE),3,2
    im=np.full((400,600,3),255,np.uint8)
    cv2.rectangle(im,(30,30),(190,140),(0,0,0),2); cv2.rectangle(im,(380,260),(560,370),(0,0,0),2)
    cv2.line(im,(190,85),(470,85),(0,0,0),2); cv2.arrowedLine(im,(470,85),(470,260),(0,0,0),2,tipLength=.10)
    yield 'elbow',im,2,1
    im=np.full((260,400,3),248,np.uint8); cv2.rectangle(im,(50,50),(350,210),(0,0,0),2)
    yield 'near-white-blank-box',im,1,0
    yield 'blank',np.full((300,500,3),255,np.uint8),0,0
    im=np.full((360,500,3),255,np.uint8)
    for x,y in np.random.default_rng(9041).integers([20,20],[480,340],size=(250,2)):
        cv2.circle(im,(int(x),int(y)),2,(255,0,0),-1)
    yield 'scatter',im,0,0
    im=np.full((260,400,3),255,np.uint8); cv2.arrowedLine(im,(30,130),(370,130),(0,0,0),2,tipLength=.08)
    yield 'unowned-arrow',im,0,0
    im=np.full((400,600,3),255,np.uint8)
    for a,b in [((30,150),(170,250)),((430,30),(570,130)),((430,270),(570,370))]: cv2.rectangle(im,a,b,(0,0,0),2)
    cv2.line(im,(170,200),(300,200),(0,0,0),2); cv2.line(im,(300,80),(300,320),(0,0,0),2)
    cv2.arrowedLine(im,(300,80),(430,80),(0,0,0),2,tipLength=.15); cv2.arrowedLine(im,(300,320),(430,320),(0,0,0),2,tipLength=.15)
    yield 'ambiguous-branch',im,3,0
    im=np.full((260,400,3),255,np.uint8)
    cv2.rectangle(im,(30,70),(170,190),(0,0,0),2); cv2.rectangle(im,(220,70),(370,190),(0,0,0),2)
    yield 'unconnected-neighbors',im,2,0


def main():
    p=argparse.ArgumentParser(); p.add_argument('--output-dir',required=True); args=p.parse_args()
    out=Path(args.output_dir); out.mkdir(parents=True,exist_ok=False)
    result=dict(generator_sha256=digest(Path(__file__)),git_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),records=[])
    for name,rgb,nodes,edges in cases():
        source=out/f'{name}.png'; output=out/f'{name}.pptx'; Image.fromarray(rgb).save(source)
        command=[sys.executable,'-m','image_to_editable_ppt.ml.convert_to_pptx',str(source),'-o',str(output),'--region','0','0','1','1','--no-ocr']
        run=subprocess.run(command,capture_output=True,text=True,timeout=60)
        report=json.loads(output.with_suffix('.region.json').read_text()) if run.returncode==0 else {}
        counts=report.get('counts',{})
        result['records'].append(dict(sample=name,source_sha256=digest(source),expected_nodes=nodes,expected_connectors=edges,
            counts=counts,passed=counts.get('nodes')==nodes and counts.get('connectors')==edges and counts.get('containers')==0,
            stdout=run.stdout,stderr=run.stderr,report=report,output_sha256=digest(output) if output.exists() else None))
        (out/'results.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(name,counts,'PASS' if result['records'][-1]['passed'] else 'FAIL',flush=True)


if __name__=='__main__': main()
