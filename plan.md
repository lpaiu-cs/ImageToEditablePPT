# ImageToEditablePPT v3 아키텍처 계획서

최종 업데이트: 2026-03-25  
상태: `Phase 5A/5B: public surface cleanup + emit-friendly IR bridge 완료`

---

## 문서 운영 원칙

이 문서는 v3 마이그레이션의 **source of truth**다.

규칙:

- 이후 context compact 등으로 대화 맥락이 일부 손실되더라도, 이 문서를 기준으로 작업을 이어간다.
- 각 Phase 종료 시 반드시 이 문서를 갱신한다.
- 문서에는 최소한 아래 항목이 항상 최신 상태로 유지되어야 한다.
  - 현재 상태
  - 다음 단계
  - 미해결 이슈
  - 보존/삭제 정책
  - 지원 family 범위
- 구현보다 문서가 먼저다. 큰 방향 변경이 생기면 코드를 먼저 고치지 말고 이 문서를 먼저 갱신한다.

---

## 1. 문제 재정의

v2 코어는 점진적으로 heuristic과 generic reconstruction 중심으로 커졌고, 현재는 프로젝트의 목표와 구조적으로 어긋난 것으로 판단한다.

v3는 다음 전제에서 다시 시작한다.

- 목표는 **범용적인 그림 복제**가 아니다.
- 목표는 **수정 가능한 PowerPoint 다이어그램 복원**이다.
- 입력 이미지는 단일 RGB 이미지 하나로 다루지 않는다.
- 입력은 최소한 다음 3개 branch로 분기한다.
  - `structure` branch
  - `style` branch
  - `text` branch
- 텍스트와 raster/non-diagram 영역은 초기에 분리한다.
- 구조 추론은 residual structural canvas 위에서 수행한다.
- family detection과 family parsing은 분리된 단계다.
- connector는 node/container 구조가 안정화된 뒤 확정한다.
- 해석되지 않은 나머지는 억지 native shape로 환각하지 않고, explicit residual/fallback으로 남긴다.

요약하면,  
v3는 **generic reconstruction**이 아니라 **family-constrained diagram parsing**을 목표로 한다.

---

## 2. 목표 / 비목표

### 2.1 목표

- 코어를 family-constrained diagram parsing 중심으로 재구성한다.
- 단계 경계를 명확한 typed IR과 contract로 고정한다.
- 기존 benchmark / validation / GT sidecar / workbench 자산은 유지한 채 코어를 교체한다.
- 텍스트, raster, diagram 구조를 초기부터 분리한다.
- unresolved residual을 명시적으로 유지한다.
- 시각적 흉내보다 editable PowerPoint primitive 복원을 우선한다.
- detector 결과를 바로 PPT로 넣지 않고, 반드시 IR을 거쳐 해석/검증 후 emit한다.

### 2.2 비목표

- v2 heuristic을 현 위치에서 계속 개선하지 않는다.
- pixel-perfect 복제를 목표로 하지 않는다.
- v2 코어 로직을 억지로 v3 내부에 재사용하지 않는다.
- `Phase 0~1`에서 detector/parser 모델의 실제 성능까지 구현하려 하지 않는다.
- migration 초기 단계에서 benchmark / validation / GT / workbench 자산을 삭제하지 않는다.
- 초기 단계에서 family 범위를 무리하게 넓히지 않는다.

---

## 3. 핵심 설계 원칙

### 원칙 1. 흑백은 유일한 입력이 아니라 구조 branch다
흑백/edge view는 구조를 보기 위한 branch이며, style/text branch를 대체하지 않는다.

### 원칙 2. 텍스트는 제거 대상이 아니라 이중 역할 대상이다
텍스트는 최종 복원 대상이므로 보존한다.  
다만 구조 추론용 canvas에서는 soft-mask 또는 inpaint를 통해 영향만 줄인다.

### 원칙 3. raster/non-diagram은 초기에 분리한다
사진, 캡처, 픽토그램, 장식 요소를 초기에 분리해 구조 추론을 안정화한다.

### 원칙 4. detector와 parser를 분리한다
- detector: 어떤 family/region일 가능성이 있는가
- parser: 그 family가 어떤 내부 구조를 가지는가

### 원칙 5. node/container가 먼저, connector는 나중이다
connector는 line evidence를 먼저 수집할 수는 있지만, 최종 확정은 node/container가 안정화된 뒤에 한다.

### 원칙 6. 직접 삽입 금지
탐지 결과를 곧바로 PPT에 삽입하지 않는다.  
반드시 IR → 검증 → 충돌 해결 → emit 순서를 거친다.

### 원칙 7. residual은 정직하게 남긴다
해석되지 않은 영역을 무리하게 native object로 복원하지 않는다.  
explicit residual / raster fallback으로 남긴다.

---

## 4. 지원 diagram family

family registry는 detector 구현 이전부터 **명시적 allowlist**로 운영한다.  
사용자는 config에서 family를 on/off 할 수 있어야 한다.

### 4.1 v3 MVP family (초기 우선순위)

초기에는 범위를 좁게 가져간다.

- `titled_panel`
- `repeated_cards`
- `orthogonal_flow`
  - simple block flow 포함
- `comparison_columns`

선정 이유:

- 현재 문제 사례와 직접적으로 맞닿아 있다.
- 구조 규칙이 비교적 명확하다.
- container / text slot / connector 관계를 파싱하기 좋은 family다.

### 4.2 후순위 family (MVP 이후)

- `cycle`
- `swimlane`
- `timeline`
- `table_matrix`
- `layered_stack`

### 4.3 family 운영 규칙

- 구현되지 않은 family는 registry에 존재하더라도 기본 비활성화할 수 있다.
- detector와 parser가 모두 준비되기 전까지 broad enable을 하지 않는다.
- family 추가는 “종류 수”보다 “benchmark에서 실질적으로 복원 가능한 구조”를 기준으로 판단한다.

---

## 5. 전체 파이프라인 단계

1. 입력 로드 및 RGB 정규화
2. multiview branch 생성
3. text region 탐지 및 OCR
4. text role 분류 및 soft masking
5. raster/non-diagram region 제안
6. residual structural canvas 생성
7. diagram family detection
8. family-specific parsing
9. node/container 안정화
10. connector resolution
11. style token 추출
12. slide-level IR 조립
13. conflict/residual 정리
14. editable PPT emit
15. diagnostics / validation / benchmark reporting

### 파이프라인 해석 규칙

- 1~6단계는 **관측 분리**
- 7~10단계는 **구조 해석**
- 11~13단계는 **스타일/조립/정리**
- 14단계는 **출력**
- 15단계는 **평가 및 진단**

---

## 6. 핵심 IR 정의

v3는 아래 named IR object를 핵심 계약으로 사용한다.

- `MultiViewBundle`
- `TextRegion`
- `RasterRegion`
- `FamilyProposal`
- `DiagramInstance`
- `ConnectorSpec`
- `StyleToken`
- `SlideIR`

### 6.1 핵심 IR 설명

#### `MultiViewBundle`
동일 입력 이미지를 구조/스타일/텍스트 목적에 맞게 분기한 뷰 묶음.

#### `TextRegion`
텍스트 bbox, OCR 문자열, 텍스트 역할(title/body/label 등)을 담는 단위.

#### `RasterRegion`
사진, 아이콘, 픽토그램, 기타 non-diagram raster 영역을 표현하는 단위.

#### `FamilyProposal`
특정 region이 어떤 diagram family일 가능성이 있는지 나타내는 제안 단위.

#### `DiagramInstance`
family parser가 해석한 구조 결과.
container, node, slot, local relation을 포함한다.

#### `ConnectorSpec`
node/container 사이의 연결 관계와 path, endpoint, arrowhead 정보를 담는 단위.

#### `StyleToken`
fill, stroke, radius, opacity, font 관련 스타일 정보.

#### `SlideIR`
최종 emit 직전의 슬라이드 내부 표현.
text, raster, diagram instance, connector, style, residual을 모두 포함한다.

### 6.2 보조 IR 개념

- `Point`
- `BBox`
- `ImageSize`
- branch payload descriptor
- unresolved residual region
- stage trace artifact
- source provenance map

---

## 7. 모듈 구조

### 7.1 전체 패키지 레이아웃

- `src/image_to_editable_ppt/legacy_v2/`
- `src/image_to_editable_ppt/shared/`
- `src/image_to_editable_ppt/eval_runtime/`
- `src/image_to_editable_ppt/v3/app/`
- `src/image_to_editable_ppt/v3/core/`
- `src/image_to_editable_ppt/v3/preprocessing/`
- `src/image_to_editable_ppt/v3/text/`
- `src/image_to_editable_ppt/v3/raster/`
- `src/image_to_editable_ppt/v3/families/`
- `src/image_to_editable_ppt/v3/connectors/`
- `src/image_to_editable_ppt/v3/style/`
- `src/image_to_editable_ppt/v3/ir/`
- `src/image_to_editable_ppt/v3/compose/`
- `src/image_to_editable_ppt/v3/emit/`
- `src/image_to_editable_ppt/v3/diagnostics/`

### 7.2 경계 규칙

- 신규 아키텍처 작업은 `src/image_to_editable_ppt/v3/` 아래에서만 수행한다.
- `legacy_v2`는 유지/호환 목적이며, 새로운 구조 아이디어를 추가하지 않는다.
- `shared/`에는 v2 가정을 끌고 오지 않는 순수 유틸만 옮긴다.
- `eval_runtime/`은 기존 benchmark/eval 자산을 보존/재사용하기 위한 계층이다.

### 7.3 모듈 책임 요약

#### `v3/app/`
실행 진입점, config, run context, orchestration

#### `v3/core/`
공통 enum, 타입, contract, 에러 정의

#### `v3/preprocessing/`
multiview 생성, normalization, residual structural canvas 준비

#### `v3/text/`
text detection, OCR, role classification, soft masking

#### `v3/raster/`
raster/icon/pictogram region 분리

#### `v3/families/`
family registry, detector, parser, family별 builder

#### `v3/connectors/`
line evidence 수집, port 추정, connector solving

#### `v3/style/`
text style / shape style / style token 추출

#### `v3/ir/`
IR dataclass, validation, source map

#### `v3/compose/`
branch 결과 조립, conflict 해결, residual 정리

#### `v3/emit/`
PPT primitive emit, raster fallback emit

#### `v3/diagnostics/`
stage artifact 기록, overlay, report helper

---

## 8. Legacy Cleanup / Isolation Phase

이번 단계 이름:

- `legacy cleanup / isolation phase`

### 8.1 이번 단계 목표

- legacy 범위를 명시적으로 정의한다.
- v2 코어와 v3 코어 사이의 경계를 문서와 테스트로 고정한다.
- v3가 legacy 내부 구현에 직접 의존하지 못하게 한다.
- benchmark / validation / GT sidecar / workbench / diagnostics 자산을 유지한 채 migration 가능한 구조를 만든다.
- 기존 public entrypoint를 즉시 깨지 않도록 compatibility shim 전략을 정의한다.

### 8.2 이번 단계 비목표

- v2 heuristic 품질 개선
- v3 detector/parser 성능 구현 확대
- benchmark methodology 재작성
- legacy 코드 전체 즉시 삭제
- "재사용 가능해 보인다"는 이유만으로 legacy 로직을 shared로 이동
- v3가 legacy 구현을 import하도록 허용하는 일

### 8.3 Legacy 후보 파일 목록

아래는 현재 기준으로 `legacy_core` 후보다.

- `src/image_to_editable_ppt/pipeline.py`
- `src/image_to_editable_ppt/geometry.py`
- `src/image_to_editable_ppt/objects.py`
- `src/image_to_editable_ppt/selection.py`
- `src/image_to_editable_ppt/graph.py`
- `src/image_to_editable_ppt/emit.py`
- `src/image_to_editable_ppt/fallback.py`
- `src/image_to_editable_ppt/guides.py`
- `src/image_to_editable_ppt/reconstructors/*`
- `src/image_to_editable_ppt/detector.py`
- `src/image_to_editable_ppt/repair.py`
- `src/image_to_editable_ppt/router.py`
- `src/image_to_editable_ppt/filtering.py`
- `src/image_to_editable_ppt/fitter.py`
- `src/image_to_editable_ppt/text.py`
- `src/image_to_editable_ppt/preprocess.py`
- `src/image_to_editable_ppt/style.py`
- `src/image_to_editable_ppt/gating.py`

설명:

- 위 목록은 "장기적으로 `legacy_v2/` 아래로 이동할 대상"이지, 이번 단계에서 즉시 물리 이동한다는 뜻은 아니다.
- 애매하면 legacy에 남긴다. shared로 올리지 않는다.

### 8.4 Preserve Eval 대상

아래는 `preserve_eval` 대상으로 유지한다.

- `src/image_to_editable_ppt/validation.py`
- `src/image_to_editable_ppt/eval_debug.py`
- `src/image_to_editable_ppt/benchmark_report.py`
- `src/image_to_editable_ppt/diagnostics.py`
- `src/image_to_editable_ppt/source_attribution.py`
- `tools/benchmark_report.py`
- `tests/test_benchmark_report.py`
- `workbench/`
- `workbench2.0/`
- `workbench2.0-geometry-only/`
- `workbench2.0-no-motifs/`
- 기존 GT sidecar, comparison, benchmark summary, diagnostics 산출물

### 8.5 Shared Candidate 기준

`shared_candidate`로 검토 가능한 것은 아래만 허용한다.

- 순수 데이터 구조
  - 예: `BBox`, `Point`, `ImageSize`
- 저수준 JSON / path / file IO helper
- v2 heuristic 가정이 전혀 없는 순수 helper

`shared/`로 절대 옮기지 않을 것:

- geometry scoring
- fallback logic
- selection heuristic
- semantic/object reconstruction logic
- detector/parser 의사결정 코드
- legacy provenance나 stage semantics에 강하게 묶인 코드

### 8.6 Compatibility Shim 원칙

- 옛 import path는 당분간 유지 가능하다.
- shim은 얇은 wrapper 또는 re-export만 허용한다.
- shim은 임시 계층임을 문서에 명시한다.
- 새 기능은 shim에 추가하지 않고 `v3/` 아래에만 구현한다.
- benchmark/eval이 legacy와 v3를 함께 다뤄야 할 때는 `eval_runtime/` adapter를 사용한다.

### 8.7 완료 조건

- `plan.md`가 이번 단계 기준으로 갱신되어 있을 것
- legacy / preserve_eval / shared_candidate / defer 분류가 존재할 것
- `legacy_v2`의 역할과 향후 이동 대상이 명시되어 있을 것
- v3가 legacy 구현에 직접 의존하지 않도록 문서/테스트/코드 중 최소 하나로 강제할 것
- compatibility shim 전략이 정의되어 있을 것
- 기존 테스트가 유지될 것
- 새 구조/경계 테스트가 추가될 것

### 8.8 이번 phase 산출물

- `docs/legacy_inventory.md`
- `src/image_to_editable_ppt/legacy_v2/README.md`
- `src/image_to_editable_ppt/shared/README.md`
- `tests/README.md`
- `tests/test_v3_architecture.py`

현재 상태 메모:

- 이 phase는 완료되었다.
- 이후 purge 단계에서 shim 전략은 최소 tombstone만 남기는 형태로 축소되었다.

---

## 9. 평가 전략

v3 migration 동안 아래 자산은 반드시 보존하고 계속 사용 가능해야 한다.

- `src/image_to_editable_ppt/validation.py`
- `src/image_to_editable_ppt/eval_debug.py`
- `src/image_to_editable_ppt/benchmark_report.py`
- `tools/benchmark_report.py`
- `tests/test_benchmark_report.py`
- 기존 diagnostics 및 benchmark summary
- `workbench/`
- `workbench2.0/`
- `workbench2.0-geometry-only/`
- `workbench2.0-no-motifs/`
- 현재 validation flow가 사용하는 GT sidecar 및 comparison artifact

### 9.1 migration 원칙

- v2 평가 경로는 v3가 자라나는 동안 유지한다.
- 초기에는 v3 전용 contract test를 먼저 만든다.
- 필요할 때만 adapter를 추가해 기존 benchmark 툴이 v3 출력을 읽을 수 있게 한다.
- `Phase 0~1`에서 benchmark methodology 자체를 뜯어고치지 않는다.
- `Phase 2`에서는 adapter를 구현하지 않고, adapter가 읽어야 할 v3 출력 계약만 고정한다.
- `Legacy purge + Phase 3 bootstrap`에서는 validation runtime adapter를 구현하지 않고 tombstone으로 고정한다.

### 9.2 현재 평가 한계

- GT-backed benchmark coverage는 아직 넓지 않다.
- 현재 결론은 일부 benchmark slide에 더 강하게 의존할 수 있다.
- 따라서 summary에는 coverage limitation을 명시적으로 남겨야 한다.

### 9.3 v3에서 유지할 평가 축

- image-level render comparison
- GT-backed stage evaluation
- per-kind breakdown
- source attribution
- residual/fallback accounting

---

## 10. 마일스톤 체크리스트

### Phase 0. 재출발 준비
- [x] root `plan.md` 생성
- [x] 이 문서를 source of truth로 선언
- [x] v2 격리 정책 문서화
- [x] benchmark / validation / GT / workbench 보존 정책 문서화
- [x] `v3/` 패키지 스캐폴딩 생성

**완료 조건**
- 새 구조의 기본 디렉터리와 책임 분리가 문서/코드에 반영되어 있어야 한다.

---

### Phase 1. 코어 계약 바닥 공사
- [x] core enums / types / contracts 추가
- [x] config 및 placeholder orchestration 추가
- [x] multiview bundle placeholder 추가
- [x] IR model / validation 추가
- [x] focused architecture test 추가

**완료 조건**
- detector/parser 성능은 비어 있어도 된다.
- 대신 어떤 데이터가 어떤 단계로 넘어가는지 타입 계약이 명확해야 한다.

---

### Phase 2. text / raster 분리 시작

이번 단계 이름:

- `Phase 2: text/raster separation`

이번 단계 목표:

- text branch가 최소 실제 region 결과를 생성한다.
- raster/non-diagram branch가 최소 실제 region 결과를 생성한다.
- text soft-mask와 raster subtraction 이후의 residual structural canvas contract를 고정한다.
- 이후 family detector/parser가 받을 입력 형식을 typed IR로 못박는다.
- preserve-eval 자산은 손대지 않고 adapter 요구사항만 기록한다.

이번 단계 비목표:

- legacy 물리 이동
- root import path shim 추가
- v2 heuristic 성능 개선
- family parser 본격 구현
- connector solving 확대
- detector 모델 성능 최적화
- shared로의 무리한 코드 추출

이번 단계에서 text branch가 출력해야 하는 것:

- `TextRegion` 목록
- `TextLayerResult`
- text-soft-masked structure view 또는 동등한 payload
- region role, provenance, diagnostics-friendly metadata

이번 단계에서 raster branch가 출력해야 하는 것:

- `RasterRegion` 목록
- `RasterLayerResult`
- subtraction에 사용할 raster mask 또는 동등한 payload
- provenance, diagnostics-friendly metadata

residual structural canvas contract:

- text soft-mask가 반영된 구조 view
- raster subtraction이 반영된 구조 view
- 최종 `ResidualStructuralCanvas`
- image size / coordinate contract
- 반영된 text/raster region id provenance

shim phase를 아직 열지 않는 이유:

- 지금 필요한 것은 import 경로 재배선이 아니라 detector/parser 입력 contract 고정이다.
- legacy 이동과 shim 작업을 지금 섞으면 branch contract보다 호환성 작업이 앞서게 된다.
- 따라서 이번 단계는 v3 내부 입력 분리 구조를 먼저 안정화하는 데 집중한다.

Phase 3로 넘어가기 위한 조건:

- text/raster/residual typed contract가 코드로 정의됨
- text branch가 최소 실제 결과를 생성함
- raster branch가 최소 실제 결과를 생성함
- residual structural canvas가 orchestration에 연결됨
- structure/contract 중심 테스트가 통과함

- [x] text region proposal 실제화
- [x] OCR 없이도 text role field를 유지하는 최소 contract 구현
- [x] text soft-mask contract 확정
- [x] raster/non-diagram proposal 최소 구현
- [x] residual structural canvas contract 확정

**완료 조건**
- empty tuple placeholder가 아니라 최소한의 실제 branch 결과가 생성되어야 한다.
- `convert.py`가 `multiview -> text -> raster -> residual` 흐름을 실제로 연결해야 한다.
- architecture boundary test와 legacy regression이 유지되어야 한다.

---

### Phase 3. family detector / parser 골격

이번 단계 이름:

- `Legacy purge + Phase 3 bootstrap`

왜 이제 v2 구현 코드를 workspace에서 제거하는가:

- `Phase 2`에서 text/raster/residual branch contract가 이미 v3 내부에 고정되었다.
- 이제부터 v3가 실제 detector/parser 입력을 받기 시작하므로, 더 이상 v2 구현을 workspace에 남겨 둘 이유가 없다.
- legacy 구현을 남겨 두면 preserve-eval과 public surface가 계속 old runtime에 기대게 되고, v3 중심 전환이 지연된다.
- 재사용하지 않을 코드는 git history에만 남기고 workspace에서는 제거하는 것이 설계 오염을 막는 데 더 낫다.

이번 단계에서 삭제하는 것:

- `legacy_core`로 분류된 v2 변환 구현 코드
- v2 전용 regression test
- v2 구현을 직접 검증하는 helper/fixture

이번 단계에서 유지하는 것:

- benchmark / validation / GT / workbench / diagnostics 자산
- `preserve_eval`로 분류된 보고/집계/분석 모듈
- v3 contract / architecture / phase test
- 최소 shared primitive

tombstone stub 허용 조건:

- 모듈 이름 자체는 당장 남아야 한다.
- 내부 구현은 절대 포함하지 않는다.
- 파일 내용은 짧고 명확한 예외 메시지뿐이어야 한다.
- 메시지에는 `v2 core removed, use v3 path / see plan.md`가 포함되어야 한다.

`Phase 3`의 목표:

- family registry를 실제 코드로 만든다.
- config 기반 family enable/disable을 registry와 연결한다.
- 첫 family에 대해 detector skeleton을 residual structural canvas 위에 연결한다.
- detector proposal을 parser skeleton으로 넘겨 최소 `DiagramInstance`를 만든다.
- broad emit 없이 `SlideIR`까지 실제로 연결한다.

`Phase 3`의 비목표:

- broad emit 구현
- connector solving 확장
- family 성능 최적화
- 여러 family 동시 구현
- legacy heuristic 재활용

첫 family 범위:

- `orthogonal_flow` 하나만 구현한다.
- 이유: 현재 residual structural canvas와 가장 자연스럽게 연결되고, node/container slot 구조를 최소한으로 시험하기 좋기 때문이다.

- [ ] family registry 실제화
- [x] config 기반 family on/off
- [x] 첫 family detector skeleton
- [x] 첫 family parser skeleton
- [x] broad emit 없이 IR 수준까지 연결

**완료 조건**
- 최소 1개 family에 대해 detector → parser → DiagramInstance 흐름이 돌아야 한다.
- legacy 구현 코드가 workspace에서 제거되어야 한다.
- old root module이 남는 경우에는 tombstone stub뿐이어야 한다.
- preserve-eval이 삭제된 구현을 import-time에 참조하지 않아야 한다.

실제 완료 결과:

- root legacy 구현 파일과 `reconstructors/*`가 workspace에서 제거되었다.
- `shared/geometry.py`에 `BBox`, `Point`, `ImageSize`만 추출되었다.
- `validation.py`와 `cli.py`만 tombstone stub로 남겼다.
- `orthogonal_flow` family registry/detector/parser skeleton이 residual structural canvas 위에 연결되었다.
- `convert.py`가 `multiview -> text -> raster -> residual -> family_detect -> family_parse` 흐름을 실제로 수행한다.

---

### Phase 4. node/container + connector evidence

이번 단계 이름:

- `Phase 4: node/container + connector evidence`

이번 단계 목표:

- `orthogonal_flow` 한 family에 대해 node와 container를 IR에서 명시적으로 분리한다.
- detector가 slide 전체 giant proposal 하나에 머무르지 않도록 최소 multi-instance proposal 방향으로 개선한다.
- connector solving이 아니라 connector evidence 수집 단계만 추가한다.
- v3-native debug/inspection loop를 만들어 proposal / instance / connector evidence를 overlay와 JSON으로 직접 확인할 수 있게 한다.
- broad emit 없이 residual canvas 기반 구조 해석을 계속 키운다.

이번 단계 비목표:

- v2 runtime 복원
- broad emit
- benchmark methodology 재작성
- 여러 family 동시 구현
- connector solving / route optimization
- style token 본격 구현
- tombstone stub에 old logic을 다시 넣는 일

왜 debug/inspection loop가 우선인가:

- 지금 단계의 병목은 emit이 아니라 해석 결과가 사람 눈에 보이지 않는다는 점이다.
- detector / parser / evidence가 잘못되더라도 overlay와 JSON이 없으면 원인을 빠르게 좁힐 수 없다.
- 따라서 `Phase 4`는 성능 향상보다 “보이게 만들기”를 먼저 수행한다.

왜 `orthogonal_flow` 한 family만 대상으로 삼는가:

- residual structural canvas와 가장 자연스럽게 연결된다.
- node / container / connector evidence를 동시에 시험해 보기 좋다.
- 여러 family를 동시에 열면 detector / parser / debug artifact contract가 다시 흐려진다.

왜 broad emit를 계속 미루는가:

- 지금은 instance 해석 결과의 신뢰성과 분해 구조가 먼저다.
- emit를 붙이면 잘못된 IR이 외부 출력 형식으로 고정될 위험이 크다.
- overlay/JSON inspection이 먼저 안정화되어야 emit 단계로 넘어갈 수 있다.

왜 connector는 evidence까지만 하는가:

- solver를 붙이기 전에 어떤 선분, 어떤 orthogonal hint, 어떤 attachment vicinity가 있는지 먼저 수집해야 한다.
- 지금 필요한 것은 최종 route가 아니라 다음 단계 solver의 입력 계약이다.
- evidence를 분리해 두면 잘못된 연결과 부족한 관측을 구분할 수 있다.

- [x] tombstone 유지 여부 재검토 및 문서화
- [x] v3-native debug/inspection runner 추가
- [x] node/container IR 분리
- [x] orthogonal_flow detector multi-instance 방향 개선
- [x] orthogonal_flow parser node/container 분리
- [x] connector evidence typed IR 추가
- [x] convert orchestration에 connector evidence 연결

**완료 조건**
- `plan.md`가 `Phase 4` 기준으로 갱신되어 있을 것
- tombstone 유지 여부가 문서화될 것
- v3 debug/inspection 경로가 JSON artifact와 overlay를 생성할 것
- detector가 최소한의 multi-instance proposal을 만들 것
- parser가 node/container를 IR에서 분리할 것
- connector evidence가 `SlideIR`에 저장될 것
- broad emit가 여전히 꺼져 있을 것

Phase 5 진입 조건:

- proposal / instance / connector evidence를 사람이 overlay와 JSON으로 점검할 수 있을 것
- node/container 분리가 한 family에서 재현 가능할 것
- connector evidence가 solver 입력으로 쓸 수 있는 최소 contract를 가질 것
- old validation runtime 복구 없이도 v3-native inspection이 가능할 것

---

### Phase 5A. public surface cleanup

이번 단계 이름:

- `Phase 5A: public surface cleanup`

이번 단계 목표:

- README와 사용자-facing 문서를 현재 v3 중심 상태에 맞춘다.
- tombstone 메시지가 제거된 v2 runtime 대신 현재 대체 경로를 명확히 가리키게 한다.
- historical / obsolete 문서를 남길 경우 상태를 명시해 현재 사용 경로와 혼동되지 않게 한다.
- 현재 레포의 public surface가 더 이상 존재하지 않는 v2 CLI / validation / emit 흐름을 “현재 사용법”처럼 말하지 않게 만든다.

이번 단계 비목표:

- old validation runtime 복구
- v2 CLI 동작 복원
- PPTX 실제 생성 복구
- benchmark methodology 재작성

왜 지금 public surface 정리가 필요한가:

- legacy purge 이후 README와 역사 문서가 여전히 v2/VLM/PPT export 중심 흐름을 설명하면 레포의 실제 상태와 문서가 어긋난다.
- `Phase 4`부터는 v3-native debug/inspection path가 실제 진입점이므로, 사용자와 이후 에이전트가 이 경로를 기준으로 이해할 수 있어야 한다.
- emit를 붙이기 전에 public surface를 정직하게 맞춰 두어야 이후 adapter/emit 문서가 누적 부채 없이 올라간다.

- [x] README 현재 상태 반영
- [x] tombstone 메시지 대체 경로 갱신
- [x] historical / obsolete 문서 상태 명시
- [x] tests/README 현재 테스트 분류 반영

**완료 조건**
- public surface가 현재 동작하는 v3 debug/inspection 중심 경로와 일치해야 한다.
- tombstone이 `plan.md`와 현재 대체 경로를 안내해야 한다.

### Phase 5B. emit-friendly IR bridge

이번 단계 이름:

- `Phase 5B: emit-friendly IR bridge`

이번 단계 목표:

- family-specific `DiagramInstance`를 family-agnostic primitive scene으로 정규화하는 중간 계층을 추가한다.
- node/container/text/raster residual/connector candidate를 하나의 scene 계약으로 묶는다.
- connector evidence를 attachment-aware connector candidate까지 끌어올린다.
- debug runner가 proposal / instance / connector evidence뿐 아니라 primitive scene도 JSON과 overlay로 보여주게 한다.

이번 단계 비목표:

- broad emit
- eval adapter 구현
- connector full route optimization
- style token full extraction
- residual fallback emit 구현

왜 broad emit를 아직 미루는가:

- 현재 필요한 것은 emit 그 자체가 아니라 emit가 읽을 수 있는 장면 표현의 안정화다.
- family parser 산출물을 곧바로 PPT primitive로 고정하면 connector attachment와 residual handoff 계약이 검증되기 전에 외부 형식이 먼저 굳는다.
- 따라서 `Phase 5B`는 “emit-ready but not emitted” 상태를 만드는 단계로 제한한다.

emit-friendly IR bridge의 목적:

- detector / parser / evidence 중심 `SlideIR`를 다음 단계 emit가 받아먹기 쉬운 scene 표현으로 정규화한다.
- family-specific 구조를 family-agnostic primitive 집합으로 내리되 provenance와 confidence를 유지한다.
- unresolved evidence와 attached candidate를 동시에 보존해 solver/emit 단계에서 정보 손실을 줄인다.

connector evidence -> attachment-aware connector candidate의 목적:

- evidence 목록만으로는 어떤 node/container edge에 붙을 수 있는지 드러나지 않는다.
- 다음 단계 solver가 route 최적화보다 먼저 attachment 구조를 이해할 수 있도록 port-aware candidate를 만든다.
- attach되지 않은 evidence는 rejection reason과 함께 남겨 residual 판단 근거로 쓴다.

- [x] primitive scene typed IR 추가
- [x] port model 추가
- [x] evidence -> attachment-aware connector candidate bridge 추가
- [x] family instance -> primitive scene mapping 추가
- [x] debug runner primitive scene artifact 확장
- [x] convert orchestration에 primitive scene 연결

**완료 조건**
- primitive scene이 정의되고 `SlideIR`에서 접근 가능해야 한다.
- port와 attachment-aware connector candidate가 생성되어야 한다.
- debug runner가 primitive scene JSON / overlay artifact를 남겨야 한다.
- broad emit가 여전히 꺼져 있어야 한다.

실제 완료 결과:

- README / tombstone / historical 문서가 현재 v3 debug 중심 상태로 정리되었다.
- `PrimitiveScene`, `PortSpec`, `PrimitiveConnectorCandidate`, `UnattachedConnectorEvidence`가 추가되었다.
- connector evidence가 port-aware attachment candidate까지 연결된다.
- `convert.py`가 `connector_evidence -> port_generate -> connector_attach -> primitive_scene` 흐름을 실제로 수행한다.
- debug runner가 primitive scene JSON / overlay artifact를 저장한다.
- broad emit는 여전히 꺼져 있다.

---

### Phase 6. actual emit / eval adapter bootstrap
- [ ] primitive scene -> emit primitive adapter 초안
- [ ] connector candidate -> solved connector bridge 초안
- [ ] v3 primitive scene -> eval adapter 범위 정의
- [ ] emit 전/후 diff inspection loop 최소 경로 확보

**완료 조건**
- primitive scene이 broad emit 바로 직전 단계로 안정화되고, emit/eval adapter가 읽을 수 있는 최소 bridge가 있어야 한다.

---

### Phase 7. family 확장 및 benchmarking
- [ ] MVP family 순차 구현
- [ ] per-family benchmark 비교
- [ ] GT-backed coverage 확장 검토
- [ ] residual/fallback 정책 정리

**완료 조건**
- 최소 MVP family 세트에 대해 품질과 실패 양상이 측정 가능해야 한다.

---

## 11. legacy 보존 / 삭제 정책

### 11.1 현재 정책

- benchmark / validation artifact / GT / workbench 자산은 유지한다.
- v2 변환 구현 코드는 workspace에서 제거한다.
- old root module은 꼭 필요한 경우에만 tombstone stub로 남긴다.
- v3는 root legacy 구현이나 `legacy_v2`에 직접 의존하지 않는다.

### 11.2 tombstone 정책

현재 허용된 tombstone은 아래뿐이다.

- `src/image_to_editable_ppt/cli.py`
- `src/image_to_editable_ppt/validation.py`

Phase 4 재검토 결과:

- `cli.py`는 `src/image_to_editable_ppt/__main__.py`와 기존 `python -m image_to_editable_ppt` 진입점을 깨지 않기 위해 유지한다.
- `validation.py`는 preserve-eval import surface를 명시적 tombstone으로 고정하기 위해 유지한다.
- 둘 다 old runtime을 복구하지 않고 짧은 예외 메시지만 유지한다.

조건:

- 내부에 old implementation을 포함하지 않는다.
- 명시적 예외 메시지만 제공한다.
- `v2 core removed, use v3 path / see plan.md` 메시지를 포함한다.

### 11.3 shared 추출 정책

- 실제 shared 추출은 `BBox`, `Point`, `ImageSize`로 제한한다.
- geometry scoring, selection, fallback, parser, emit logic은 shared로 올리지 않는다.
- 새로 공유할 후보가 생기면 v2 가정이 전혀 없는지 별도 검토 후 추가한다.

---

## 12. 열린 문제 / 리스크

### 열린 문제

- v3 MVP family 범위를 어디까지로 둘 것인가
- 어떤 low-level utility가 v2 가정 없이 재사용 가능한가
- text soft-mask를 detector-friendly하게 어떤 형식으로 넘길 것인가
- family parsing 이후 residual handoff format을 어떻게 정의할 것인가
- v3 diagnostics를 기존 benchmark manifest와 어떻게 맞출 것인가

### 리스크

- family 범위를 초기에 너무 넓히면 다시 generic reconstruction처럼 흐를 수 있다.
- v2 로직을 부분 재사용하려는 유혹이 v3 설계를 오염시킬 수 있다.
- benchmark GT coverage가 좁으면 초기 결론을 과신할 수 있다.
- emit를 너무 빨리 붙이면 parser/IR 설계가 불안정한 상태로 굳을 수 있다.

---

## 13. 현재 상태

- `plan.md`가 v3 migration의 source of truth로 설정되었다.
- 방금 완료한 단계는 `Phase 5A/5B: public surface cleanup + emit-friendly IR bridge`다.
- 다음 활성 단계는 `Phase 6: actual emit / eval adapter bootstrap`이다.
- `legacy cleanup / isolation phase` 기준이 문서화되었다.
  - legacy 후보
  - preserve_eval 대상
  - shared_candidate 기준
  - compatibility shim 원칙
- `src/image_to_editable_ppt/v3/` 스캐폴드가 생성되었다.
- 최소 v3 contract가 구현되었다.
  - `V3Config`
  - multiview bundle builder
  - IR dataclass
  - IR validator
  - unresolved residual을 명시하는 placeholder orchestration
- `Phase 2` branch contract가 구현되었다.
  - `TextLayerResult`
  - `RasterLayerResult`
  - `ResidualStructuralCanvas`
  - `ResidualCanvasResult`
- text branch가 최소 실제 결과를 생성한다.
  - text region proposal
  - role field
  - soft-masked structure view
- raster branch가 최소 실제 결과를 생성한다.
  - raster/non-diagram region proposal
  - subtraction mask
  - subtracted structure view
- residual structural canvas가 고정되었다.
  - text-suppressed view
  - raster-suppressed view
  - final residual canvas
  - text/raster provenance ids
- 보존 namespace가 준비되었다.
  - `src/image_to_editable_ppt/legacy_v2/`
  - `src/image_to_editable_ppt/shared/`
  - `src/image_to_editable_ppt/eval_runtime/`
- legacy purge가 완료되었다.
  - root legacy 구현 파일 제거
  - `reconstructors/*` 제거
  - deleted implementation은 git history에만 존재
- legacy inventory가 문서화되었다.
  - `docs/legacy_inventory.md`
- `legacy_v2`는 역사적 namespace로만 남겼다.
  - `src/image_to_editable_ppt/legacy_v2/README.md`
- shared 수용 기준과 실제 추출물이 문서화되었다.
  - `src/image_to_editable_ppt/shared/README.md`
- 실제 shared primitive가 추출되었다.
  - `BBox`
  - `Point`
  - `ImageSize`
- 테스트 분류 규칙이 문서화되었다.
  - `tests/README.md`
- v3 import 경계가 테스트로 강제된다.
  - `tests/test_v3_architecture.py`
- old public surface는 v3-first로 바뀌었다.
  - `image_to_editable_ppt.__init__`
  - `image_to_editable_ppt.v3`
- tombstone stub만 남아 있다.
  - `cli.py`
  - `validation.py`
- preserve-eval은 deleted runtime을 import-time에 참조하지 않는다.
- v2 전용 테스트가 퇴역되었다.
  - `tests/test_pipeline.py`
  - `tests/test_stage_refactor.py`
  - `tests/synthetic.py`
- `Phase 3` bootstrap이 완료되었다.
  - family registry 실제화
  - config 기반 family on/off
  - `orthogonal_flow` detector skeleton
  - `orthogonal_flow` parser skeleton
  - detector -> parser -> `SlideIR` 연결
- `Phase 4`가 완료되었다.
  - tombstone 재검토 완료
  - `cli.py`, `validation.py` 유지 이유 문서화
  - proposal / instance / connector evidence JSON artifact 저장
  - proposal / instance / connector evidence overlay 저장
  - `orthogonal_flow` detector가 connected component 단위 multi-instance proposal 생성
  - parser가 node/container를 명시적으로 분리
  - connector evidence가 `SlideIR.connector_evidence`에 저장
- `Phase 5A/5B`가 완료되었다.
  - public surface를 v3 debug/inspection 중심 상태로 맞췄다.
    - README는 `tools/run_v3_debug.py`와 `image_to_editable_ppt.v3.convert_image`를 현재 진입점으로 안내한다.
    - `conversion-spec.md`, `v2.0 instruction.md`에 historical / obsolete 상태를 명시했다.
    - `cli.py`, `validation.py` tombstone은 `plan.md`와 `tools/run_v3_debug.py`를 대체 경로로 안내한다.
  - primitive scene / port / attachment-aware connector candidate bridge가 추가되었다.
    - `SlideIR.primitive_scene`이 추가되었다.
    - `SlideIR.connector_candidates`, `SlideIR.unattached_connector_evidence`가 추가되었다.
    - debug runner가 `primitive_scene.json`, `attached_connectors.json`, `overlay_ports.png`, `overlay_primitives.png`, `overlay_attached_connectors.png`를 저장한다.
- adapter 구현은 아직 하지 않았다.
  - future `eval_runtime/` adapter는 `SlideIR.text_layer`, `SlideIR.raster_layer`, `SlideIR.residual_canvas`, `SlideIR.family_proposals`, `SlideIR.diagram_instances`를 읽을 수 있어야 한다.
  - next adapter는 `SlideIR.primitive_scene`, `SlideIR.connector_candidates`, `SlideIR.unattached_connector_evidence`도 읽을 수 있어야 한다.
- shim phase는 아직 열지 않았다.
  - 이유: 현재는 v3 IR과 family flow를 먼저 자라게 하는 편이 더 안전하기 때문이다.

---

## 14. 다음 단계

다음 단계는 `Phase 6: actual emit / eval adapter bootstrap`이다.

1. primitive scene을 broad emit 직전의 adapter 입력으로 내리는 최소 bridge를 만든다.
2. attachment-aware connector candidate를 solved connector contract로 잇는 최소 계층을 만든다.
3. debug artifact를 emit 전/후 비교 루프와 연결한다.
4. preserve-eval이 읽을 최소 adapter 범위를 정의하되 old runtime은 복구하지 않는다.

---

## 15. 검증 스냅샷

예시 검증 명령:

- `pytest tests/test_legacy_purge.py`
- `pytest tests/test_v3_phase1.py`
- `pytest tests/test_v3_phase2.py`
- `pytest tests/test_v3_phase3.py`
- `pytest tests/test_v3_architecture.py`
- `pytest tests/test_benchmark_report.py`

이번 단계 검증 스냅샷:

- purge / preserve-eval boundary test 통과
- v3 phase 1~3 contract test 통과
- v3 architecture boundary test 통과
- benchmark report regression test 통과
- v3 phase 4 inspection / detector / parser / connector evidence test 통과
- v3 phase 5 public surface / primitive scene / attachment bridge / debug artifact test 통과
