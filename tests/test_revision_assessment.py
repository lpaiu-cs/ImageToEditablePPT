from copy import deepcopy
import pytest
from image_to_editable_ppt.research.revision_assessment import assess_revision


def scene():
    return dict(image_size=dict(width=640,height=360),coordinate_space='image_space',
        shapes=[dict(id=k,owner_kind='node',shape_kind='box',label=k,confidence=.9,
                     bbox=dict(x0=x,y0=30,x1=x+30,y1=60)) for k,x in [('a',20),('b',100),('c',180)]],
        texts=[],residuals=[],connectors=[dict(id='e',source_owner_id='a',target_owner_id='b',
            kind='line',arrowhead_start=False,arrowhead_end=True,
            path_points=[dict(x=50,y=45),dict(x=100,y=45)])])


def test_identity():
    result = assess_revision(scene(),scene())
    assert not any(result[k] for k in ('structural_changes','geometry_changes','metadata_changes'))
    assert 'pass' not in result


@pytest.mark.parametrize('dx',[1,20])
def test_translation_geometry_not_structure(dx):
    before, after = scene(),scene()
    for s in after['shapes']:
        for k in ('x0','x1'): s['bbox'][k] += dx
    for p in after['connectors'][0]['path_points']: p['x'] += dx
    result = assess_revision(before,after)
    assert not result['structural_changes'] and not result['metadata_changes']
    assert len(result['geometry_changes']) == 4
    assert result['geometry_changes'][-1]['max_endpoint_displacement_px'] == dx


def test_same_endpoints_different_inner_path():
    after = scene()
    after['connectors'][0]['path_points'].insert(1,dict(x=75,y=50))
    result = assess_revision(scene(),after)
    assert not result['structural_changes']
    assert len(result['geometry_changes']) == 1
    assert result['geometry_changes'][0]['max_endpoint_displacement_px'] == 0


@pytest.mark.parametrize('change',['target','direction','remove_edge','remove_node','text','kind','standalone_text','residual'])
def test_content_and_structure_even_without_geometry_change(change):
    before, after = scene(),scene()
    if change == 'target': after['connectors'][0]['target_owner_id'] = 'c'
    elif change == 'direction': after['connectors'][0].update(arrowhead_start=True,arrowhead_end=False)
    elif change == 'remove_edge': after['connectors'] = []
    elif change == 'remove_node': after['shapes'].pop()
    elif change == 'text': after['shapes'][0]['label'] += '.'
    elif change == 'kind': after['shapes'][0]['shape_kind'] = 'ellipse'
    elif change == 'standalone_text':
        before['texts'] = [dict(id='t',text='CP',bbox=dict(x0=1,y0=1,x1=10,y1=10))]
        after['texts'] = deepcopy(before['texts']); after['texts'][0]['text'] = 'CP.'
    elif change == 'residual': after['residuals'] = [dict(id='r',kind='unknown',bbox=dict(x0=1,y0=1,x1=5,y1=5))]
    result = assess_revision(before,after)
    assert len(result['structural_changes']) == 1 and not result['geometry_changes']


def test_confidence_is_not_quality_verdict():
    after = scene();after['shapes'][0]['confidence'] = .1
    result = assess_revision(scene(),after)
    assert len(result['metadata_changes']) == 1 and not result['structural_changes']


@pytest.mark.parametrize('mode',['duplicate','nan','size','coordinate_space'])
def test_invalid_or_different_coordinates(mode):
    after = scene()
    if mode == 'duplicate': after['shapes'].append(deepcopy(after['shapes'][0]))
    if mode == 'nan': after['shapes'][0]['bbox']['x0'] = float('nan')
    if mode == 'size': after['image_size']['width'] += 1
    if mode == 'coordinate_space': after['coordinate_space'] = 'different'
    with pytest.raises(ValueError): assess_revision(scene(),after)
