"""Build, target-install and smoke-test the actual wheel, retaining bounded evidence."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from image_to_editable_ppt.research.region_first import digest


def main():
    p=argparse.ArgumentParser(); p.add_argument('--output-dir',required=True); args=p.parse_args()
    root=Path(__file__).resolve().parents[1]; out=root/args.output_dir; out.mkdir(parents=True,exist_ok=False)
    records=[]
    def run(command):
        result=subprocess.run(command,cwd=root,text=True,capture_output=True,encoding='utf-8',errors='replace',timeout=180)
        records.append(dict(command=command,returncode=result.returncode,stdout=result.stdout,stderr=result.stderr))
        if result.returncode: raise RuntimeError(result.stdout+result.stderr)
        return result
    run([sys.executable,'-m','pip','wheel','.', '--no-deps','--no-build-isolation','-w',str(out/'dist')])
    wheel=next((out/'dist').glob('*.whl')); target=out/'installed'
    run([sys.executable,'-m','pip','install','--no-deps','--target',str(target),str(wheel)])
    output=out/'smoke.pptx'
    source=root/'artifacts/region-native-production/synthetic-v3/chain-1.5.png'
    script="\n".join([
        'import sys,json; from pathlib import Path',
        f'target=Path({str(target)!r}).resolve(); sys.path.insert(0,str(target))',
        'import image_to_editable_ppt.region.convert as runtime',
        'assert Path(runtime.__file__).is_relative_to(target)',
        'from image_to_editable_ppt.ml.convert_to_pptx import main',
        f'assert main({[str(source),"-o",str(output),"--region","0","0","1","1","--no-ocr"]!r})==0',
        "assert 'torch' not in sys.modules",
        f'r=json.loads(Path({str(output.with_suffix(".region.json"))!r}).read_text())',
        "assert r['counts']['nodes']==3 and r['counts']['connectors']==2",
        "print('verified installed wheel without loading torch:',runtime.__file__)",
    ])
    run([sys.executable,'-I','-c',script])
    tests=run([sys.executable,'-m','pytest','-q'])
    runtime_hashes={str(p.relative_to(root)):digest(p) for p in (root/'src/image_to_editable_ppt/region').glob('*.py')}
    for path,sha in runtime_hashes.items(): assert digest(target/Path(path).relative_to('src'))==sha
    evidence=dict(git_commit=run(['git','rev-parse','HEAD']).stdout.strip(),
        wheel_path=str(wheel.relative_to(root)),wheel_sha256=digest(wheel),runtime_sha256=runtime_hashes,
        installed_runtime_matches_source=True,output_sha256=digest(output),report_sha256=digest(output.with_suffix('.region.json')),
        commands=records,verifier_sha256=digest(Path(__file__)))
    (out/'verification.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    print(tests.stdout.splitlines()[-1]); print('wheel',digest(wheel))


if __name__=='__main__': main()
