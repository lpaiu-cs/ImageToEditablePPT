"""R7b: conservative blockers and ownership-isolated interior color."""
from dataclasses import replace
import cv2
import numpy as np
import pytest
from tests.test_region_r7 import fixture
from image_to_editable_ppt.research.accepted_owners import accept_oracle
from image_to_editable_ppt.research.ownership_guards import observe_guarded, owned_styles, neutralize_boxes


def test_direct_connection_survives_guards():
    rgb, candidate, data = fixture()
    accepted, _ = accept_oracle(candidate, data)
    final, audit, _ = observe_guarded(accepted, rgb, data['scope'], data, ocr=False)
    assert [(c.source_owner_id, c.target_owner_id, c.arrowhead_end) for c in final.connectors] == [('a', 'b', True)]
    assert not audit['rejected_boundary']


def test_external_branch_prevents_inferred_local_pair():
    rgb, candidate, data = fixture()
    cv2.line(rgb, (200, 0), (200, 110), (0, 0, 0), 2)
    accepted, _ = accept_oracle(candidate, data)
    final, audit, blocked = observe_guarded(accepted, rgb, data['scope'], data, ocr=False)
    assert blocked.connectors
    assert not final.connectors and audit['rejected_boundary']


def test_unsupported_outline_is_not_a_through_route():
    rgb, candidate, data = fixture()
    data['objects'].append(dict(id='compound', role='node', geometry='cylinder', closed=True,
                               parent=None, bbox=[180, 80, 220, 140], label='not emitted'))
    accepted, _ = accept_oracle(candidate, data)
    final, audit, _ = observe_guarded(accepted, rgb, data['scope'], data, ocr=False)
    assert len(final.shapes) == 2 and not final.connectors
    assert audit['blockers']


def test_white_closed_children_occlude_colored_parent_without_contamination():
    rgb, candidate, data = fixture()
    rgb[:] = (240, 190, 190)
    rgb[60:160, 30:150] = (245, 245, 245)
    rgb[60:160, 250:370] = (255, 255, 255)
    data['objects'].append(dict(id='panel', role='container', bbox=[10, 10, 390, 200],
                                parent=None, geometry='box', closed=True))
    for o in data['objects'][:2]: o['parent'] = 'panel'
    accepted, _ = accept_oracle(candidate, data, exact_geometry=True)
    styles, _ = owned_styles(accepted, rgb)
    assert styles['panel'].fill == (240, 190, 190)
    assert styles['a'].fill == (245, 245, 245)
    assert styles['b'].fill == (255, 255, 255)


def test_illustration_pixels_cannot_define_owner_fill():
    rgb, candidate, data = fixture()
    rgb[80:140, 50:130] = (0, 0, 0)
    data['objects'].append(dict(id='illustration', role='nonstructural', parent='a', bbox=[50, 80, 130, 140]))
    accepted, _ = accept_oracle(candidate, data)
    styles, _ = owned_styles(accepted, rgb)
    assert styles['a'].fill == (255, 255, 255)


def test_mixed_uncertain_interior_abstains_from_fill():
    rgb, candidate, data = fixture()
    rgb[60:160, 30:90] = (220, 30, 30)
    rgb[60:160, 90:150] = (30, 30, 220)
    accepted, _ = accept_oracle(candidate, data)
    styles, audit = owned_styles(accepted, rgb)
    assert styles['a'].fill is None
    assert audit['a']['reason'] == 'uncertain_fill_abstention'


@pytest.mark.parametrize('background', [0, 255])
def test_mask_uses_exterior_polarity_and_preserves_source(background):
    rgb = np.full((80, 100, 3), background, np.uint8)
    rgb[20:60, 30:70] = 255-background
    clean = neutralize_boxes(rgb, [(30, 20, 70, 60)])
    assert np.all(clean == background)
    assert np.any(rgb != background)


def test_guards_require_explicit_accepted_scene():
    rgb, candidate, data = fixture()
    with pytest.raises(TypeError): owned_styles(candidate, rgb)
    with pytest.raises(TypeError): observe_guarded(candidate, rgb, data['scope'], data)
