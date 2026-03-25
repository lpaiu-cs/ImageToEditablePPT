# ImageToEditablePPT v3 아키텍처 계획서

최종 업데이트: 2026-03-25  
상태: `Phase 2: text/raster separation 완료`

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
- `tests/test_stage_refactor.py`
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
- [ ] family registry 실제화
- [ ] config 기반 family on/off
- [ ] 첫 family detector skeleton
- [ ] 첫 family parser skeleton
- [ ] broad emit 없이 IR 수준까지 연결

**완료 조건**
- 최소 1개 family에 대해 detector → parser → DiagramInstance 흐름이 돌아야 한다.

---

### Phase 4. node/container + connector 기초
- [ ] node/container stabilization
- [ ] connector evidence 수집
- [ ] connector solving skeleton
- [ ] style token skeleton
- [ ] compose 기초

**완료 조건**
- node/container가 먼저 정해지고 connector가 나중에 붙는 구조가 코드상 드러나야 한다.

---

### Phase 5. emit 및 evaluation adapter
- [ ] editable PPT emit 연결
- [ ] residual/raster fallback emit 연결
- [ ] v3 → 기존 validation/eval adapter 추가
- [ ] benchmark run 가능한 최소 경로 확보

**완료 조건**
- v3 결과가 기존 평가 계층을 통해 비교 가능한 상태가 되어야 한다.

---

### Phase 6. family 확장 및 benchmarking
- [ ] MVP family 순차 구현
- [ ] per-family benchmark 비교
- [ ] GT-backed coverage 확장 검토
- [ ] residual/fallback 정책 정리

**완료 조건**
- 최소 MVP family 세트에 대해 품질과 실패 양상이 측정 가능해야 한다.

---

## 11. legacy 보존 / 삭제 정책

### 11.1 즉시 정책

- benchmark / validation / GT / workbench 자산은 유지한다.
- `Phase 0~1`에서 legacy 모듈을 물리적으로 삭제하지 않는다.
- 기존 import path를 무리하게 바꾸지 않는다.
- 현재 코어 변환 모듈은 v2 legacy 후보로 취급한다.

대상:

- `pipeline.py`
- `geometry.py`
- `objects.py`
- `selection.py`
- `graph.py`
- `emit.py`
- `fallback.py`
- `guides.py`
- `reconstructors/*`

### 11.2 격리 정책

- 장기적으로는 `src/image_to_editable_ppt/legacy_v2/`가 현재 v2 변환 코어의 집이 된다.
- `Phase 0~1`에서는 namespace만 만들고, 물리 이동은 compatibility shim이 준비된 이후에 한다.
- 재사용 가능한 유틸만 검토 후 `shared/`로 이동한다.
- v2 동작을 v3 내부로 복사하지 않는다.
- evaluation을 위해 필요한 경우에만 명시적 adapter를 둔다.

### 11.3 삭제 정책

다음 조건을 만족하기 전에는 legacy를 삭제하지 않는다.

- v3가 최소한의 benchmark parity를 확보
- 기존 validation/eval과 안정적으로 연결
- GT-backed run에서 최소한의 재현성과 비교 가능성 확보
- old import path를 사용하던 호출부 정리 완료

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
- 현재 활성 단계는 `Phase 2: text/raster separation`까지 완료된 상태다.
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
- legacy inventory가 문서화되었다.
  - `docs/legacy_inventory.md`
- `legacy_v2` 책임과 장기 이동 대상이 문서화되었다.
  - `src/image_to_editable_ppt/legacy_v2/README.md`
- shared 수용 기준이 문서화되었다.
  - `src/image_to_editable_ppt/shared/README.md`
- 테스트 분류 규칙이 문서화되었다.
  - `tests/README.md`
- v3 import 경계가 테스트로 강제된다.
  - `tests/test_v3_architecture.py`
- 아직 물리 이동하지 않은 legacy는 root 경로에 남아 있다.
  - 이유: 기존 public import path와 regression/eval 흐름을 깨지 않기 위해서
- compatibility shim은 아직 "전략 정의" 상태이며, 실제 re-export wrapper 이동은 다음 shim phase에서 수행한다.
- shared 후보는 아직 symbol-level 검토만 존재하며, 실제 이동된 코드는 없다.
  - 현재 후보: `BBox`, `Point`
- focused v3 architecture test가 추가되었고, legacy regression test도 유지되고 있다.
- shim phase는 아직 열지 않았다.
  - 이유: branch contract와 residual canvas 정의가 shim 작업보다 우선이기 때문이다.
- adapter 구현은 아직 하지 않았다.
  - 다만 future `eval_runtime/` adapter는 `SlideIR.text_layer`, `SlideIR.raster_layer`, `SlideIR.residual_canvas`를 읽을 수 있어야 한다.

---

## 14. 다음 단계

다음 단계는 두 축으로 나뉜다.

### 14.1 v3 구현 축

다음 구현 단계는 `Phase 3: family detector / parser 골격`이다.

1. `ResidualStructuralCanvas`를 첫 family detector 입력 계약으로 사용한다.
2. 첫 family detector skeleton과 첫 family parser skeleton을 broad emit 없이 IR 수준까지 연결한다.
3. text/raster provenance가 family parsing과 충돌하지 않도록 instance/source contract를 정리한다.
4. 아직 broad emit는 붙이지 않는다.

### 14.2 legacy shim 축

physical relocation이 필요해지는 시점에는 별도 shim phase로 진행한다.

1. root import path를 유지하는 얇은 re-export/wrapper 설계를 먼저 만든다.
2. `legacy_v2/`로의 실제 이동은 regression/eval이 안전하게 유지된다는 전제에서만 수행한다.
3. shared 추출은 symbol-level 검토를 다시 통과한 것만 진행한다.
4. Phase 종료 후 반드시 이 문서를 갱신한다.

---

## 15. 검증 스냅샷

예시 검증 명령:

- `pytest tests/test_v3_phase1.py`
- `pytest tests/test_v3_architecture.py`
- `pytest tests/test_benchmark_report.py`
- `pytest tests/test_stage_refactor.py`
- `pytest tests/test_pipeline.py`

### Phase 2 이후 추가 예정 검증

- text/raster separation contract test
- residual structural canvas test
- family registry on/off test
- first family parser IR test
