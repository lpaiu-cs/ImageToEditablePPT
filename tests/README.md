# Test Layout

테스트는 아래 관점으로 유지한다.

## Purge / Boundary

- `tests/test_legacy_purge.py`
- `tests/test_v3_architecture.py`

규칙:

- 삭제된 legacy 구현이 workspace에 다시 들어오지 않게 막는다.
- `v3/*`와 preserve-eval이 purge된 root runtime에 직접 기대지 않게 검증한다.

## Preserve Eval / Benchmark

- `tests/test_benchmark_report.py`

규칙:

- benchmark / diagnostics artifact reader 계약을 보존한다.
- methodology 변경 없이 rollup 회귀 방지에 집중한다.

## v3 Contract / Architecture

- `tests/test_v3_phase1.py`
- `tests/test_v3_phase2.py`
- `tests/test_v3_phase3.py`
- `tests/test_v3_phase4.py`
- `tests/test_v3_architecture.py`

규칙:

- `test_v3_*.py`는 v3 전용 테스트에 사용한다.
- 계약, 경계, branch orchestration, family skeleton, debug artifact visibility를 우선 검증한다.
- legacy heuristic 품질 검증은 여기로 가져오지 않는다.
