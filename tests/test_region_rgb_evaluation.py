import importlib
from pathlib import Path


def evaluator(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'tools'))
    return importlib.import_module('evaluate_region_rgb_baseline')


def test_role_and_kind_metrics_are_distinct(monkeypatch):
    m = evaluator(monkeypatch)
    bbox = dict(x0=0, y0=0, x1=50, y1=50)
    pred = [dict(id='p', owner_kind='node', shape_kind='box', bbox=bbox)]
    ref = [dict(id='g', owner_kind='node', kind='rounded_box', bbox=bbox)]
    assert m.match(pred, ref) == {'p': 'g'}
    assert m.match(pred, ref, exact_kind=True) == {}
    ref[0]['owner_kind'] = 'container'
    assert m.match(pred, ref) == {}


def test_duplicate_predictions_match_once(monkeypatch):
    m = evaluator(monkeypatch)
    bbox = dict(x0=0, y0=0, x1=50, y1=50)
    pred = [dict(id=str(i), owner_kind='node', shape_kind='box', bbox=bbox) for i in range(2)]
    ref = [dict(id='g', owner_kind='node', kind='box', bbox=bbox)]
    assert len(m.match(pred, ref)) == 1
    assert m.counts(1, 2, 1) == dict(tp=1, fp=1, fn=0, predictions=2, references=1)


def test_edge_direction_and_multiplicity_are_preserved(monkeypatch):
    m = evaluator(monkeypatch)
    assert m.signature('a', 'b', True, False) == m.signature('b', 'a', False, True)
    assert m.signature('a', 'b', False, False) == m.signature('b', 'a', False, False)
    assert m.signature('a', 'b', False, True) != m.signature('b', 'a', False, True)
    connector = dict(source_owner_id='a', target_owner_id='b', arrowhead_start=False, arrowhead_end=True)
    result = m.edges(dict(connectors=[connector, connector]), {'a': 'g1', 'b': 'g2'})
    assert sum(result.values()) == 2
