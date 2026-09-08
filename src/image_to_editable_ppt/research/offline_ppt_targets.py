"""제한된 offline PPT target 추출. GT는 여기서만 읽고 추론에 전달하지 않는다."""
from __future__ import annotations

import hashlib
from io import BytesIO
import json
from pathlib import Path
import posixpath
import zipfile
from xml.etree import ElementTree as ET

from PIL import Image

NS = {'p': 'http://schemas.openxmlformats.org/presentationml/2006/main', 'a': 'http://schemas.openxmlformats.org/drawingml/2006/main'}
GEOMETRIES = {'rect': 'rect', 'roundRect': 'round_rect', 'ellipse': 'ellipse'}
ROLE_COLLECTIONS = {
    'primitive_scene.nodes': 'node',
    'primitive_scene.containers': 'container',
    'excluded_objects': 'excluded',
    'unclassified_objects': 'unknown',
}


class TargetExtractionError(ValueError):
    pass


def _require(condition, message):
    if not condition:
        raise TargetExtractionError(message)


def _keys(value, fields, where):
    _require(isinstance(value, dict) and set(value) == set(fields), f'{where}: missing/unknown fields')


def _text(value, where):
    _require(isinstance(value, str) and bool(value), f'{where}: nonempty string required')


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def canonical_sha(value):
    return sha_bytes(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode())


def reference(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': sha_bytes(path.read_bytes())}


def read_reference(ref, suffix=None):
    _keys(ref, ('path', 'sha256'), 'source reference')
    _text(ref['path'], 'source path')
    path = Path(ref['path'])
    _require(path.is_absolute(), 'absolute source path required')
    _require(isinstance(ref['sha256'], str) and len(ref['sha256']) == 64 and all(c in '0123456789abcdef' for c in ref['sha256']), 'SHA256 required')
    if suffix:
        _require(path.suffix.lower() == suffix, f'expected {suffix} source')
    data = path.read_bytes()
    _require(sha_bytes(data) == ref['sha256'], 'source SHA mismatch: ' + str(path))
    return data


def parse_json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            _require(key not in result, 'duplicate JSON identity/key')
            result[key] = value
        return result
    def bad_constant(value):
        raise TargetExtractionError('nonfinite JSON value: ' + value)
    return json.loads(data.decode('utf-8-sig'), object_pairs_hook=pairs, parse_constant=bad_constant)


def _xml(data):
    _require(b'<!DOCTYPE' not in data.upper() and b'<!ENTITY' not in data.upper(), 'unsupported XML declaration')
    return ET.fromstring(data)


def _integer(value, where):
    try:
        _require(isinstance(value, str) and value.strip() == value, f'{where}: XML integer required')
        return int(value)
    except (ValueError, TypeError) as error:
        raise TargetExtractionError(f'{where}: invalid XML integer') from error


def _boolean(value):
    _require(value in (None, '0', '1', 'false', 'true'), 'invalid XML boolean')
    return value in ('1', 'true')


def _shape_records(slide):
    identities = []
    for item in slide.findall('.//p:cNvPr', NS):
        identity = item.get('id')
        _require(identity is not None and identity.isdigit(), 'missing/invalid shape ID')
        identities.append(identity)
    _require(len(identities) == len(set(identities)), 'duplicate source shape identity')
    tree = slide.find('p:cSld/p:spTree', NS)
    _require(tree is not None, 'missing explicit shape tree')
    result = []
    shape_tags = {'sp', 'grpSp', 'cxnSp', 'pic', 'graphicFrame', 'contentPart'}
    def walk(parent, ancestry):
        for child in parent:
            kind = child.tag.rsplit('}', 1)[-1]
            if kind not in shape_tags:
                _require(kind in {'nvGrpSpPr', 'grpSpPr', 'extLst'}, 'unsupported shape-tree element')
                continue
            identity = next((item for metadata in child if metadata.tag.rsplit('}', 1)[-1].startswith('nv') for item in metadata if item.tag == '{'+NS['p']+'}cNvPr'), None)
            _require(identity is not None, 'shape identity metadata missing')
            record = {'element': child, 'shape_type': kind, 'shape_id': identity.get('id'), 'shape_name': identity.get('name', ''), 'hidden': _boolean(identity.get('hidden')), 'group_ancestry': list(ancestry)}
            result.append(record)
            if kind == 'grpSp':
                walk(child, ancestry + [identity.get('id')])
    walk(tree, [])
    return result


def _collection(document, name):
    current = document
    for key in name.split('.'):
        current = current.get(key, {}) if isinstance(current, dict) else None
    if current == {}:
        return []
    _require(isinstance(current, list), 'annotation collection must be a list')
    return current


def _roles(role_doc, case, records):
    _keys(role_doc, ('schema_version', 'sample_id', 'source_ppt_sha256', 'source_rgb_sha256', 'source_annotation', 'review', 'assignments'), 'role document')
    _require(role_doc['schema_version'] == 'offline_reviewed_roles_v1', 'unsupported role schema')
    _require(role_doc['sample_id'] == case['sample_id'], 'role sample mismatch')
    _require(role_doc['source_ppt_sha256'] == case['source_ppt']['sha256'] and role_doc['source_rgb_sha256'] == case['source_rgb']['sha256'], 'role source SHA mismatch')
    review = role_doc['review']
    _keys(review, ('status', 'method', 'reference', 'visibility_basis'), 'role review')
    _require(review['status'] == 'verified_membership_and_identity', 'unverified role review')
    _text(review['method'], 'review method')
    _text(review['visibility_basis'], 'visibility review basis')
    read_reference(review['reference'])
    annotation = parse_json(read_reference(role_doc['source_annotation'], '.json'))
    _require(annotation.get('image_id') == case['sample_id'], 'annotation sample mismatch')
    available, seen_annotations = {}, set()
    for collection in ROLE_COLLECTIONS:
        for item in _collection(annotation, collection):
            _require(isinstance(item, dict), 'invalid annotation object')
            identity = item.get('id')
            _text(identity, 'annotation object ID')
            _require(identity not in seen_annotations, 'duplicate annotation object identity')
            seen_annotations.add(identity)
            available[(collection, identity)] = item
    by_id = {item['shape_id']: item for item in records}
    _require(isinstance(role_doc['assignments'], list), 'role assignments must be a list')
    joined, used_annotation_ids = {}, set()
    for assignment in role_doc['assignments']:
        _keys(assignment, ('source_shape_id', 'source_shape_name', 'annotation_object_id', 'annotation_collection', 'semantic_role', 'visibility'), 'role assignment')
        identity = assignment['source_shape_id']
        _text(identity, 'assigned shape ID')
        _require(identity in by_id and identity not in joined, 'missing/duplicate assigned source identity')
        record = by_id[identity]
        _require(record['shape_name'] == assignment['source_shape_name'] == assignment['annotation_object_id'], 'source/annotation name join mismatch')
        _require(sum(r['shape_name'] == record['shape_name'] for r in records) == 1, 'ambiguous source name join')
        collection = assignment['annotation_collection']
        _require(collection in ROLE_COLLECTIONS and assignment['semantic_role'] == ROLE_COLLECTIONS[collection], 'role contradicts separate annotation collection')
        key = (collection, assignment['annotation_object_id'])
        _require(key in available, 'role annotation object missing')
        _require(assignment['annotation_object_id'] not in used_annotation_ids, 'duplicate role annotation identity')
        used_annotation_ids.add(assignment['annotation_object_id'])
        _require(assignment['visibility'] in ('reviewed_visible', 'unknown', 'occluded'), 'unsupported visibility review')
        joined[identity] = {'value': assignment['semantic_role'], 'source_collection': collection, 'annotation_object_id': assignment['annotation_object_id'], 'source_annotation_sha256': role_doc['source_annotation']['sha256'], 'legacy_annotation_kind': available[key].get('kind'), 'visibility': assignment['visibility']}
    return joined


def _geometry(record, transform):
    shape = record['element']
    preset = shape.find('p:spPr/a:prstGeom', NS)
    raw_preset = preset.get('prst') if preset is not None else None
    properties = shape.find('p:nvSpPr/p:cNvSpPr', NS)
    textbox = _boolean(properties.get('txBox')) if properties is not None else False
    xfrm = shape.find('p:spPr/a:xfrm', NS)
    adjustments = [dict(item.attrib) for item in preset.findall('a:avLst/a:gd', NS)] if preset is not None else []
    raw = {'prstGeom': raw_preset, 'preset_adjustments': adjustments, 'textbox': textbox, 'custom_geometry': shape.find('p:spPr/a:custGeom', NS) is not None, 'shape_type': record['shape_type'], 'group_ancestry': record['group_ancestry'], 'hidden': record['hidden'], 'transform': None}
    reasons = []
    if record['shape_type'] != 'sp':
        reasons.append('unsupported_shape_type')
    if record['group_ancestry'] or record['shape_type'] == 'grpSp':
        reasons.append('unsupported_group_transform')
    if record['hidden']:
        reasons.append('hidden_source_object')
    geometry = 'text_only' if textbox else GEOMETRIES.get(raw_preset)
    if geometry is None or raw['custom_geometry']:
        reasons.append('unsupported_geometry')
    if textbox and (shape.find('p:spPr/a:noFill', NS) is None or shape.find('p:spPr/a:ln/a:noFill', NS) is None):
        reasons.append('textbox_boundary_visibility_not_explicit')
    if textbox and not any((item.text or '').strip() for item in shape.findall('p:txBody/a:p/a:r/a:t', NS)):
        reasons.append('empty_textbox')
    bbox = None
    if xfrm is None or xfrm.find('a:off', NS) is None or xfrm.find('a:ext', NS) is None:
        reasons.append('missing_explicit_transform')
    else:
        off, ext = xfrm.find('a:off', NS), xfrm.find('a:ext', NS)
        x, y = _integer(off.get('x'), 'x'), _integer(off.get('y'), 'y')
        width, height = _integer(ext.get('cx'), 'cx'), _integer(ext.get('cy'), 'cy')
        rotation = _integer(xfrm.get('rot', '0'), 'rotation')
        flip_h, flip_v = _boolean(xfrm.get('flipH')), _boolean(xfrm.get('flipV'))
        raw['transform'] = {'offset_emu': [x, y], 'extent_emu': [width, height], 'rotation_60000th_degree': rotation, 'flipH': flip_h, 'flipV': flip_v}
        if rotation != 0:
            reasons.append('unsupported_rotation')
        if flip_h or flip_v:
            reasons.append('unsupported_flip')
        if width <= 0 or height <= 0:
            reasons.append('nonpositive_extent')
        if x < 0 or y < 0 or x + width > transform['slide_size_emu'][0] or y + height > transform['slide_size_emu'][1]:
            reasons.append('outside_slide_or_clipped')
        if not reasons:
            sx, sy = transform['scale_pixels_per_emu']
            bbox = [x * sx, y * sy, (x + width) * sx, (y + height) * sy]
    return raw, geometry if not reasons else None, bbox, reasons


def extract_case(case):
    _keys(case, ('sample_id', 'source_ppt', 'source_rgb', 'role_annotations', 'render'), 'case')
    _text(case['sample_id'], 'sample ID')
    ppt_bytes = read_reference(case['source_ppt'], '.pptx')
    rgb_bytes = read_reference(case['source_rgb'], '.png')
    roles_doc = parse_json(read_reference(case['role_annotations'], '.json'))
    _keys(roles_doc, ('schema_version', 'sample_id', 'source_ppt_sha256', 'source_rgb_sha256', 'source_annotation', 'review', 'assignments'), 'role document')
    render = case['render']
    _keys(render, ('renderer_id', 'renderer_version', 'full_slide', 'source_manifest'), 'render metadata')
    _require(render['full_slide'] is True, 'cropped/unknown render mapping unsupported')
    _text(render['renderer_id'], 'renderer ID')
    _require(render['renderer_version'] is None or isinstance(render['renderer_version'], str), 'renderer version must be explicit string or null')
    source_manifest = parse_json(read_reference(render['source_manifest'], '.json'))
    _require(source_manifest['generator']['renderer'] == render['renderer_id'], 'renderer provenance mismatch')
    source_rows = [item for item in source_manifest['samples'] if item['id'] == case['sample_id']]
    _require(len(source_rows) == 1, 'missing/duplicate source manifest identity')
    base = Path(render['source_manifest']['path']).parent
    for key, ref in [('pptx', case['source_ppt']), ('image', case['source_rgb']), ('annotation', roles_doc['source_annotation'])]:
        _require((base / source_rows[0][key]).resolve() == Path(ref['path']).resolve(), 'source manifest path mismatch')
    with Image.open(BytesIO(rgb_bytes)) as image:
        _require(image.mode == 'RGB', 'RGB source required')
        image_size = [image.width, image.height]
    expected = source_manifest['generator']['image_size']
    _require(image_size == [expected['width'], expected['height']], 'renderer pixel size mismatch')
    with zipfile.ZipFile(BytesIO(ppt_bytes)) as archive:
        _require(len(archive.namelist()) == len(set(archive.namelist())), 'duplicate PPT ZIP part identity')
        presentation = _xml(archive.read('ppt/presentation.xml'))
        slide_ids = presentation.find('p:sldIdLst', NS)
        _require(slide_ids is not None and len(slide_ids) == 1, 'prototype supports one-slide source PPT only')
        relationship_id = slide_ids[0].get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
        relationships = _xml(archive.read('ppt/_rels/presentation.xml.rels'))
        relationship_ids = [item.get('Id') for item in relationships]
        _require(len(relationship_ids) == len(set(relationship_ids)), 'duplicate slide relationship identity')
        matches = [item for item in relationships if item.get('Id') == relationship_id]
        _require(len(matches) == 1 and matches[0].get('Type', '').endswith('/slide') and matches[0].get('TargetMode') != 'External', 'invalid slide relationship')
        target = matches[0].get('Target', '')
        target = posixpath.normpath(target.lstrip('/') if target.startswith('/') else posixpath.join('ppt', target))
        _require(target == 'ppt/slides/slide1.xml', 'prototype requires explicit first slide part')
        slide = _xml(archive.read('ppt/slides/slide1.xml'))
    size = presentation.find('p:sldSz', NS)
    _require(size is not None, 'missing slide size')
    slide_size = [_integer(size.get('cx'), 'slide cx'), _integer(size.get('cy'), 'slide cy')]
    _require(all(value > 0 for value in slide_size), 'nonpositive slide size')
    sx, sy = image_size[0] / slide_size[0], image_size[1] / slide_size[1]
    transform = {'slide_size_emu': slide_size, 'rgb_size_pixels': image_size, 'scale_pixels_per_emu': [sx, sy], 'matrix_slide_emu_to_pixels': [[sx, 0, 0], [0, sy, 0], [0, 0, 1]], 'crop': 'none_declared', 'mapping_provenance': 'declared_full_slide_from_source_manifest_not_render_reexecuted', 'renderer_id': render['renderer_id'], 'renderer_version': render['renderer_version'], 'renderer_version_status': 'not_recorded' if render['renderer_version'] is None else 'declared'}
    records = _shape_records(slide)
    roles = _roles(roles_doc, case, records)
    targets = []
    for record in records:
        raw, geometry, bbox, reasons = _geometry(record, transform)
        role = roles.get(record['shape_id'], {'value': 'unknown', 'source_collection': None, 'annotation_object_id': None, 'source_annotation_sha256': None, 'legacy_annotation_kind': None, 'visibility': 'unknown'})
        if role['value'] == 'unknown':
            reasons.append('unverified_or_unknown_role')
        elif role['value'] == 'excluded':
            reasons.append('non_structural_role')
        if role['visibility'] != 'reviewed_visible':
            reasons.append('visibility_not_verified')
        supervise = not reasons
        targets.append({'object_id': case['source_ppt']['sha256'] + ':ppt/slides/slide1.xml:shape:' + record['shape_id'], 'source_shape_id': record['shape_id'], 'source_shape_name': record['shape_name'], 'semantic_role': role, 'raw_geometry': raw, 'rendered_geometry': {'value': geometry, 'source': 'source_ppt_xml', 'label_state': 'supported_source_geometry' if geometry else 'unsupported'}, 'bbox_xyxy_pixels': bbox, 'annotation_bbox_used': False, 'supervision_mask': {'role': supervise, 'geometry': supervise, 'bbox': supervise}, 'mask_reasons': reasons})
    return {'sample_id': case['sample_id'], 'source_ppt': case['source_ppt'], 'source_rgb': case['source_rgb'], 'source_annotation': roles_doc['source_annotation'], 'role_annotations': case['role_annotations'], 'role_review': roles_doc['review'], 'source_manifest': render['source_manifest'], 'coordinate_system': 'rendered_rgb_pixels', 'render_transform': transform, 'objects': targets}


def extract_request(request):
    _keys(request, ('schema_version', 'cases'), 'request')
    _require(request['schema_version'] == 'offline_target_request_v1', 'unsupported request schema')
    _require(isinstance(request['cases'], list) and len(request['cases']) > 0, 'nonempty cases required')
    sample_ids = [case.get('sample_id') for case in request['cases']]
    _require(all(isinstance(value, str) for value in sample_ids) and len(sample_ids) == len(set(sample_ids)), 'duplicate/invalid request sample identity')
    cases = [extract_case(case) for case in request['cases']]
    identities = [obj['object_id'] for case in cases for obj in case['objects']]
    _require(len(identities) == len(set(identities)), 'duplicate target identity across cases')
    return {'schema_version': 'offline_role_geometry_targets_v1', 'research_only': True, 'inference_input_allowed': False, 'training_performed': False, 'request_sha256': canonical_sha(request), 'extractor_sha256': sha_bytes(Path(__file__).read_bytes()), 'limitations': ['Only explicit, ungrouped, unrotated, unflipped rect/roundRect/ellipse and explicit borderless textbox geometry is supported.', 'Role supervision comes only from separately reviewed annotation membership; preset alone never supplies a role.', 'Renderer mapping is declared full-slide and not rerendered here; unavailable renderer version remains null.', 'These two existing validation graph cases are a target contract diagnosis, not unseen evaluation or product improvement.'], 'cases': cases}


def extract_to_file(request_path, output_path):
    request = parse_json(Path(request_path).read_bytes())
    result = extract_request(request)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + '\n')
    return result
