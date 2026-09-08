from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import zipfile

from PIL import Image
import pytest

from image_to_editable_ppt.research import offline_ppt_targets as t

P = t.NS['p']
A = t.NS['a']
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'


def fixture_request(tmp_path, *, preset='ellipse', role='node', assigned=True, grouped=False, transform='', extent='cx="2000" cy="1000"', offset='x="1000" y="500"', textbox=False, borderless=True, hidden=False, duplicate_id=False, duplicate_name=False, slide_target='slides/slide1.xml', extra_tree_element=''):
    name = 'object:a'
    shape = f'''<p:sp><p:nvSpPr><p:cNvPr id="2" name="{name}" hidden="{int(hidden)}"/><p:cNvSpPr txBox="{int(textbox)}"/></p:nvSpPr><p:spPr><a:xfrm {transform}><a:off {offset}/><a:ext {extent}/></a:xfrm><a:prstGeom prst="{preset}"><a:avLst/></a:prstGeom>{'<a:noFill/><a:ln><a:noFill/></a:ln>' if borderless else ''}</p:spPr><p:txBody><a:p><a:r><a:t>label</a:t></a:r></a:p></p:txBody></p:sp>'''
    if duplicate_id or duplicate_name:
        duplicate = shape.replace('name="object:a"', 'name="object:b"') if duplicate_id else shape.replace('id="2"', 'id="3"')
        shape += duplicate
    if grouped:
        shape = '<p:grpSp><p:nvGrpSpPr><p:cNvPr id="10" name="group"/></p:nvGrpSpPr><p:grpSpPr/>' + shape + '</p:grpSp>'
    slide = f'<p:sld xmlns:p="{P}" xmlns:a="{A}"><p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/></p:nvGrpSpPr><p:grpSpPr/>{shape}{extra_tree_element}</p:spTree></p:cSld></p:sld>'
    presentation = f'<p:presentation xmlns:p="{P}" xmlns:r="{R}"><p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst><p:sldSz cx="6400" cy="3200"/></p:presentation>'
    rels = f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="{R}/slide" Target="{slide_target}"/></Relationships>'
    ppt = tmp_path / 'source.pptx'
    with zipfile.ZipFile(ppt, 'w') as archive:
        archive.writestr('ppt/presentation.xml', presentation)
        archive.writestr('ppt/_rels/presentation.xml.rels', rels)
        archive.writestr('ppt/slides/slide1.xml', slide)
    rgb = tmp_path / 'source.png'
    Image.new('RGB', (64, 32), 'white').save(rgb)
    annotation = {'image_id': 'sample', 'primitive_scene': {'nodes': [], 'containers': []}, 'excluded_objects': [], 'unclassified_objects': []}
    collection = {'node': 'primitive_scene.nodes', 'container': 'primitive_scene.containers', 'excluded': 'excluded_objects', 'unknown': 'unclassified_objects'}[role]
    item = {'id': name, 'kind': 'box', 'bbox': {'x0': 999, 'y0': 999, 'x1': 1000, 'y1': 1000}}
    if collection.startswith('primitive_scene.'):
        annotation['primitive_scene'][collection.split('.')[1]].append(item)
    else:
        annotation[collection].append(item)
    annotation_path = tmp_path / 'source.json'
    annotation_path.write_text(json.dumps(annotation))
    review_path = tmp_path / 'review.txt'
    review_path.write_text('unit fixture of metadata validation only; not a rendered-image evaluation')
    roles = {'schema_version': 'offline_reviewed_roles_v1', 'sample_id': 'sample', 'source_ppt_sha256': t.reference(ppt)['sha256'], 'source_rgb_sha256': t.reference(rgb)['sha256'], 'source_annotation': t.reference(annotation_path), 'review': {'status': 'verified_membership_and_identity', 'method': 'unit-fixture membership', 'reference': t.reference(review_path), 'visibility_basis': 'declared for unit test'}, 'assignments': [{'source_shape_id': '2', 'source_shape_name': name, 'annotation_object_id': name, 'annotation_collection': collection, 'semantic_role': role, 'visibility': 'reviewed_visible'}] if assigned else []}
    role_path = tmp_path / 'roles.json'
    role_path.write_text(json.dumps(roles))
    manifest = {'generator': {'renderer': 'unit_fixture', 'image_size': {'width': 64, 'height': 32}}, 'samples': [{'id': 'sample', 'image': 'source.png', 'pptx': 'source.pptx', 'annotation': 'source.json'}]}
    manifest_path = tmp_path / 'dataset_manifest.json'
    manifest_path.write_text(json.dumps(manifest))
    return {'schema_version': 'offline_target_request_v1', 'cases': [{'sample_id': 'sample', 'source_ppt': t.reference(ppt), 'source_rgb': t.reference(rgb), 'role_annotations': t.reference(role_path), 'render': {'renderer_id': 'unit_fixture', 'renderer_version': None, 'full_slide': True, 'source_manifest': t.reference(manifest_path)}}]}


def object_target(request):
    return next(obj for obj in t.extract_request(request)['cases'][0]['objects'] if obj['source_shape_id'] == '2')


def edit_roles(request, edit):
    case = request['cases'][0]
    path = Path(case['role_annotations']['path'])
    roles = json.loads(path.read_text())
    edit(roles)
    path.write_text(json.dumps(roles))
    case['role_annotations'] = t.reference(path)


@pytest.mark.parametrize(('preset', 'expected'), [('rect', 'rect'), ('roundRect', 'round_rect'), ('ellipse', 'ellipse')])
def test_supported_source_preset_is_independent_of_legacy_kind_and_bbox(tmp_path, preset, expected):
    obj = object_target(fixture_request(tmp_path, preset=preset))
    assert obj['semantic_role']['value'] == 'node'
    assert obj['semantic_role']['legacy_annotation_kind'] == 'box'
    assert obj['rendered_geometry']['value'] == expected
    assert obj['raw_geometry']['prstGeom'] == preset
    assert obj['bbox_xyxy_pixels'] == [10, 5, 30, 15]
    assert obj['annotation_bbox_used'] is False
    assert all(obj['supervision_mask'].values())


def test_explicit_borderless_textbox_is_supported(tmp_path):
    obj = object_target(fixture_request(tmp_path, preset='rect', textbox=True))
    assert obj['rendered_geometry']['value'] == 'text_only'
    assert obj['raw_geometry']['prstGeom'] == 'rect'
    assert obj['supervision_mask']['geometry'] is True


@pytest.mark.parametrize('preset', ['rect', 'roundRect', 'ellipse'])
def test_native_preset_without_verified_role_never_becomes_a_node_target(tmp_path, preset):
    obj = object_target(fixture_request(tmp_path, preset=preset, assigned=False))
    assert obj['semantic_role']['value'] == 'unknown'
    assert not any(obj['supervision_mask'].values())
    assert 'unverified_or_unknown_role' in obj['mask_reasons']


@pytest.mark.parametrize('role', ['excluded', 'unknown'])
def test_explicit_nonstructural_or_unknown_role_stays_masked(tmp_path, role):
    obj = object_target(fixture_request(tmp_path, role=role))
    assert obj['semantic_role']['value'] == role
    assert not any(obj['supervision_mask'].values())


def test_same_preset_can_be_container_only_from_separate_membership(tmp_path):
    obj = object_target(fixture_request(tmp_path, preset='rect', role='container'))
    assert obj['semantic_role']['value'] == 'container'
    assert obj['supervision_mask']['role'] is True


@pytest.mark.parametrize(('settings', 'reason'), [
    ({'grouped': True}, 'unsupported_group_transform'),
    ({'transform': 'rot="60000"'}, 'unsupported_rotation'),
    ({'transform': 'flipH="1"'}, 'unsupported_flip'),
    ({'transform': 'flipV="true"'}, 'unsupported_flip'),
    ({'preset': 'triangle'}, 'unsupported_geometry'),
    ({'textbox': True, 'borderless': False}, 'textbox_boundary_visibility_not_explicit'),
    ({'hidden': True}, 'hidden_source_object'),
    ({'extent': 'cx="0" cy="1000"'}, 'nonpositive_extent'),
    ({'offset': 'x="-100" y="500"'}, 'outside_slide_or_clipped'),
])
def test_unsupported_source_is_masked_without_silent_coordinate_repair(tmp_path, settings, reason):
    obj = object_target(fixture_request(tmp_path, **settings))
    assert reason in obj['mask_reasons']
    assert obj['bbox_xyxy_pixels'] is None
    assert not any(obj['supervision_mask'].values())


@pytest.mark.parametrize('option', ['duplicate_id', 'duplicate_name'])
def test_duplicate_or_ambiguous_source_identity_fails_closed(tmp_path, option):
    with pytest.raises(t.TargetExtractionError, match='duplicate|ambiguous'):
        t.extract_request(fixture_request(tmp_path, **{option: True}))


def test_duplicate_role_assignment_fails_closed(tmp_path):
    request = fixture_request(tmp_path)
    edit_roles(request, lambda roles: roles['assignments'].append(deepcopy(roles['assignments'][0])))
    with pytest.raises(t.TargetExtractionError, match='duplicate'):
        t.extract_request(request)


def test_role_cannot_be_changed_to_node_against_annotation_membership(tmp_path):
    request = fixture_request(tmp_path, role='excluded')
    edit_roles(request, lambda roles: roles['assignments'][0].__setitem__('semantic_role', 'node'))
    with pytest.raises(t.TargetExtractionError, match='contradicts'):
        t.extract_request(request)


def test_unverified_role_review_fails_closed(tmp_path):
    request = fixture_request(tmp_path)
    edit_roles(request, lambda roles: roles['review'].__setitem__('status', 'inferred_from_ellipse'))
    with pytest.raises(t.TargetExtractionError, match='unverified'):
        t.extract_request(request)


def test_unknown_visibility_disables_supervision(tmp_path):
    request = fixture_request(tmp_path)
    edit_roles(request, lambda roles: roles['assignments'][0].__setitem__('visibility', 'unknown'))
    obj = object_target(request)
    assert 'visibility_not_verified' in obj['mask_reasons']
    assert not any(obj['supervision_mask'].values())


def test_annotation_sha_tampering_is_rejected(tmp_path):
    request = fixture_request(tmp_path)
    (tmp_path / 'source.json').write_text('{}')
    with pytest.raises(t.TargetExtractionError, match='SHA mismatch'):
        t.extract_request(request)


def test_nonfinite_xml_transform_is_not_repaired(tmp_path):
    with pytest.raises(t.TargetExtractionError, match='invalid XML integer'):
        t.extract_request(fixture_request(tmp_path, offset='x="NaN" y="500"'))


def test_cropped_render_is_not_assumed_full_slide(tmp_path):
    request = fixture_request(tmp_path)
    request['cases'][0]['render']['full_slide'] = False
    with pytest.raises(t.TargetExtractionError, match='render mapping'):
        t.extract_request(request)


def test_slide_part_must_match_actual_presentation_relationship(tmp_path):
    with pytest.raises(t.TargetExtractionError, match='explicit first slide'):
        t.extract_request(fixture_request(tmp_path, slide_target='slides/slide2.xml'))


def test_duplicate_request_sample_fails_closed(tmp_path):
    request = fixture_request(tmp_path)
    request['cases'].append(deepcopy(request['cases'][0]))
    with pytest.raises(t.TargetExtractionError, match='duplicate'):
        t.extract_request(request)


def test_missing_role_metadata_fails_closed(tmp_path):
    request = fixture_request(tmp_path)
    del request['cases'][0]['role_annotations']
    with pytest.raises(t.TargetExtractionError, match='missing'):
        t.extract_request(request)


def test_unknown_shape_tree_content_cannot_be_silently_skipped(tmp_path):
    with pytest.raises(t.TargetExtractionError, match='unsupported shape-tree'):
        t.extract_request(fixture_request(tmp_path, extra_tree_element='<p:unknownShape/>'))


def test_output_is_offline_only_and_never_overwrites(tmp_path):
    request = fixture_request(tmp_path)
    path = tmp_path / 'request.json'
    path.write_text(json.dumps(request))
    output = tmp_path / 'targets.json'
    result = t.extract_to_file(path, output)
    assert result['inference_input_allowed'] is False
    assert result['training_performed'] is False
    assert result['research_only'] is True
    assert result['cases'][0]['render_transform']['renderer_version_status'] == 'not_recorded'
    with pytest.raises(FileExistsError):
        t.extract_to_file(path, output)
