from dataclasses import replace

import numpy as np

from image_to_editable_ppt.research.predicted_owners import prediction_scene
from image_to_editable_ppt.research.text_only_ocr import recover_text_only


def scene():
    return prediction_scene(dict(image_size=[100, 100], objects=[
        dict(id='a', role='node', semantic_kind='label_anchor', bbox_xyxy=[10.2, 10.2, 25.1, 20.1], confidence=.99),
        dict(id='b', role='node', semantic_kind='box', bbox_xyxy=[50, 50, 80, 80], confidence=.9)]))


def response(text='CP', score=.99):
    return [[[[4, 4], [40, 4], [40, 20], [4, 20]], text, score]], None


def test_one_transform_preserves_everything_except_text_only_label():
    original = scene()
    calls = []
    def engine(crop):
        calls.append(crop.shape)
        return response()
    updated, audit = recover_text_only(original, np.full((100, 100, 3), 255, np.uint8), engine)
    assert updated.shapes[0] == replace(original.shapes[0], label='CP')
    assert updated.shapes[1] is original.shapes[1]
    assert updated.connectors == original.connectors
    assert audit['a']['crop_xyxy'] == [8, 8, 28, 23]
    assert calls == [(141, 156, 3), (212, 234, 3)]


def test_disagreement_is_blank_without_lexical_repair():
    replies = iter([response('CP'), response('OP')])
    result, audit = recover_text_only(scene(), np.zeros((100, 100, 3), np.uint8), lambda _: next(replies))
    assert result.shapes[0].label is None
    assert audit['a']['reason'] == 'scale_disagreement'


def test_low_confidence_and_unavailable_backend_abstain():
    rgb = np.zeros((100, 100, 3), np.uint8)
    for engine, reason in [(lambda _: response(score=.89), 'low_confidence'), (None, 'backend_unavailable')]:
        result, audit = recover_text_only(scene(), rgb, engine)
        assert result.shapes[0].label is None and audit['a']['reason'] == reason
