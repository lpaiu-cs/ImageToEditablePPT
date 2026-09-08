import pytest
from image_to_editable_ppt.research.owned_text_consensus import select_label,balanced_prefix


def audit(label):
    return dict(accepted=[dict(text=t) for t in label.split('\n')] if label else [])


@pytest.mark.parametrize('db,row,expected',[
    ('Title','Title\nBody','Title\nBody'),('Title\nBody','Title','Title\nBody'),
    ('Title','Different',None),(None,'Title','Title'),('Title',None,'Title'),
    ('T',None,None),(None,'T',None),('T','T','T'),(None,None,None),
    ('x=1+2','X=1+2',None),('Parent Header','ParentHeader',None)])
def test_complete_prefix_and_conflict_contract(db,row,expected):
    label,info=select_label(db,audit(db),row,audit(row))
    assert label==expected


@pytest.mark.parametrize('text,expected',[
    ('Title\n(incomplete,','Title'),('Title\n(full body)','Title\n(full body)'),
    ('Title\n[first\nsecond]','Title\n[first\nsecond]'),('<EOS>','<EOS>'),
    ('Title\nbad closing)','Title'),('x=f(a',None)])
def test_incomplete_explanation_is_not_exported_as_a_finished_label(text,expected):
    label,info=select_label(text,audit(text),None,audit(None))
    assert label==expected
    assert info['observed_accepted']==audit(text)['accepted']
