# legacy_v2 Namespace

`legacy_v2/`는 현재 root 아래 흩어져 있는 v2 변환 코어의 장기적 수용 위치다.

이번 phase의 원칙:

- 이 namespace는 **경계 확정**이 목적이다.
- 이번 phase에서 모든 legacy 모듈을 즉시 물리 이동하지 않는다.
- 기존 public import path와 테스트를 깨지 않는 것이 우선이다.
- 새 기능은 여기에 추가하지 않는다.

## Responsibility

- legacy CV / heuristic conversion core의 장기 보관 위치
- compatibility shim의 종착점
- preserve_eval과 분리된 legacy runtime 구현 위치

## Planned Long-Term Residents

- `pipeline.py`
- `config.py`
- `preprocess.py`
- `components.py`
- `detector.py`
- `fitter.py`
- `geometry.py`
- `guides.py`
- `objects.py`
- `selection.py`
- `graph.py`
- `emit.py`
- `exporter.py`
- `fallback.py`
- `filtering.py`
- `gating.py`
- `repair.py`
- `router.py`
- `style.py`
- `text.py`
- `vlm_parser.py`
- `reconstructors/*`
- legacy `ir.py`의 v2-specific payload

## Compatibility Shim Strategy

- 기존 import path는 당분간 유지한다.
- 이동 시 root 경로에는 얇은 wrapper 또는 re-export shim만 남긴다.
- shim에는 새 로직을 추가하지 않는다.
- 새 기능은 `src/image_to_editable_ppt/v3/` 아래에만 추가한다.

## Explicit Non-Goals

- v3가 이 namespace를 직접 import하게 만들지 않는다.
- "쓸 만해 보이는" legacy heuristic을 shared로 복사하지 않는다.
- preserve_eval tooling을 legacy runtime과 섞어 놓지 않는다.
