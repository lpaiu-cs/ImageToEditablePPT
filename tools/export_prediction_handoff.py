"""기존 v1 RGB 예측을 v2 연구 계약으로 고정한다. 추론/학습/GT 읽기는 하지 않는다."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from image_to_editable_ppt.research import prediction_handoff as contract

REFERENCE_COMMIT = '7bb2beddcd50ffd65146082a6f82947f3a2613e1'


def reference(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': contract.sha_file(path)}


def signed(body):
    return dict(body, sha256=contract.digest(body))


def write_new(path, body):
    with path.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(body, indent=2, ensure_ascii=False, allow_nan=False) + '\n')


def prepare(args):
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    snapshots = out / 'provenance'
    snapshots.mkdir()

    def snapshot(git_spec, filename, only_path=None):
        command = ['rtk', 'proxy', 'git', 'show', git_spec]
        if only_path:
            command += ['--', only_path]
        result = subprocess.run(command, cwd=ROOT, check=True, capture_output=True)
        path = snapshots / filename
        path.write_bytes(result.stdout)
        return reference(path)

    logical_files = [
        'tools/ml_image_only_pilot.py',
        'src/image_to_editable_ppt/ml/lightning_module.py',
        'src/image_to_editable_ppt/ml/dataset.py',
        'src/image_to_editable_ppt/v3/core/enums.py',
    ]
    code_files = [{'logical_path': logical, 'file': snapshot(REFERENCE_COMMIT + ':' + logical, Path(logical).name)} for logical in logical_files]
    files_by_name = {Path(item['logical_path']).name: item['file'] for item in code_files}
    class_schema = signed({
        'source_num_classes': 7,
        'current_num_classes': 8,
        'raw_label_space': 'r7b_current_labels_already_remapped',
        'entries': contract.CLASS_ENTRIES,
        'unsupported_current_classes': contract.UNSUPPORTED_CLASSES,
        'provenance': {
            'kind': 'legacy_inferred',
            'description': 'Inferred from pre-ellipse enum and insertion diff. The v13 checkpoint lacks class names and run code SHA; this is not execution attestation.',
            'evidence': [snapshot('a00d61c:src/image_to_editable_ppt/v3/core/enums.py', 'legacy_enums.py'), snapshot('3ae7caf', 'ellipse_insertion.patch', 'src/image_to_editable_ppt/v3/core/enums.py')],
        },
    })
    declaration = {
        'schema_version': contract.DECLARATION_SCHEMA,
        'source_prediction': reference(args.v1_root / 'baseline_legacy_predictions.json'),
        'rgb_inputs': reference(args.v1_root / 'rgb_inputs.json'),
        'checkpoint': reference(args.checkpoint),
        'inference_code': signed({'attestation': 'post_run_reference_snapshot', 'run_git_commit': None, 'reference_git_commit': REFERENCE_COMMIT, 'scope': 'listed_project_files_only_not_execution_attested', 'files': code_files}),
        'class_schema': class_schema,
        'postprocess': {'settings': contract.SETTINGS, 'implementation': snapshot(REFERENCE_COMMIT + ':src/image_to_editable_ppt/ml/detection_postprocess.py', 'detection_postprocess.py'), 'dependencies': {'dataset': files_by_name['dataset.py'], 'enums': files_by_name['enums.py']}},
    }
    write_new(out / 'declaration.json', declaration)
    print(out / 'declaration.json')


def install_read_guard(declaration, entry_path, output_paths, extra_refs=()):
    # Warm lazy library imports before restricting all subsequent file opens.
    from PIL import Image
    from image_to_editable_ppt.ml import dataset, detection_postprocess
    from image_to_editable_ppt.v3.core import enums
    Image.init()
    allowed = {Path(entry_path).resolve(), Path(contract.__file__).resolve(), Path(__file__).resolve()}
    allowed.update(Path(module.__file__).resolve() for module in (dataset, detection_postprocess, enums))
    def add_refs(value):
        if isinstance(value, dict):
            if set(value) == {'path', 'sha256'}:
                allowed.add(contract._safe_path(value['path']))
            for child in value.values():
                add_refs(child)
        elif isinstance(value, list):
            for child in value:
                add_refs(child)
    add_refs(declaration)
    add_refs(list(extra_refs))
    inputs = contract.VerifiedReads().json(declaration['rgb_inputs'], 'RGB input manifest')
    for row in inputs:
        contract._keys(row, {'id', 'image', 'image_sha256'}, 'RGB input')
        allowed.add(contract._safe_path(row['image']))
    writes = {Path(path).resolve() for path in output_paths}
    events = []
    def audit(event, values):
        if event != 'open' or not isinstance(values[0], (str, bytes)):
            return
        path = Path(values[0].decode() if isinstance(values[0], bytes) else values[0]).resolve()
        mode = values[1]
        writing = isinstance(mode, str) and any(c in mode for c in 'wax+')
        permitted = path in (writes if writing else allowed)
        events.append({'path': str(path), 'mode': str(mode), 'allowed': permitted})
        if not permitted:
            raise PermissionError('handoff read/write allowlist rejected: ' + str(path))
    sys.addaudithook(audit)
    return events


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='stage', required=True)
    p = commands.add_parser('prepare-legacy')
    p.add_argument('--v1-root', type=Path, required=True)
    p.add_argument('--checkpoint', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    p = commands.add_parser('export')
    p.add_argument('--declaration', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--allow-legacy-research', action='store_true')
    p = commands.add_parser('validate')
    p.add_argument('--bundle', type=Path, required=True)
    p.add_argument('--allow-legacy-research', action='store_true')
    args = parser.parse_args(argv)
    if args.stage == 'prepare-legacy':
        prepare(args)
        return 0
    entry = args.declaration if args.stage == 'export' else args.bundle
    initial = contract.parse_json(entry.read_bytes())
    declaration = initial if args.stage == 'export' else initial['payload']['declaration']
    audit_path = args.output.with_name(args.output.name + '.reads.json') if args.stage == 'export' else args.bundle.with_name(args.bundle.name + '.validation.reads.json')
    if audit_path.exists():
        raise FileExistsError(audit_path)
    writes = [audit_path] + ([args.output] if args.stage == 'export' else [])
    extra_refs = [initial['payload']['exporter_code']] if args.stage == 'validate' else []
    events = install_read_guard(declaration, entry, writes, extra_refs)
    try:
        if args.stage == 'export':
            bundle = contract.export_bundle(args.declaration, args.output, allow_legacy_research=args.allow_legacy_research)
        else:
            bundle = contract.validate_bundle(args.bundle, allow_legacy_research=args.allow_legacy_research)
        write_new(audit_path, {'status': 'accepted_research_only', 'scope': 'all Python file opens after metadata/library initialization', 'events': list(events)})
        payload = bundle['payload']
        print(json.dumps({'payload_sha256': bundle['payload_sha256'], 'research_only': payload['research_only'], 'samples': len(payload['samples']), 'objects': sum(len(s['objects']) for s in payload['samples'])}))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        write_new(audit_path, {'status': 'rejected', 'error': str(error), 'events': list(events)})
        print(str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
