"""Research-only accepted ownership and source-frame invariants."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import importlib
import sys

import cv2
import numpy as np
import pytest

from image_to_editable_ppt.research.accepted_owners import (
    AcceptedScene, CandidateScene, accept_oracle, observe_accepted, proposals,
    validate_annotation, match,
)
from image_to_editable_ppt.v3.core.enums import NodeKind, PortOwnerKind
from image_to_editable_ppt.v3.core.types import BBox, ImageSize
from image_to_editable_ppt.v3.emit.models import EmitScene, EmitShapePrimitive


def fixture():
    rgb = np.full((220, 400, 3), 255, dtype=np.uint8)
    shapes = []
    objects = []
    for sid, box in [('a', [30, 60, 150, 160]), ('b', [250, 60, 370, 160])]:
        cv2.rectangle(rgb, tuple(box[:2]), tuple(box[2:]), (0, 0, 0), 2)
        shapes.append(EmitShapePrimitive(sid, PortOwnerKind.NODE, NodeKind.BOX, BBox(*box), 1.))
        objects.append(dict(id=sid, role='node', bbox=box, parent=None, geometry='box', closed=True, label='SECRET'))
    cv2.arrowedLine(rgb, (150, 110), (250, 110), (0, 0, 0), 2, tipLength=.15)
    candidate = CandidateScene(EmitScene(ImageSize(400, 220), shapes=tuple(shapes)), ((0, 0, 400, 220),))
    data = dict(schema='r7_source_roles_v1', population='consumed_development',
                source_size=[400, 220], source_sha256=hashlib.sha256(b'fixture').hexdigest(),
                coordinate_space='original_pixels',
                view_to_source=dict(scale=[1, 1], offset=[0, 0], view_size=[400, 220]),
                scope=[0, 0, 400, 220], objects=objects,
                relations=[dict(id='ab', source='a', target='b', directed=True, style='solid')])
    return rgb, candidate, data


def test_source_binding_and_identity_view_are_required():
    rgb, _, data = fixture()
    assert validate_annotation(data, rgb, b'fixture') is data
    with pytest.raises(ValueError, match='binding'):
        validate_annotation(data, rgb, b'other')
    data['view_to_source']['scale'] = [2, 2]
    with pytest.raises(ValueError, match='transform'):
        validate_annotation(data, rgb, b'fixture')


@pytest.mark.parametrize('box', [[-1, 0, 5, 6], [0, 0, 401, 220], [2, 2, 1, 8],
                               [0, 0, float('nan'), 8], [0, 0, float('inf'), 8], [False, 0, 5, 6]])
def test_invalid_original_boxes_fail(box):
    rgb, _, data = fixture()
    data['objects'][0]['bbox'] = box
    with pytest.raises(ValueError):
        validate_annotation(data, rgb, b'fixture')


@pytest.mark.parametrize('mutation', ['duplicate', 'unknown_parent', 'cycle', 'outside_parent',
                                     'unknown_role', 'open_owner', 'dangling_edge', 'wrong_population'])
def test_invalid_ownership_annotation_fails(mutation):
    rgb, _, data = fixture()
    a, b = data['objects']
    if mutation == 'duplicate': b['id'] = 'a'
    if mutation == 'unknown_parent': a['parent'] = 'missing'
    if mutation == 'cycle': a['parent'] = 'a'
    if mutation == 'outside_parent': a['parent'] = 'b'
    if mutation == 'unknown_role': a['role'] = 'guess'
    if mutation == 'open_owner': a['closed'] = False
    if mutation == 'dangling_edge': data['relations'][0]['target'] = 'missing'
    if mutation == 'wrong_population': data['population'] = 'holdout'
    with pytest.raises(ValueError):
        validate_annotation(data, rgb, b'fixture')


def test_candidates_cannot_reach_ocr_or_masking():
    rgb, candidate, _ = fixture()
    with pytest.raises(TypeError, match='AcceptedScene'):
        observe_accepted(candidate, rgb, [0, 0, 400, 220])
    labeled = replace(candidate.scene, shapes=(replace(candidate.scene.shapes[0], label='bad'),))
    with pytest.raises(ValueError, match='labels'):
        CandidateScene(labeled, ())


def test_oracle_never_injects_truth_text_or_relations():
    rgb, candidate, data = fixture()
    accepted, _ = accept_oracle(candidate, data)
    assert all(s.label is None for s in accepted.scene.shapes)
    # Erase the observed arrow but retain the annotation relation. No invention.
    blank = rgb.copy()
    blank[90:130, 153:248] = 255
    scene, _ = observe_accepted(accepted, blank, data['scope'], ocr=False)
    assert not scene.connectors
    assert not any(s.label for s in scene.shapes)
    scene, _ = observe_accepted(accepted, rgb, data['scope'], ocr=False)
    assert [(c.source_owner_id, c.target_owner_id, c.arrowhead_end) for c in scene.connectors] == [('a', 'b', True)]


def test_match_is_one_to_one_and_cannot_match_partial_caps():
    _, candidate, data = fixture()
    extra = replace(candidate.scene.shapes[0], id='duplicate')
    candidate = CandidateScene(replace(candidate.scene, shapes=(*candidate.scene.shapes, extra)), ())
    assert len(match(candidate, data)) == 2
    cap = replace(extra, bbox=BBox(30, 60, 150, 80))
    assert not match(CandidateScene(replace(candidate.scene, shapes=(cap,)), ()), data)


def test_unknown_and_unsupported_do_not_become_native_owners():
    _, candidate, data = fixture()
    data['objects'][0]['geometry'] = 'cylinder'
    data['objects'].append(dict(id='excluded', role='unknown', bbox=[245, 55, 375, 165], parent=None))
    accepted, audit = accept_oracle(candidate, data, exact_geometry=True)
    assert not accepted.scene.shapes
    assert {r['reason'] for r in audit['rejected']} == {'unsupported_owner_geometry', 'excluded_region'}


def test_valid_container_parent_is_retained_without_label_injection():
    _, candidate, data = fixture()
    data['objects'].append(dict(id='panel', role='container', bbox=[10, 10, 390, 200],
                                parent=None, geometry='box', closed=True))
    data['objects'][0]['parent'] = 'panel'
    accepted, _ = accept_oracle(candidate, data, exact_geometry=True)
    assert dict(accepted.parents)['a'] == 'panel'
    assert not any(s.label for s in accepted.scene.shapes)
    with pytest.raises(ValueError, match='parent'):
        replace(accepted, parents=(('a', 'a'), ('b', None), ('panel', None)))


def test_fixed_local_windows_preserve_source_frame_without_truth_input():
    rgb = np.full((600, 900, 3), 255, np.uint8)
    cv2.rectangle(rgb, (100, 100), (220, 210), (0, 0, 0), 2)
    result = proposals(rgb, [50, 50, 850, 550], local=True)
    assert result.windows == ((50, 50, 850, 550), (50, 50, 562, 550), (338, 50, 850, 550))
    assert any(abs(s.bbox.x0-100) <= 3 for s in result.scene.shapes)
    assert all(50 <= s.bbox.x0 < s.bbox.x1 <= 850 for s in result.scene.shapes)


def test_excluded_icon_is_removed_before_ocr(monkeypatch):
    rgb, candidate, data = fixture()
    rgb[80:100, 70:90] = 0
    data['objects'].append(dict(id='icon', role='nonstructural', bbox=[70, 80, 90, 100], parent='a'))
    accepted, _ = accept_oracle(candidate, data)
    module = importlib.import_module('image_to_editable_ppt.research.accepted_owners')
    def check(scene, image, **kwargs):
        assert np.all(image[80:100, 70:90] == 255)
        return scene, {}
    monkeypatch.setattr(module, 'recover_labels', check)
    observe_accepted(accepted, rgb, data['scope'])
    assert np.all(rgb[80:100, 70:90] == 0)


def test_production_has_no_research_oracle_dependency():
    import subprocess
    code = "import sys; import image_to_editable_ppt.region.convert; assert 'image_to_editable_ppt.research.accepted_owners' not in sys.modules"
    subprocess.run([sys.executable, '-c', code], check=True)
