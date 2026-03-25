# Legacy Inventory

최종 업데이트: 2026-03-25

이 문서는 `plan.md`의 legacy cleanup / isolation phase를 구체화한 inventory다.

분류 태그:

- `legacy_core`: 기존 v2 변환 코어로 간주. 더 이상 기능 확장 대상이 아님.
- `preserve_eval`: benchmark / validation / diagnostics / GT 비교 흐름 보존 대상.
- `shared_candidate`: 매우 보수적으로 검토 가능한 순수 데이터 구조 또는 저수준 helper 후보.
- `defer`: 이번 단계에서 이동/재구성하지 않음. 필요 시 shim 또는 후속 phase에서 처리.

## 1. Public Surface / Compatibility

| Path | Category | Note |
| --- | --- | --- |
| `src/image_to_editable_ppt/__init__.py` | `defer` | 현재 public import surface. 이후 shim 계층이 되더라도 당장 깨지지 않게 유지. |
| `src/image_to_editable_ppt/__main__.py` | `defer` | CLI 진입 유지. 내부 재배선은 shim으로 처리. |
| `src/image_to_editable_ppt/cli.py` | `defer` | 기존 CLI entrypoint. 새 기능은 여기에 추가하지 않고 이후 명시적 v3 command를 고려. |

## 2. Legacy Core Modules

| Path | Category | Note |
| --- | --- | --- |
| `src/image_to_editable_ppt/config.py` | `legacy_core`, `defer` | v2 heuristic 튜닝 파라미터 집합. shared 이동 금지. |
| `src/image_to_editable_ppt/pipeline.py` | `legacy_core` | 기존 convert/build orchestration의 중심. |
| `src/image_to_editable_ppt/preprocess.py` | `legacy_core` | legacy 전처리 흐름에 묶임. |
| `src/image_to_editable_ppt/components.py` | `legacy_core` | legacy CV component 추출. |
| `src/image_to_editable_ppt/detector.py` | `legacy_core` | legacy semantic/object detection helper. |
| `src/image_to_editable_ppt/fitter.py` | `legacy_core` | legacy geometric fitting heuristic. |
| `src/image_to_editable_ppt/geometry.py` | `legacy_core` | legacy geometry candidate 생성/스코어링. |
| `src/image_to_editable_ppt/guides.py` | `legacy_core` | guide inference heuristic. |
| `src/image_to_editable_ppt/objects.py` | `legacy_core` | object hypothesis 조립. |
| `src/image_to_editable_ppt/selection.py` | `legacy_core` | selection/suppression heuristic. |
| `src/image_to_editable_ppt/graph.py` | `legacy_core` | authoring graph 조립. |
| `src/image_to_editable_ppt/emit.py` | `legacy_core` | legacy emission planning. |
| `src/image_to_editable_ppt/exporter.py` | `legacy_core`, `defer` | legacy `Element` 기반 PPTX export. |
| `src/image_to_editable_ppt/fallback.py` | `legacy_core` | fallback hypothesis logic. shared 이동 금지. |
| `src/image_to_editable_ppt/filtering.py` | `legacy_core` | residual filtering heuristic. |
| `src/image_to_editable_ppt/gating.py` | `legacy_core` | legacy gating rule 집합. |
| `src/image_to_editable_ppt/repair.py` | `legacy_core` | occlusion repair heuristic. |
| `src/image_to_editable_ppt/router.py` | `legacy_core` | legacy connector routing helper. |
| `src/image_to_editable_ppt/style.py` | `legacy_core` | legacy style extraction logic. |
| `src/image_to_editable_ppt/text.py` | `legacy_core` | OCR 및 text routing이 legacy stage semantics에 묶여 있음. |
| `src/image_to_editable_ppt/vlm_parser.py` | `legacy_core`, `defer` | 현재 semantic mode와 결합된 parser surface. v3와 직접 공유하지 않음. |
| `src/image_to_editable_ppt/reconstructors/__init__.py` | `legacy_core` | legacy reconstruction registry. |
| `src/image_to_editable_ppt/reconstructors/containers.py` | `legacy_core` | legacy container reconstruction. |
| `src/image_to_editable_ppt/reconstructors/connectors.py` | `legacy_core` | legacy connector reconstruction. |
| `src/image_to_editable_ppt/reconstructors/motifs.py` | `legacy_core` | motif heuristic. |
| `src/image_to_editable_ppt/reconstructors/raster_regions.py` | `legacy_core` | raster fallback heuristic. |
| `src/image_to_editable_ppt/reconstructors/textboxes.py` | `legacy_core` | text-box reconstruction heuristic. |

## 3. Legacy IR / Schema

| Path | Category | Note |
| --- | --- | --- |
| `src/image_to_editable_ppt/ir.py` | `legacy_core`, `shared_candidate`, `defer` | 모듈 전체는 legacy IR이지만 `BBox`, `Point` 같은 순수 primitive만 symbol-level 후보. `Element` 계열은 shared 금지. |
| `src/image_to_editable_ppt/schema.py` | `preserve_eval`, `defer` | stage artifact schema. legacy stage semantics에 강하게 결합되어 있어 shared 이동 금지. |

## 4. Preserve Eval / Diagnostics

| Path | Category | Note |
| --- | --- | --- |
| `src/image_to_editable_ppt/validation.py` | `preserve_eval` | validation 루프 보존. |
| `src/image_to_editable_ppt/eval_debug.py` | `preserve_eval` | stage attrition/failure taxonomy 보존. |
| `src/image_to_editable_ppt/benchmark_report.py` | `preserve_eval` | benchmark rollup 유지. |
| `src/image_to_editable_ppt/diagnostics.py` | `preserve_eval`, `defer` | diagnostics recorder. 현재 legacy와 밀결합되어 있어 이동 보류. |
| `src/image_to_editable_ppt/source_attribution.py` | `preserve_eval`, `defer` | source bucket attribution 유지. |
| `tools/benchmark_report.py` | `preserve_eval` | CLI benchmark utility 유지. |
| `workbench/` | `preserve_eval` | 수작업/benchmark workspace 자산 보존. |
| `workbench2.0/` | `preserve_eval` | diagnostics/summary 자산 보존. |
| `workbench2.0-geometry-only/` | `preserve_eval` | geometry-only benchmark 자산 보존. |
| `workbench2.0-no-motifs/` | `preserve_eval` | ablation benchmark 자산 보존. |

## 5. Reserved v3 / Adapter Namespaces

| Path | Category | Note |
| --- | --- | --- |
| `src/image_to_editable_ppt/v3/*` | `defer` | active new architecture. legacy cleanup의 목적은 여기를 legacy로부터 분리하는 것. |
| `src/image_to_editable_ppt/legacy_v2/` | `defer` | 장기적 v2 수용 위치. 이번 단계에서는 namespace 책임만 확정. |
| `src/image_to_editable_ppt/shared/` | `defer` | 엄격한 기준 통과 전까지 비워 둔다. |
| `src/image_to_editable_ppt/eval_runtime/` | `defer` | legacy/v3 비교 adapter 전용. |

## 6. Test Inventory

| Path | Category | Note |
| --- | --- | --- |
| `tests/test_pipeline.py` | `legacy_core` | legacy regression anchor. |
| `tests/test_stage_refactor.py` | `preserve_eval` | stage artifact/eval contract regression. |
| `tests/test_benchmark_report.py` | `preserve_eval` | benchmark summary regression. |
| `tests/test_v3_phase1.py` | `defer` | v3 contract test. |
| `tests/test_v3_architecture.py` | `defer` | v3 import 경계 강제 테스트. |
| `tests/synthetic.py` | `legacy_core`, `defer` | legacy regression fixture 생성기. |

## 7. Shared Candidate Status

현재 phase에서 실제 이동 승인된 것은 없다.

검토 가능 후보는 symbol-level로만 제한한다.

- `src/image_to_editable_ppt/ir.py::BBox`
- `src/image_to_editable_ppt/ir.py::Point`

보류 이유:

- 현재 `ir.py`는 `Element`, `FillStyle`, `StrokeStyle`, geometry payload 등 legacy emit 모델까지 함께 포함한다.
- 모듈 단위 이동은 v2 가정을 그대로 끌고 갈 가능성이 높다.
- v3는 이미 자체 primitive를 가지고 있으므로, 섣부른 통합보다 중복을 감수하는 편이 안전하다.

## 8. Immediate Migration Guidance

- v2 개선 작업은 기존 root 경로에 추가하지 않는다.
- 새 구조 작업은 `src/image_to_editable_ppt/v3/` 아래에만 구현한다.
- legacy와 v3 비교는 향후 `eval_runtime/` adapter를 통해 연결한다.
- 애매한 모듈은 shared가 아니라 legacy 또는 defer로 둔다.
