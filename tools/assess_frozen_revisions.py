"""Read-only scene comparison; write a new diagnostic without altering frozen runs."""
import argparse
from pathlib import Path
import json
from run_region_rgb_baseline import ROOT, digest, save
from image_to_editable_ppt.research.revision_assessment import assess_revision


def main(args):
    refs = [ROOT/'benchmarks/region_r8a_attachment.json',ROOT/'benchmarks/r9_centerline_v2_results.json']
    before_ref = json.loads(refs[0].read_text())['arms']['t']
    after_ref = json.loads(refs[1].read_text())
    paths = [ROOT/r['artifact_root']/'results.json' for r in (before_ref,after_ref)]
    for ref,path in zip((before_ref,after_ref),paths,strict=True):
        if digest(path) != ref['files']['results.json']:
            raise ValueError('frozen source hash mismatch')
    runs = [json.loads(p.read_text(encoding='utf-8')) for p in paths]
    args.output.mkdir(parents=True,exist_ok=False)
    code = [Path(__file__),ROOT/'src/image_to_editable_ppt/research/revision_assessment.py',
            ROOT/'docs/research_error_contract_v1.md',ROOT/'tests/test_revision_assessment.py']
    save(args.output/'lock.json',dict(inputs={str(p):digest(p) for p in paths+refs},
         code={str(p.relative_to(ROOT)):digest(p) for p in code},stage='before_assessment'))
    left,right = [{r['id']:r for r in run['records']} for run in runs]
    if set(left) != set(right): raise ValueError('different population')
    rows=[]
    for key,a in left.items():
        b = right[key]
        if a['source_sha256'] != b['source_sha256']: raise ValueError('different source image')
        rows.append(dict(id=key,slot=a['slot'],source=assess_revision(a['report']['source_scene'],b['report']['source_scene']),
            emitted=assess_revision(a['report']['emitted_scene'],b['report']['emitted_scene'])))
    summary={arm:{kind:sum(len(r[arm][kind]) for r in rows) for kind in
        ('structural_changes','geometry_changes','metadata_changes')} for arm in ('source','emitted')}
    save(args.output/'results.json',dict(schema='frozen_revision_interpretation_v1',
        purpose='diagnostic classification, not a new reconstruction or acceptance run',
        lock_sha256=digest(args.output/'lock.json'),summary=summary,records=rows))
    print(json.dumps(summary))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    main(parser.parse_args())
