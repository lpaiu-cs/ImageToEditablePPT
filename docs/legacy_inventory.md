# Legacy Inventory

최종 업데이트: 2026-03-25

이 문서는 `plan.md`의 purge 결과와 `Phase 4` tombstone 재검토 상태를 반영한 inventory다.

분류 태그:

- `legacy_core`: v2 변환 구현이었고 이번 단계에서 workspace에서 제거됨
- `preserve_eval`: benchmark / validation / diagnostics / GT artifact reader로 유지
- `shared_candidate`: symbol-level 검토 끝에 실제 shared로 추출된 최소 primitive
- `defer`: 이후 adapter나 emit phase에서 다시 판단

## 1. Public Surface / Tombstones

| Path | Category | Note |
| --- | --- | --- |
| `src/image_to_editable_ppt/__init__.py` | `defer` | root package는 v3-first surface로 유지 |
| `src/image_to_editable_ppt/__main__.py` | `defer` | 기존 CLI 진입점 이름은 남기되 내부는 tombstone CLI로 연결 |
| `src/image_to_editable_ppt/cli.py` | `defer` | Phase 4 재검토 후 유지. `__main__`/module entrypoint 안정성 때문에 tombstone으로 남김 |
| `src/image_to_editable_ppt/validation.py` | `preserve_eval`, `defer` | Phase 4 재검토 후 유지. preserve-eval import surface를 tombstone으로 고정 |

## 2. Purged Legacy Core

아래 구현은 workspace에서 제거됐다. 재사용하지 않고 git history에만 남긴다.

| Path | Category | Note |
| --- | --- | --- |
| `src/image_to_editable_ppt/config.py` | `legacy_core` | removed |
| `src/image_to_editable_ppt/pipeline.py` | `legacy_core` | removed |
| `src/image_to_editable_ppt/preprocess.py` | `legacy_core` | removed |
| `src/image_to_editable_ppt/components.py` | `legacy_core` | removed |
| `src/image_to_editable_ppt/detector.py` | `legacy_core` | removed |
| `src/image_to_editable_ppt/fitter.py` | `legacy_core` | removed |
| `src/image_to_editable_ppt/geometry.py` | `legacy_core` | removed after primitive extraction |
| `src/image_to_editable_ppt/guides.py` | `legacy_core` | removed |
| `src/image_to_editable_ppt/objects.py` | `legacy_core` | removed |
| `src/image_to_editable_ppt/selection.py` | `legacy_core` | removed |
| `src/image_to_editable_ppt/graph.py` | `legacy_core` | removed |
| `src/image_to_editable_ppt/emit.py` | `legacy_core` | removed |
| `src/image_to_editable_ppt/exporter.py` | `legacy_core` | removed |
| `src/image_to_editable_ppt/fallback.py` | `legacy_core` | removed |
| `src/image_to_editable_ppt/filtering.py` | `legacy_core` | removed |
| `src/image_to_editable_ppt/gating.py` | `legacy_core` | removed |
| `src/image_to_editable_ppt/repair.py` | `legacy_core` | removed |
| `src/image_to_editable_ppt/router.py` | `legacy_core` | removed |
| `src/image_to_editable_ppt/style.py` | `legacy_core` | removed |
| `src/image_to_editable_ppt/text.py` | `legacy_core` | removed |
| `src/image_to_editable_ppt/vlm_parser.py` | `legacy_core` | removed |
| `src/image_to_editable_ppt/ir.py` | `legacy_core` | removed after symbol-level primitive extraction |
| `src/image_to_editable_ppt/svg_exporter.py` | `legacy_core` | removed |
| `src/image_to_editable_ppt/reconstructors/*` | `legacy_core` | removed |

## 3. Preserve Eval / Diagnostics

| Path | Category | Note |
| --- | --- | --- |
| `src/image_to_editable_ppt/eval_debug.py` | `preserve_eval` | GT/oracle/attrition analysis 유지 |
| `src/image_to_editable_ppt/benchmark_report.py` | `preserve_eval` | summary/rollup reader 유지 |
| `src/image_to_editable_ppt/diagnostics.py` | `preserve_eval` | stage artifact recorder 유지 |
| `src/image_to_editable_ppt/source_attribution.py` | `preserve_eval` | source bucket attribution 유지 |
| `src/image_to_editable_ppt/schema.py` | `preserve_eval` | artifact schema 유지. shared로 승격하지 않음 |
| `tools/benchmark_report.py` | `preserve_eval` | benchmark report CLI 유지 |
| `workbench/` | `preserve_eval` | 유지 |
| `workbench2.0/` | `preserve_eval` | 유지 |
| `workbench2.0-geometry-only/` | `preserve_eval` | 유지 |
| `workbench2.0-no-motifs/` | `preserve_eval` | 유지 |

정리 원칙:

- preserve-eval은 deleted legacy runtime을 import-time에 참조하지 않는다.
- old conversion 실행 경로가 필요한 부분은 현재 tombstone 또는 future adapter 요구사항으로 남긴다.
- benchmark report처럼 artifact만 읽는 코드는 그대로 유지한다.

## 4. Shared Primitive Status

이번 단계에서 실제 shared로 추출한 것은 아래뿐이다.

| Symbol | Path | Category | Note |
| --- | --- | --- | --- |
| `BBox` | `src/image_to_editable_ppt/shared/geometry.py` | `shared_candidate` | 순수 bbox primitive |
| `Point` | `src/image_to_editable_ppt/shared/geometry.py` | `shared_candidate` | 순수 point primitive |
| `ImageSize` | `src/image_to_editable_ppt/shared/geometry.py` | `shared_candidate` | 순수 image size primitive |

shared로 올리지 않은 것:

- geometry scoring
- object hypothesis
- selection heuristic
- fallback logic
- parser / reconstructor
- legacy stage semantics

## 5. Reserved v3 / Adapter Namespaces

| Path | Category | Note |
| --- | --- | --- |
| `src/image_to_editable_ppt/v3/*` | `defer` | active architecture |
| `src/image_to_editable_ppt/legacy_v2/` | `defer` | documentation-only historical namespace |
| `src/image_to_editable_ppt/shared/` | `defer` | minimal primitive namespace |
| `src/image_to_editable_ppt/eval_runtime/` | `defer` | future adapter namespace |

## 6. Test Inventory

| Path | Category | Note |
| --- | --- | --- |
| `tests/test_legacy_purge.py` | `defer` | purge / preserve-eval boundary 검증 |
| `tests/test_benchmark_report.py` | `preserve_eval` | benchmark rollup regression |
| `tests/test_v3_phase1.py` | `defer` | v3 base contract |
| `tests/test_v3_phase2.py` | `defer` | text/raster/residual contract |
| `tests/test_v3_phase3.py` | `defer` | family registry / detector / parser skeleton |
| `tests/test_v3_phase4.py` | `defer` | node/container 분리, connector evidence, debug runner 검증 |
| `tests/test_v3_architecture.py` | `defer` | v3 import boundary |

퇴역된 테스트:

- `tests/test_pipeline.py`
- `tests/test_stage_refactor.py`
- `tests/synthetic.py`

## 7. Immediate Migration Guidance

- v2 구현은 workspace에서 다시 살리지 않는다.
- 새 구조 작업은 `src/image_to_editable_ppt/v3/` 아래에만 구현한다.
- preserve-eval과 v3를 연결해야 할 때만 future adapter를 `eval_runtime/`에 추가한다.
- 애매한 helper는 shared가 아니라 v3 내부 또는 preserve-eval 내부에 둔다.
