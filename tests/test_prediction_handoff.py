from copy import deepcopy
import json
from pathlib import Path

from PIL import Image
import pytest

from image_to_editable_ppt.research import prediction_handoff as h


def ref(path):
    return {'path': str(path.resolve()), 'sha256': h.sha_file(path)}


def signed(body):
    return dict(body, sha256=h.digest(body))


def resign(body):
    body['sha256'] = h.digest({k: v for k, v in body.items() if k != 'sha256'})


@pytest.fixture
def data(tmp_path):
    from image_to_editable_ppt.ml import dataset, detection_postprocess
    from image_to_editable_ppt.v3.core import enums
    image_path = tmp_path / 'rgb.png'
    Image.new('RGB', (32, 24), 'white').save(image_path)
    inputs = [{'id': 'opaque-one', 'image': str(image_path), 'image_sha256': h.sha_file(image_path)}]
    input_path = tmp_path / 'inputs.json'
    input_path.write_text(json.dumps(inputs))
    checkpoint = tmp_path / 'identity.ckpt'
    checkpoint.write_bytes(b'identity-only; never deserialized')
    prediction = {'checkpoint_sha256': h.sha_file(checkpoint), 'inputs_sha256': h.sha_file(input_path), 'label_adapter': h.LEGACY_ADAPTER, 'seconds': 1.0, 'predictions': [{'id': 'opaque-one', 'source_sha256': h.sha_file(image_path), 'image_size': [32, 24], 'coordinate_system': 'original_image_pixels', 'prediction': {'boxes': [[1.,1.,12.,12.], [2.,2.,12.,12.], [0.,0.,20.,20.]], 'scores': [.9,.8,.7], 'labels': [1,2,6]}}]}
    prediction_path = tmp_path / 'prediction.json'
    prediction_path.write_text(json.dumps(prediction))
    evidence = []
    for name in ('before.txt', 'insertion.txt'):
        path = tmp_path / name
        path.write_text('test fixture, not execution provenance')
        evidence.append(ref(path))
    declaration = {
        'schema_version': h.DECLARATION_SCHEMA,
        'source_prediction': ref(prediction_path), 'rgb_inputs': ref(input_path), 'checkpoint': ref(checkpoint),
        'class_schema': signed({'source_num_classes': 7, 'current_num_classes': 8, 'raw_label_space': 'r7b_current_labels_already_remapped', 'entries': deepcopy(h.CLASS_ENTRIES), 'unsupported_current_classes': deepcopy(h.UNSUPPORTED_CLASSES), 'provenance': {'kind': 'legacy_inferred', 'description': 'test fixture with explicit uncertainty', 'evidence': evidence}}),
        'inference_code': signed({'attestation': 'post_run_reference_snapshot', 'run_git_commit': None, 'reference_git_commit': 'a'*40, 'scope': 'listed_project_files_only_not_execution_attested', 'files': [{'logical_path': 'tools/ml_image_only_pilot.py', 'file': ref(Path(h.__file__))}]}),
        'postprocess': {'settings': deepcopy(h.SETTINGS), 'implementation': ref(Path(detection_postprocess.__file__)), 'dependencies': {'dataset': ref(Path(dataset.__file__)), 'enums': ref(Path(enums.__file__))}},
    }
    return declaration, prediction, tmp_path


def change_prediction(data, edit):
    declaration, prediction, _ = data
    edit(prediction)
    path = Path(declaration['source_prediction']['path'])
    path.write_text(json.dumps(prediction))
    declaration['source_prediction'] = ref(path)


def test_explicit_legacy_export_preserves_raw_values_semantics_and_omissions(data):
    declaration, _, _ = data
    payload = h.build_payload(declaration, allow_legacy_research=True)
    assert payload['research_only'] is True
    assert payload['declaration']['inference_code']['run_git_commit'] is None
    sample = payload['samples'][0]
    assert [(o['semantic_kind'], o['role']) for o in sample['objects']] == [('box', 'node'), ('flow_cluster', 'container')]
    assert sample['objects'][0]['bbox_xyxy'] == sample['objects'][0]['raw_bbox_xyxy']
    assert sample['omitted'][0]['object']['raw_label'] == 2
    assert sample['omitted'][0]['reason'] == 'cross_class_nms_or_node_containment'
    assert sample['connection_prediction_status'] == 'not_predicted'


def test_strict_default_rejects_legacy_provenance(data):
    with pytest.raises(h.HandoffError, match='allow-legacy-research'):
        h.build_payload(data[0])


@pytest.mark.parametrize('field', ['class_schema', 'inference_code', 'checkpoint', 'postprocess'])
def test_missing_metadata_is_rejected(data, field):
    del data[0][field]
    with pytest.raises(h.HandoffError, match='metadata'):
        h.build_payload(data[0], allow_legacy_research=True)


@pytest.mark.parametrize('change', ['name', 'role', 'source_expansion', 'current_expansion', 'bool_index'])
def test_resigned_but_false_class_metadata_is_rejected(data, change):
    classes = data[0]['class_schema']
    if change == 'name':
        classes['entries'][1]['semantic_kind'] = 'ellipse'
    elif change == 'role':
        classes['entries'][1]['role'] = 'container'
    elif change == 'source_expansion':
        classes['source_num_classes'] = 8
    elif change == 'current_expansion':
        classes['current_num_classes'] = 9
    else:
        classes['entries'][1]['source_label'] = True
    resign(classes)
    with pytest.raises(h.HandoffError, match='class'):
        h.build_payload(data[0], allow_legacy_research=True)


@pytest.mark.parametrize('label', [0, 3, 8, 999, True, 1.0])
def test_unknown_or_untrained_raw_class_is_rejected(data, label):
    change_prediction(data, lambda p: p['predictions'][0]['prediction']['labels'].__setitem__(0, label))
    with pytest.raises(h.HandoffError, match='class label'):
        h.build_payload(data[0], allow_legacy_research=True)


@pytest.mark.parametrize('box', [[0,0,float('nan'),10], [0,0,float('inf'),10], [-1,0,10,10], [0,0,33,10], [1,1,1,10], [1,5,10,4]])
def test_bad_geometry_fails_even_before_score_filter(data, box):
    change_prediction(data, lambda p: p['predictions'][0]['prediction']['boxes'].__setitem__(0, box))
    with pytest.raises(h.HandoffError, match='finite|bbox'):
        h.build_payload(data[0], allow_legacy_research=True)


@pytest.mark.parametrize('score', [-.1, 1.1, float('nan'), float('inf')])
def test_bad_confidence_fails_closed(data, score):
    change_prediction(data, lambda p: p['predictions'][0]['prediction']['scores'].__setitem__(0, score))
    with pytest.raises(h.HandoffError, match='finite|confidence'):
        h.build_payload(data[0], allow_legacy_research=True)


@pytest.mark.parametrize('kind', ['image_size', 'source_sha256', 'coordinate_system'])
def test_source_contract_mismatch(data, kind):
    value = [31, 24] if kind == 'image_size' else ('0'*64 if kind == 'source_sha256' else 'normalized')
    change_prediction(data, lambda p: p['predictions'][0].__setitem__(kind, value))
    with pytest.raises(h.HandoffError, match='mismatch'):
        h.build_payload(data[0], allow_legacy_research=True)


def test_source_checkpoint_hash_is_checked_without_deserialization(data):
    Path(data[0]['checkpoint']['path']).write_bytes(b'tampered')
    with pytest.raises(h.HandoffError, match='SHA mismatch'):
        h.build_payload(data[0], allow_legacy_research=True)


def test_duplicate_sample_id_is_rejected(data):
    declaration, prediction, _ = data
    path = Path(declaration['rgb_inputs']['path'])
    inputs = json.loads(path.read_text())
    path.write_text(json.dumps(inputs + inputs))
    declaration['rgb_inputs'] = ref(path)
    change_prediction(data, lambda p: p.__setitem__('inputs_sha256', declaration['rgb_inputs']['sha256']))
    with pytest.raises(h.HandoffError, match='duplicate sample'):
        h.build_payload(declaration, allow_legacy_research=True)


@pytest.mark.parametrize('kind', ['duplicate_object_id', 'wrong_kind', 'changed_bbox', 'research_flag'])
def test_resigned_bundle_tampering_cannot_pass_source_rederivation(data, kind):
    payload = h.build_payload(data[0], allow_legacy_research=True)
    objects = payload['samples'][0]['objects']
    if kind == 'duplicate_object_id':
        objects[1]['id'] = objects[0]['id']
    elif kind == 'wrong_kind':
        objects[0]['semantic_kind'] = 'ellipse'
    elif kind == 'changed_bbox':
        objects[0]['bbox_xyxy'][0] += 1
    else:
        payload['research_only'] = False
    path = data[2] / 'bundle.json'
    path.write_text(json.dumps({'payload': payload, 'payload_sha256': h.digest(payload)}))
    with pytest.raises(h.HandoffError, match='scope|derivation'):
        h.validate_bundle(path, allow_legacy_research=True)


def test_no_silent_metadata_repair_or_run_attestation(data):
    code = data[0]['inference_code']
    code['run_git_commit'] = 'a'*40
    resign(code)
    with pytest.raises(h.HandoffError, match='must remain unknown'):
        h.build_payload(data[0], allow_legacy_research=True)


def test_declared_postprocess_sha_must_match_active_implementation(data):
    path = data[2] / 'different.py'
    path.write_text('# different NMS')
    data[0]['postprocess']['implementation'] = ref(path)
    with pytest.raises(h.HandoffError, match='active postprocess'):
        h.build_payload(data[0], allow_legacy_research=True)


def test_export_and_validate_do_not_overwrite(data):
    declaration, _, root = data
    path = root / 'declaration.json'
    path.write_text(json.dumps(declaration))
    output = root / 'bundle.json'
    original = h.export_bundle(path, output, allow_legacy_research=True)
    assert h.validate_bundle(output, allow_legacy_research=True) == original
    with pytest.raises(FileExistsError):
        h.export_bundle(path, output, allow_legacy_research=True)


def test_gt_path_rejected_before_open(tmp_path):
    path = tmp_path / 'ds-private' / 'target.json'
    with pytest.raises(h.HandoffError, match='GT/dataset'):
        h.VerifiedReads().file({'path': str(path), 'sha256': 'a'*64}, 'malicious source')


def test_duplicate_json_keys_are_rejected():
    with pytest.raises(h.HandoffError, match='duplicate JSON'):
        h.parse_json(b'{"id":1,"id":2}')


def test_cli_allowlist_denies_even_an_unlabelled_unlisted_file(data):
    import subprocess
    import sys
    declaration, _, root = data
    path = root / 'declaration.json'
    path.write_text(json.dumps(declaration))
    secret = root / 'unlisted.json'
    secret.write_text('{"sensitive":true}')
    code = "import sys; from pathlib import Path; sys.path.insert(0,'tools'); import export_prediction_handoff as t; d=t.contract.parse_json(Path(sys.argv[1]).read_bytes()); t.install_read_guard(d,Path(sys.argv[1]),[]); Path(sys.argv[2]).read_bytes()"
    result = subprocess.run([sys.executable, '-c', code, str(path), str(secret)], cwd=Path(__file__).parents[1], capture_output=True, text=True)
    assert result.returncode != 0
    assert 'allowlist rejected' in result.stderr
    assert 'sensitive' not in result.stdout


def test_cli_export_and_independent_validation_with_read_audits(data):
    import subprocess
    import sys
    declaration, _, root = data
    path = root / 'declaration.json'
    path.write_text(json.dumps(declaration))
    output = root / 'handoff.json'
    command = [sys.executable, 'tools/export_prediction_handoff.py']
    cwd = Path(__file__).parents[1]
    exported = subprocess.run(command + ['export', '--declaration', str(path), '--output', str(output), '--allow-legacy-research'], cwd=cwd, capture_output=True, text=True)
    assert exported.returncode == 0, exported.stderr
    validated = subprocess.run(command + ['validate', '--bundle', str(output), '--allow-legacy-research'], cwd=cwd, capture_output=True, text=True)
    assert validated.returncode == 0, validated.stderr
    audits = sorted(root.glob('*.reads.json'))
    assert len(audits) == 2
    for audit in audits:
        result = json.loads(audit.read_text())
        assert result['status'] == 'accepted_research_only'
        assert all(event['allowed'] for event in result['events'])


def test_evaluator_iou_cannot_silently_replace_nms_setting(data):
    settings = data[0]['postprocess']['settings']
    settings['iou'] = settings.pop('cross_class_nms_iou')
    with pytest.raises(h.HandoffError, match='metadata'):
        h.build_payload(data[0], allow_legacy_research=True)


def test_same_helper_content_from_another_checkout_can_validate(data):
    payload = h.build_payload(data[0], allow_legacy_research=True)
    snapshot = data[2] / 'origin_helper.py'
    snapshot.write_bytes(Path(h.__file__).read_bytes())
    payload['exporter_code'] = ref(snapshot)
    bundle = {'payload': payload, 'payload_sha256': h.digest(payload)}
    path = data[2] / 'portable.json'
    path.write_text(json.dumps(bundle))
    assert h.validate_bundle(path, allow_legacy_research=True) == bundle
    snapshot.write_text('# changed exporter')
    payload['exporter_code'] = ref(snapshot)
    path.write_text(json.dumps({'payload': payload, 'payload_sha256': h.digest(payload)}))
    with pytest.raises(h.HandoffError, match='active exporter code SHA'):
        h.validate_bundle(path, allow_legacy_research=True)
