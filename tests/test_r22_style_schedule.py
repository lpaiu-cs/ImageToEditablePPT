"""Keep the geometry RNG identical to R19 despite independent style sampling."""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from r22_native_style_transfer import schedule


def test_style_does_not_change_geometry_sampling():
    expected = random.Random(1901)
    plan = list(schedule(288))
    assert [i for batch in plan for i, _ in batch] == [expected.randrange(288) for _ in range(7200)]
    assert plan == list(schedule(288))
    assert {style for batch in plan for _, style in batch} == {0, 1}
