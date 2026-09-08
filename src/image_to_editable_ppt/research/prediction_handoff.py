"""이미지 단독 예측의 엄격한 연구용 handoff. 모델/GT loader는 사용하지 않는다."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

SCHEMA = 'image_only_prediction_handoff_v2'
DECLARATION_SCHEMA = 'image_only_prediction_handoff_declaration_v2'
SETTINGS = {'score_threshold': 0.5, 'cross_class_nms_iou': 0.7, 'node_containment_threshold': 0.85}
CLASS_ENTRIES = [
    {'source_label': 0, 'raw_label': 0, 'semantic_kind': 'background', 'role': 'background'},
    {'source_label': 1, 'raw_label': 1, 'semantic_kind': 'box', 'role': 'node'},
    {'source_label': 2, 'raw_label': 2, 'semantic_kind': 'rounded_box', 'role': 'node'},
    {'source_label': 3, 'raw_label': 4, 'semantic_kind': 'section', 'role': 'node'},
    {'source_label': 4, 'raw_label': 5, 'semantic_kind': 'label_anchor', 'role': 'node'},
    {'source_label': 5, 'raw_label': 6, 'semantic_kind': 'flow_cluster', 'role': 'container'},
    {'source_label': 6, 'raw_label': 7, 'semantic_kind': 'panel', 'role': 'container'},
]
UNSUPPORTED_CLASSES = [{'raw_label': 3, 'semantic_kind': 'ellipse', 'role': 'node'}]
LEGACY_ADAPTER = {str(e['source_label']): e['raw_label'] for e in CLASS_ENTRIES[1:]}
LIMITATIONS = [
    'Legacy class names are inferred from Git enum history, not recorded in the checkpoint.',
    'Inference code is a post-run reference snapshot; the actual run Git commit and code SHA are not attested.',
    'Export validates existing predictions only; it does not rerun inference or approve model performance.',
    'Synthetic validation was exposed to checkpoint selection; this is not an unseen holdout result.',
]


class HandoffError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def sha_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            hasher.update(chunk)
    return hasher.hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise HandoffError(message)


def _keys(value: Any, expected: set[str], where: str) -> None:
    _require(isinstance(value, dict) and set(value) == expected, f'{where}: missing or unknown metadata fields')


def _string(value: Any, where: str) -> None:
    _require(isinstance(value, str) and bool(value.strip()), f'{where}: nonempty string required')


def _hash(value: Any, where: str) -> None:
    _require(isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value), f'{where}: SHA-256 required')


def _finite(value: Any, where: str) -> float:
    _require(type(value) in (int, float) and math.isfinite(value), f'{where}: finite number required')
    return float(value)


def parse_json(data: bytes) -> Any:
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            _require(key not in result, f'duplicate JSON key: {key}')
            result[key] = value
        return result

    def invalid_constant(value):
        raise HandoffError(f'non-finite JSON constant: {value}')

    try:
        return json.loads(data.decode('utf-8-sig'), object_pairs_hook=unique_pairs, parse_constant=invalid_constant)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise HandoffError(f'invalid JSON: {error}') from error


def _safe_path(value: Any) -> Path:
    _string(value, 'path')
    path = Path(value)
    _require(path.is_absolute(), 'absolute source path required')
    resolved = path.resolve()
    parts = [p.lower() for p in resolved.parts]
    _require(not any(p.startswith('ds-') or 'annotation' in p or 'holdout' in p for p in parts), 'GT/dataset path forbidden')
    _require(resolved.suffix.lower() != '.pptx', 'PPT/GT input forbidden')
    return resolved


class VerifiedReads:
    def __init__(self):
        self.records: dict[str, dict[str, str]] = {}

    def file(self, reference: Any, purpose: str, *, suffix: str | None = None) -> Path:
        _keys(reference, {'path', 'sha256'}, purpose)
        _hash(reference['sha256'], purpose)
        path = _safe_path(reference['path'])
        if suffix is not None:
            _require(path.suffix.lower() == suffix, f'{purpose}: expected {suffix}')
        actual = sha_file(path)
        _require(actual == reference['sha256'], f'{purpose}: SHA mismatch')
        self.records[str(path)] = {'path': str(path), 'sha256': actual, 'purpose': purpose}
        return path

    def json(self, reference: Any, purpose: str) -> Any:
        path = self.file(reference, purpose, suffix='.json')
        data = path.read_bytes()
        _require(hashlib.sha256(data).hexdigest() == reference['sha256'], f'{purpose}: changed while reading')
        return parse_json(data)


def _signed_section(section: Any, fields: set[str], where: str) -> dict:
    _keys(section, fields | {'sha256'}, where)
    _hash(section['sha256'], where)
    body = {k: v for k, v in section.items() if k != 'sha256'}
    _require(digest(body) == section['sha256'], f'{where}: metadata SHA mismatch')
    return body


def _validate_declaration(declaration: Any, reads: VerifiedReads, allow_legacy_research: bool) -> None:
    _keys(declaration, {'schema_version', 'source_prediction', 'rgb_inputs', 'checkpoint', 'inference_code', 'class_schema', 'postprocess'}, 'declaration')
    _require(declaration['schema_version'] == DECLARATION_SCHEMA, 'unsupported declaration schema')
    classes = _signed_section(declaration['class_schema'], {'source_num_classes', 'current_num_classes', 'raw_label_space', 'entries', 'unsupported_current_classes', 'provenance'}, 'class_schema')
    _require(type(classes['source_num_classes']) is int and classes['source_num_classes'] == 7, 'source class expansion forbidden')
    _require(type(classes['current_num_classes']) is int and classes['current_num_classes'] == 8, 'current class expansion forbidden')
    _require(classes['raw_label_space'] == 'r7b_current_labels_already_remapped', 'raw label space mismatch')
    _require(canonical_bytes(classes['entries']) == canonical_bytes(CLASS_ENTRIES), 'class semantic name/role/index mismatch')
    _require(canonical_bytes(classes['unsupported_current_classes']) == canonical_bytes(UNSUPPORTED_CLASSES), 'unsupported class metadata mismatch')
    provenance = classes['provenance']
    _keys(provenance, {'kind', 'description', 'evidence'}, 'class provenance')
    _require(provenance['kind'] == 'legacy_inferred', 'unsupported class provenance; do not claim run attestation')
    _string(provenance['description'], 'class provenance description')
    _require(isinstance(provenance['evidence'], list) and len(provenance['evidence']) == 2, 'two enum history evidence files required')
    for item in provenance['evidence']:
        reads.file(item, 'class history evidence')
    inference = _signed_section(declaration['inference_code'], {'attestation', 'run_git_commit', 'reference_git_commit', 'scope', 'files'}, 'inference_code')
    _require(inference['attestation'] == 'post_run_reference_snapshot', 'unsupported inference attestation')
    _require(inference['run_git_commit'] is None, 'legacy inference run commit must remain unknown')
    commit = inference['reference_git_commit']
    _require(isinstance(commit, str) and len(commit) == 40 and all(c in '0123456789abcdef' for c in commit), 'reference Git commit required')
    _require(inference['scope'] == 'listed_project_files_only_not_execution_attested', 'inference code scope required')
    _require(isinstance(inference['files'], list) and len(inference['files']) > 0, 'inference code files required')
    _require(allow_legacy_research, 'legacy inferred provenance rejected; explicit --allow-legacy-research required')
    seen_code = set()
    for item in inference['files']:
        _keys(item, {'logical_path', 'file'}, 'inference code entry')
        _string(item['logical_path'], 'logical code path')
        _require(item['logical_path'] not in seen_code, 'duplicate inference code identity')
        seen_code.add(item['logical_path'])
        reads.file(item['file'], 'inference reference code', suffix='.py')
    _require('tools/ml_image_only_pilot.py' in seen_code, 'inference entrypoint metadata missing')
    post = declaration['postprocess']
    _keys(post, {'settings', 'implementation', 'dependencies'}, 'postprocess')
    _keys(post['settings'], set(SETTINGS), 'postprocess settings')
    for key, expected in SETTINGS.items():
        _require(_finite(post['settings'][key], key) == expected, f'{key}: frozen baseline setting mismatch')
    from image_to_editable_ppt.ml import dataset, detection_postprocess
    from image_to_editable_ppt.v3.core import enums
    implementation = reads.file(post['implementation'], 'postprocess implementation', suffix='.py')
    _require(sha_file(Path(detection_postprocess.__file__)) == sha_file(implementation), 'active postprocess implementation SHA mismatch')
    _keys(post['dependencies'], {'dataset', 'enums'}, 'postprocess dependencies')
    for name, module in [('dataset', dataset), ('enums', enums)]:
        path = reads.file(post['dependencies'][name], f'postprocess {name}', suffix='.py')
        _require(sha_file(Path(module.__file__)) == sha_file(path), f'active {name} SHA mismatch')
    current_names = {i: dataset.label_to_kind(i).value for i in range(1, 8)}
    expected_names = {e['raw_label']: e['semantic_kind'] for e in CLASS_ENTRIES[1:] + UNSUPPORTED_CLASSES}
    _require(current_names == expected_names, 'active enum/class semantics mismatch')


def build_payload(declaration: Any, *, allow_legacy_research: bool = False) -> dict:
    """Validate source bytes and export selected semantic objects without GT/model reads."""
    reads = VerifiedReads()
    _validate_declaration(declaration, reads, allow_legacy_research)
    inputs = reads.json(declaration['rgb_inputs'], 'RGB input manifest')
    prediction = reads.json(declaration['source_prediction'], 'existing RGB-only prediction')
    reads.file(declaration['checkpoint'], 'checkpoint identity only', suffix='.ckpt')
    _keys(prediction, {'checkpoint_sha256', 'inputs_sha256', 'label_adapter', 'seconds', 'predictions'}, 'source prediction')
    _require(prediction['checkpoint_sha256'] == declaration['checkpoint']['sha256'], 'prediction checkpoint SHA mismatch')
    _require(prediction['inputs_sha256'] == declaration['rgb_inputs']['sha256'], 'prediction RGB manifest SHA mismatch')
    _require(canonical_bytes(prediction['label_adapter']) == canonical_bytes(LEGACY_ADAPTER), 'source label adapter mismatch')
    _require(_finite(prediction['seconds'], 'seconds') >= 0, 'negative inference time')
    _require(isinstance(inputs, list) and len(inputs) > 0, 'nonempty RGB manifest required')
    input_by_id, image_hashes = {}, set()
    for row in inputs:
        _keys(row, {'id', 'image', 'image_sha256'}, 'RGB input')
        _string(row['id'], 'input id')
        _hash(row['image_sha256'], 'RGB input SHA')
        _require(row['id'] not in input_by_id, 'duplicate sample ID')
        _require(row['image_sha256'] not in image_hashes, 'duplicate RGB source identity')
        input_by_id[row['id']] = row
        image_hashes.add(row['image_sha256'])
    raw_rows = prediction['predictions']
    _require(isinstance(raw_rows, list) and len(raw_rows) == len(inputs), 'prediction/input sample count mismatch')
    import torch
    from PIL import Image
    from image_to_editable_ppt.ml.detection_postprocess import select_detection_indices
    semantics = {e['raw_label']: e for e in CLASS_ENTRIES[1:]}
    samples, seen = [], set()
    for raw in raw_rows:
        _keys(raw, {'id', 'source_sha256', 'image_size', 'coordinate_system', 'prediction'}, 'prediction sample')
        _string(raw['id'], 'prediction id')
        _require(raw['id'] in input_by_id and raw['id'] not in seen, 'missing or duplicate prediction sample ID')
        seen.add(raw['id'])
        row = input_by_id[raw['id']]
        _require(raw['source_sha256'] == row['image_sha256'], 'sample source SHA mismatch')
        image_ref = {'path': row['image'], 'sha256': row['image_sha256']}
        image_path = reads.file(image_ref, 'RGB source image', suffix='.png')
        image_data = image_path.read_bytes()
        _require(hashlib.sha256(image_data).hexdigest() == image_ref['sha256'], 'RGB changed while reading')
        from io import BytesIO
        with Image.open(BytesIO(image_data)) as image:
            _require(image.mode == 'RGB', 'RGB source mode required; no silent color conversion')
            width, height = image.size
        _require(isinstance(raw['image_size'], list) and all(type(v) is int for v in raw['image_size']) and raw['image_size'] == [width, height], 'RGB size mismatch')
        _require(raw['coordinate_system'] == 'original_image_pixels', 'coordinate system mismatch')
        pred = raw['prediction']
        _keys(pred, {'boxes', 'scores', 'labels'}, 'raw detection tensors')
        _require(all(isinstance(pred[k], list) for k in pred), 'detection arrays required')
        _require(len(pred['boxes']) == len(pred['scores']) == len(pred['labels']), 'detection array lengths mismatch')
        validated = []
        sample_id = 'rgb-' + row['image_sha256']
        for index, (box, score, label) in enumerate(zip(pred['boxes'], pred['scores'], pred['labels'])):
            _require(type(label) is int and label in semantics, 'unknown/background/untrained class label')
            _require(isinstance(box, list) and len(box) == 4, 'bbox_xyxy requires four coordinates')
            coords = [_finite(v, 'bbox') for v in box]
            x0, y0, x1, y1 = coords
            _require(0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height, 'bbox outside image or nonpositive area; no silent correction')
            confidence = _finite(score, 'confidence')
            _require(0 <= confidence <= 1, 'confidence out of range')
            semantic = semantics[label]
            validated.append({'id': f'{sample_id}:det:{index}', 'source_detection_index': index, 'source_label': semantic['source_label'], 'raw_label': label, 'semantic_kind': semantic['semantic_kind'], 'role': semantic['role'], 'bbox_xyxy': coords, 'raw_bbox_xyxy': box, 'confidence': confidence, 'evidence': 'rgb_detector_prediction', 'geometry_change': 'none'})
        tensor = {'boxes': torch.tensor(pred['boxes'], dtype=torch.float32).reshape(-1, 4), 'scores': torch.tensor(pred['scores'], dtype=torch.float32), 'labels': torch.tensor(pred['labels'], dtype=torch.int64)}
        selected = select_detection_indices(tensor, **SETTINGS)
        _require(len(set(selected)) == len(selected), 'duplicate selected object ID')
        selected_set = set(selected)
        omitted = [dict(object=item, reason='below_score_threshold' if item['confidence'] < SETTINGS['score_threshold'] else 'cross_class_nms_or_node_containment') for i, item in enumerate(validated) if i not in selected_set]
        samples.append({'sample_id': sample_id, 'source_record_id': row['id'], 'source_rgb': image_ref, 'image_size': [width, height], 'coordinate_system': 'original_image_pixels', 'objects': [validated[i] for i in selected], 'omitted': omitted, 'text_prediction_status': 'not_predicted', 'connection_prediction_status': 'not_predicted'})
    return {'schema_version': SCHEMA, 'research_only': True, 'limitations': LIMITATIONS, 'declaration': declaration, 'exporter_code': {'path': str(Path(__file__).resolve()), 'sha256': sha_file(Path(__file__))}, 'samples': samples, 'verified_source_files': sorted(reads.records.values(), key=lambda r: r['path'])}


def export_bundle(declaration_path: Path, output_path: Path, *, allow_legacy_research: bool = False) -> dict:
    declaration = parse_json(_safe_path(str(declaration_path.resolve())).read_bytes())
    payload = build_payload(declaration, allow_legacy_research=allow_legacy_research)
    bundle = {'payload': payload, 'payload_sha256': digest(payload)}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(bundle, indent=2, ensure_ascii=False, allow_nan=False) + '\n')
    return bundle


def validate_bundle(path: Path, *, allow_legacy_research: bool = False) -> dict:
    bundle = parse_json(path.read_bytes())
    _keys(bundle, {'payload', 'payload_sha256'}, 'bundle')
    _hash(bundle['payload_sha256'], 'bundle payload')
    _require(digest(bundle['payload']) == bundle['payload_sha256'], 'bundle payload SHA mismatch')
    payload = bundle['payload']
    _keys(payload, {'schema_version', 'research_only', 'limitations', 'declaration', 'exporter_code', 'samples', 'verified_source_files'}, 'payload')
    _require(payload['schema_version'] == SCHEMA and payload['research_only'] is True, 'research-only scope required')
    origin_code = VerifiedReads().file(payload['exporter_code'], 'exporter code', suffix='.py')
    _require(sha_file(origin_code) == sha_file(Path(__file__)), 'active exporter code SHA mismatch')
    # Re-derive every semantic object, omission and source hash; a recomputed envelope
    # hash cannot legitimize a tampered object ID, meaning, bbox or confidence.
    expected = build_payload(payload['declaration'], allow_legacy_research=allow_legacy_research)
    # Another checkout may run the identical helper. Preserve its verified origin
    # path while binding the consumer implementation by content SHA, not cwd.
    expected['exporter_code'] = payload['exporter_code']
    _require(canonical_bytes(payload) == canonical_bytes(expected), 'bundle differs from verified source derivation (IDs/objects/provenance)')
    return bundle
