# Test Layout

테스트는 아래 관점으로 유지한다.

## Legacy Regression

- `tests/test_pipeline.py`
- `tests/synthetic.py`

규칙:

- legacy 코어 동작 회귀를 막는 테스트다.
- v3 기능 확장은 이 파일들에 섞지 않는다.

## Preserve Eval / Benchmark

- `tests/test_stage_refactor.py`
- `tests/test_benchmark_report.py`

규칙:

- benchmark / diagnostics / stage artifact 계약을 보존한다.
- methodology 변경 없이 회귀 방지에 집중한다.

## v3 Contract / Architecture

- `tests/test_v3_phase1.py`
- `tests/test_v3_architecture.py`

규칙:

- `test_v3_*.py`는 v3 전용 테스트에 사용한다.
- 계약, 경계, placeholder orchestration, architecture rules를 우선 검증한다.
- legacy heuristic 품질 검증은 여기로 가져오지 않는다.
