"""현행 오방향의 특성화와 strict xfail. 제품 수정 시 fixture 판정도 함께 재검토한다."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from image_to_editable_ppt.ml.visual_connectors import _arrow_direction

FIXTURE = json.loads(
    (Path(__file__).parent / 'fixtures/visual_arrow_direction_known_failure_v1.json').read_text(encoding='utf-8')
)
CASES = FIXTURE['cases']


def _mask(widths: list[int]) -> np.ndarray:
    """Width-only reconstruction; no image, annotation, checkpoint or PPT is read."""
    mask = np.zeros((len(widths), FIXTURE['mask_width']), dtype=bool)
    center = FIXTURE['mask_width'] // 2
    for row, width in enumerate(widths):
        mask[row, center - width // 2 : center - width // 2 + width] = True
    return mask


def _case_mask(case: dict) -> np.ndarray:
    return _mask([width for width, count in case['width_profile_rle'] for _ in range(count)])


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['id'])
def test_characterizes_current_reverse_direction_failure(case):
    # This assertion documents the bug. It must be revised with the eventual fix,
    # not treated as a requirement that arrows should continue pointing backward.
    result = _arrow_direction(_case_mask(case), axis=FIXTURE['axis'])
    assert result == case['observed_current_direction'] == -1
    assert result != case['observed_image_direction']


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['id'])
@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason='Known v1 failure: source-boundary shadow/closing width drop is misread as a reverse arrowhead',
)
def test_repaired_direction_must_be_forward_or_conservatively_undirected(case):
    # A future XPASS requires explicit review/removal of this known-failure mark.
    assert _arrow_direction(_case_mask(case), axis=FIXTURE['axis']) in case['acceptable_future_directions']


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['id'])
def test_source_boundary_removal_changes_the_failure_as_observed(case):
    # A diagnostic ablation, not a proposed universal four-row crop policy.
    trimmed = _case_mask(case)[4:]
    assert _arrow_direction(trimmed, axis=FIXTURE['axis']) == case['observed_after_removing_first_four_rows']


def test_plain_shaft_control_remains_undirected():
    assert _arrow_direction(_mask([3] * 50), axis='vertical') == 0


@pytest.mark.parametrize('reverse', [False, True])
def test_clean_arrow_control_retains_both_directions(reverse):
    profile = [3] * 30 + [11, 9, 7, 5, 3, 1]
    if reverse:
        profile.reverse()
    assert _arrow_direction(_mask(profile), axis='vertical') == (-1 if reverse else 1)
