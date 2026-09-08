"""기존 graph 두 개에 한정한 offline target prototype 준비 및 실행."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from image_to_editable_ppt.research import offline_ppt_targets as targets


def write_new(path, value):
    with path.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n')


def prepare(args):
    audit_path = args.audit.resolve()
    audit = targets.parse_json(audit_path.read_bytes())
    expected_ids = {'graph_1302_00029', 'graph_1302_00063'}
    if {case['id'] for case in audit['cases']} != expected_ids or len(audit['cases']) != 2:
        raise targets.TargetExtractionError('prototype preparation is limited to the two reviewed graph cases')
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    cases = []
    for case in audit['cases']:
        ppt = Path(case['source_ppt'])
        rgb = ppt.with_suffix('.png')
        annotation = ppt.with_suffix('.json')
        source_manifest = ppt.parent.parent / 'dataset_manifest.json'
        for path, expected_sha in [(ppt, case['source_ppt_sha256']), (rgb, case['source_rgb_sha256']), (annotation, case['annotation_sha256'])]:
            targets.read_reference({'path': str(path), 'sha256': expected_sha})
        annotation_doc = targets.parse_json(annotation.read_bytes())
        node_ids = {node['id'] for node in annotation_doc['primitive_scene']['nodes']}
        if node_ids != {node['id'] for node in case['nodes']}:
            raise targets.TargetExtractionError('reviewed node membership changed')
        roles = {
            'schema_version': 'offline_reviewed_roles_v1', 'sample_id': case['id'],
            'source_ppt_sha256': case['source_ppt_sha256'], 'source_rgb_sha256': case['source_rgb_sha256'],
            'source_annotation': targets.reference(annotation),
            'review': {'status': 'verified_membership_and_identity', 'method': 'previous two-source XML identity audit plus existing annotation node membership; preset is not a role source', 'reference': targets.reference(audit_path), 'visibility_basis': '2026-09-08 manual view of these same two RGB images; selected 11 node boundaries and labels visible; other objects not reviewed for supervision'},
            'assignments': [{'source_shape_id': node['source_ppt']['ppt_shape_id'], 'source_shape_name': node['id'], 'annotation_object_id': node['id'], 'annotation_collection': 'primitive_scene.nodes', 'semantic_role': 'node', 'visibility': 'reviewed_visible'} for node in case['nodes']],
        }
        role_path = output / (case['id'] + '.roles.json')
        write_new(role_path, roles)
        generator = targets.parse_json(source_manifest.read_bytes())['generator']
        cases.append({'sample_id': case['id'], 'source_ppt': targets.reference(ppt), 'source_rgb': targets.reference(rgb), 'role_annotations': targets.reference(role_path), 'render': {'renderer_id': generator['renderer'], 'renderer_version': None, 'full_slide': True, 'source_manifest': targets.reference(source_manifest)}})
    request_path = output / 'request.json'
    write_new(request_path, {'schema_version': 'offline_target_request_v1', 'cases': cases})
    print(request_path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='stage', required=True)
    command = commands.add_parser('prepare')
    command.add_argument('--audit', type=Path, required=True)
    command.add_argument('--output-dir', type=Path, required=True)
    command = commands.add_parser('extract')
    command.add_argument('--request', type=Path, required=True)
    command.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.stage == 'prepare':
            prepare(args)
        else:
            result = targets.extract_to_file(args.request, args.output)
            objects = [obj for case in result['cases'] for obj in case['objects']]
            print(json.dumps({'samples': len(result['cases']), 'supervised_geometry': dict(Counter(obj['rendered_geometry']['value'] for obj in objects if obj['supervision_mask']['geometry'])), 'masked_objects': sum(not obj['supervision_mask']['geometry'] for obj in objects), 'extractor_sha256': result['extractor_sha256']}))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
