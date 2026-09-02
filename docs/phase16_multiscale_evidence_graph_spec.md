# Phase 16. Multi-scale Evidence Graph specification

작성일: 2026-09-02

상태: **specification only — 구현·튜닝·승인 실험 미시작**

동결 baseline: Git `3ae7caf2c6160bd84e4bc851212b22c536cb3348`

baseline candidate bundle SHA-256: `d9d232c44eed893e7c63baa30059f1728da9946077467d2d2e6a664f740023ac`

## 1. 결정

Phase 16의 이름은 **Multi-scale Evidence Graph(MEG)** 로 한다.

Phase 15의 source-pixel confirmation을 더 많은 threshold와 예외 규칙으로 확장하지 않는다. 대신 다음 네 증거를 원본 좌표계에서 독립적으로 만들고, 마지막에 하나의 구조 graph로 결합한다.

1. 여러 해상도에서 관측된 shape boundary/fill 증거
2. shape 사이의 containment·반복·정렬 계층
3. 실제 connector stroke가 이루는 path graph
4. 확정된 shape ROI에서 원본 해상도로 다시 읽은 OCR 합의

Phase 15 코드는 비교 baseline으로 보존한다. Phase 16은 명시적으로 opt-in한 새 provider와 실험 lock을 사용하며, 기존 기본 명령의 동작을 바꾸지 않는다.

제품 판정은 여전히 **사용자에게 남는 PowerPoint 재작도량**으로 한다. 객체 수나 OCR 인식 개수는 진단값일 뿐 승인 기준이 아니다.

## 2. 이 접근을 선택한 근거

### 2.1 실제 해상도 probe

동일한 복잡 입력 `input.png`를 frozen Phase 15 코드와 동일 bundle로 변환하되 입력 폭만 바꿔 PowerPoint로 재렌더했다.

| 처리 폭 | node | container | connector | OCR 보고 | 육안 관찰 |
|---:|---:|---:|---:|---:|---|
| 768 | 16 | 3 | 6 | 77/102 | 일부 큰 구조만 남고 RETRIEVE·Memory가 대량 누락됨 |
| 1280 | 20 | 3 | 7 | 65/81 | PERCEIVE·ACT 내부 box가 더 살아나지만 잘못된 대형 영역, RETRIEVE·Memory 누락, OCR 손상이 지속됨 |
| 2048 | 16 | 3 | 6 | 53/67 | 1280에서 보이던 일부 구조가 다시 사라지고 OCR 조합도 달라짐 |

객체 수와 OCR 개수는 해상도에 대해 단조롭게 좋아지지 않았다. 따라서 `--width 1280` 같은 한 개의 전역 해상도로 교체하는 것은 해결책이 아니다. 큰 panel, 작은 node, 얇은 connector, 작은 text가 서로 다른 scale에서 가장 잘 보이므로 **scale별 증거를 원본 좌표계로 되돌려 융합**해야 한다.

공개 개발 표본에서는 geometry 개수가 scale 사이에 비교적 안정적이었지만, 사진·plot에서도 잘못된 rectangle 후보가 여러 scale에 반복됐다. 따라서 scale 안정성만으로 diagram 여부나 객체 정답을 판정해서도 안 된다.

### 2.2 현재 구현의 구조적 한계

- `visual_geometry.py`는 gray `< 170`, 네 변의 연속 지지, 16단계 색 quantization, 전역 0.6% 면적 바닥에 크게 의존한다. gradient·shadow·부분 가림·작은 nested node에는 약하다.
- container는 titled panel이거나 하나의 내부 후보만 있어도 승격될 수 있다. 이는 복잡 입력의 잘못된 대형 영역을 설명한다.
- `visual_connectors.py`는 마주 보는 두 객체 사이의 열린 직선 gap만 본다. elbow, 분절 route, dotted route, 다른 객체와 겹치는 route는 표현할 수 없다.
- provider 경로는 구조를 먼저 만들고 난 뒤 downscaled connected-component text region에 OCR을 적용한다. geometry scale과 OCR scale이 결합되어 있고, OCR confidence는 문자열의 정확성을 보장하지 않는다.
- `connector / structure >= 0.20`은 알려진 사진 오탐을 막았지만 의미 정확도나 실제 편집 이득을 측정하지 못한다.

### 2.3 검토했지만 이번 Phase의 중심으로 선택하지 않은 방법

| 방법 | 판단 |
|---|---|
| Phase 15 threshold/예외 추가 | 이미 본 표본에 맞추는 rescue tuning이므로 금지한다. |
| 단일 1280/2048 처리 | 실제 probe가 비단조였으므로 기각한다. |
| 기존 `run-rel8`을 그대로 기본화 | 기존 구현은 straight pair와 불완전한 line mask에 의존해 실제 figure에서 실패했다. 다만 이것이 stroke graph 계열 전체의 실패를 뜻하지는 않는다. 실제 route component graph는 Phase 16의 새 가설로 검증한다. |
| detector를 즉시 재학습 | real mask/hierarchy annotation 없이 다시 학습하면 Phase 14의 domain gap을 반복한다. Phase 16 proposal ceiling이 실패할 때 별도 Phase로 새 preregistration한다. |
| vision-language model로 장면을 직접 생성 | 의미 추론은 늘 수 있지만 좌표 근거, 재현성, 환각 통제가 현재 우선순위와 맞지 않는다. 이번 Phase의 primary path가 아니다. |

## 3. 목표와 비목표

### 3.1 목표

1. gradient·shadow·부분 가림이 있는 rectangle/rounded rectangle/ellipse와 nested panel의 core 구조 recall을 높인다.
2. 직접 gap뿐 아니라 실제 픽셀로 이어지는 solid orthogonal multi-segment/elbow topology를 복원한다.
3. shape와 connector의 거짓 양성을 낮게 유지하면서, 낮은 연결 밀도의 정당한 diagram을 전체 blank로 만들지 않는다.
4. 확정된 shape ROI에서만 원본 해상도 OCR을 수행해 label 재입력량을 줄인다.
5. Phase 15보다 실제 PowerPoint 수정 작업량을 유의하게 줄인다.

### 3.2 비목표

- Phase 15 파일에 sample-specific 예외를 추가하는 일
- icon, logo, illustration, photo, texture 복원
- pixel-perfect style, shadow, gradient 재현
- 의미만으로 보이지 않는 box나 connector를 만드는 일
- arbitrary curve/freeform의 외형 복제
- 새 diagram family 확장
- 새 holdout을 본 뒤 같은 Phase에서 rescue tuning

Phase 16의 1차 지원 범위는 **rectangular/nested structural diagram + solid orthogonal topology**다. 곡선의 topology가 source에서 명확해도 최초 milestone에서는 진단으로만 남기고 출력하지 않는다. Dotted orthogonal route는 별도 sub-gate를 통과할 때만 포함한다.

## 4. 격리와 실행 계약

### 4.1 새 namespace

Phase 16 구현은 다음 새 namespace 아래에 둔다.

```text
src/image_to_editable_ppt/ml/phase16/
  models.py
  evidence_pyramid.py
  region_proposals.py
  hierarchy_solver.py
  stroke_graph.py
  ocr_consensus.py
  abstention.py
  provider.py
```

Phase 15의 `MLSlideIRProvider`, `visual_geometry`, `visual_connectors`는 수정하지 않는다. 공용 IR·adapter·emit writer는 기존 계약으로 표현할 수 없는 것이 확인된 경우에만 최소 확장한다.

### 4.2 명시적 opt-in

실험 CLI에는 다음과 같은 명시적 선택을 추가한다.

```powershell
.venv\Scripts\python.exe tools\convert_to_pptx.py figure.png `
  --experimental-reconstruction phase16-meg `
  --bundle workbench-ml\model_bundle.candidate.json `
  --allow-candidate-bundle
```

- 옵션이 없으면 frozen Phase 15 경로를 그대로 사용한다.
- Phase 16은 candidate bundle만 허용하고 canonical로 가장하지 않는다.
- `--no-gate`, source-pixel 근거 완화, holdout 재실행은 진단 artifact에 명시적으로 기록한다.

### 4.3 실험 lock

각 공식 run은 `phase16_experiment.lock.json`으로 다음을 묶는다.

- baseline/candidate Git SHA
- bundle 및 checkpoint SHA-256
- dev/holdout manifest와 annotation SHA-256
- 모든 algorithm setting과 threshold
- Python/OpenCV/RapidOCR/PowerPoint 버전
- input/output/IR/render SHA-256
- random seed와 A/B 표시 순서 seed

holdout run은 기존 output이 있으면 덮어쓰지 않고 중단한다.

## 5. 내부 데이터 모델

### 5.1 `RegionHypothesis`

각 shape 후보는 최소 다음 필드를 가진다.

```text
id
bbox_original
shape_kind
observed_scales
border_support[top,right,bottom,left]
border_continuity[top,right,bottom,left]
corner_support
inner_outer_color_delta
detrended_inner_texture
text_overlap
raster_overlap
detector_overlap
repetition_group_id
parent_candidate_ids
evidence_families
confidence
provenance
```

ML detector overlap은 독립 evidence가 아니라 약한 prior다. ML-only 후보는 emit하지 않는다.

### 5.2 `StrokeGraph`

connector evidence는 단일 bbox가 아니라 다음 graph로 유지한다.

```text
vertices: endpoint / bend / junction / arrowhead
segments: source-supported polyline fragments
components: connected stroke components
attachments: candidate shape boundary + approach side + distance
style: solid / dotted / unknown
direction: observed / unknown
occlusion_gaps: bridged gap + 허용 근거
```

최종 IR에는 하나의 semantic connector와 전체 `path_points`를 넘긴다. PowerPoint에서는 하나의 editable straight/elbow connector로 단순화하되 source/target topology와 방향을 보존한다.

### 5.3 내부 hierarchy

현재 public IR의 flat container membership을 바로 확장하지 않는다. 먼저 내부 containment DAG에서 parent/child와 role을 해결하고, emit 직전에 기존 node/container 객체로 flatten한다. 실제 편집 이득이 확인된 뒤에만 optional `parent_container_id` 같은 public IR 확장을 검토한다.

## 6. 파이프라인 상세

### 6.1 Stage A — evidence pyramid

원본 폭을 `W`라고 할 때 구조 proposal pyramid는 `min(W, 768)`, `min(W, 1280)`, `min(W, 2048)`의 중복 없는 level로 구성한다. Native 원본은 항상 별도로 보존해 최종 boundary refinement, stroke graph, OCR에 사용한다. `W > 2048`이면 native 전체에서 모든 region proposal을 다시 열거하지 않아 메모리와 scale-fragile 오탐을 제한한다.

- 작은 원본을 구조 검출 목적으로 전역 upsample하지 않는다.
- frozen learned detector와 diagram gate는 기존 계약과 비교 가능하도록 normalized width 768에서 한 번만 실행한다. 작은 원본의 이 upsample 결과는 weak prior일 뿐 source-pixel evidence로 세지 않는다.
- shape와 stroke evidence는 모든 level에서 계산해 원본 좌표로 역투영한다.
- final OCR은 항상 원본 ROI에서 수행하고, 작은 crop만 국소적으로 upsample한다.

각 level은 다음 map을 만든다.

- Lab luminance/chroma edge
- bilateral low-frequency background와의 residual
- detection-only text candidate soft mask (이 단계에서는 문자열을 emit하지 않음)
- raster/texture mask
- solid stroke mask
- dotted-component mask

### 6.2 Stage B — geometry proposal

Rectangle/rounded rectangle는 contour bbox 하나가 아니라 line·corner fitting으로 제안한다.

- 네 변이 모두 보이면 가장 강한 증거다.
- 한 변이 가려진 경우에는 나머지 세 변, 두 corner, 내부/외부 색 차, sibling 정렬 중 최소 두 종류가 추가로 필요하다.
- 두 opposite side만 보이는 후보는 반복 sibling group과 fill-annulus 증거가 모두 있을 때만 유지한다.
- missing side의 gap은 text/raster soft mask와 실제로 겹칠 때만 연장한다.
- fill은 quantized 단색이 아니라 저주파 gradient를 제거한 내부 texture와 안쪽/바깥쪽 ring의 Lab 차이로 평가한다.
- ellipse는 기존 fit residual 원칙을 유지하되 scale fusion을 적용한다.
- icon·glyph 크기의 singleton은 geometry evidence만으로 node가 되지 않는다.

Scale별 후보를 원본 좌표에서 clustering하고 robust median boundary를 사용한다. `scale_support`, boundary MAD, size-appropriate level을 함께 기록한다. 여러 scale에 보였다는 사실은 한 종류의 증거일 뿐이며, 사진의 반복 오탐을 막기 위해 edge/fill/hierarchy/path 중 다른 증거가 반드시 필요하다.

### 6.3 Stage C — containment/hierarchy solve

모든 region 후보로 containment DAG를 만든다.

- container 승격은 `titled header`, `서로 다른 child 2개 이상`, `반복 child group` 중 하나와 강한 외곽 증거를 함께 요구한다.
- 내부 후보 하나만 있다는 이유로 container가 되지 않는다.
- leaf node는 자체 경계/fill과 text, connector attachment, coherent repetition group membership 중 하나를 추가로 가져야 한다.
- 후보끼리 큰 면적을 겹치면서 containment 관계가 아니면 conflict로 처리한다.
- 선택 objective는 source evidence와 예상 편집 이득을 더하고, overlap conflict·unsupported extrapolation·객체 복잡도를 뺀다.
- 잘못된 대형 region 하나가 여러 정확한 child를 덮는 해는 허용하지 않는다.

Solver는 선택된 각 객체에 `accepted_reason`과 `rejected_reason`을 남겨 육안 검토가 가능해야 한다.

### 6.4 Stage D — source-resolution stroke graph

선택된 shape를 기준으로 원본 해상도 stroke map을 다시 만든다.

1. text/raster 내부 잉크를 soft-mask한다.
2. shape border를 제거하되 attachment 후보 주변의 작은 halo는 보존한다.
3. solid stroke를 in-repo deterministic thinning(Zhang–Suen 또는 동등한 morphological skeleton)으로 skeletonize하고 endpoint/bend/junction에서 graph segment로 나눈다. 새 heavyweight dependency는 추가하지 않는다.
4. endpoint가 shape boundary로 접근하는 각도와 거리, component 연속성으로 attachment 후보를 만든다.
5. 두 endpoint를 공유하는 실제 component path가 있을 때만 topology를 생성한다.
6. line이 text에 가려진 gap은 양쪽 segment가 collinear하고 gap 대부분이 알려진 text mask와 겹칠 때만 bridge한다.
7. arrowhead는 원본 ROI의 contour/폭 profile로만 판정한다. 불명확하면 undirected line으로 남긴다.

최초 milestone에서 허용하는 route:

- direct horizontal/vertical
- solid orthogonal elbow/multi-segment
- 동일 component에서 source/target이 분명한 branch

Dotted orthogonal route는 정렬된 component가 3개 이상이고 간격/길이 변동이 dev에서 정한 범위 안에 있을 때만 별도 sub-gate로 연다. Curve/free route는 이번 Phase의 출력 범위 밖이다.

기존 `run-rel8`의 pair classifier는 사용하지 않는다. 다만 실제 stroke component가 어떤 node boundary를 함께 만지는지 보는 component-level 아이디어는 새 deterministic graph에서 검증한다.

### 6.5 Stage E — shape-conditioned OCR consensus

OCR은 geometry와 topology가 확정된 후 text 생성에만 사용한다.

각 node와 titled header ROI에 대해 원본에서 다음 view를 만든다.

- source RGB
- grayscale + local contrast
- inverted grayscale
- adaptive binary

각 view의 OCR 결과를 원본 좌표의 line box로 되돌린다.

출력 규칙:

- 정규화한 문자열이 독립 view 2개 이상에서 일치하면 가장 높은 품질의 원문을 사용한다.
- 한 view만 결과를 내면 confidence `>= 0.92`, ROI 내부 완전 포함, 다른 view의 모순 없음이 모두 필요하다.
- 문자 집합/backend coverage가 확인되지 않은 언어는 blank로 둔다.
- 사전·LLM·caption을 이용한 의미적 철자 교정은 하지 않는다.
- OCR disagreement와 confidence는 provenance에 남긴다.
- standalone text는 slide title 또는 확정된 connector label 역할이 아니면 생략한다.

OCR arm이 실패해도 geometry/topology 결과까지 폐기하지 않는다. 해당 label을 blank로 내보내는 것이 정식 fallback이다.

### 6.6 Stage F — component utility and abstention

Phase 16에서는 전역 `connector / structure` 비율을 사용하지 않는다. coarse learned diagram gate 뒤에 구조 component 단위의 utility gate를 적용한다.

다음 중 하나를 만족하는 component만 출력 후보가 된다.

1. source-supported shape 2개 이상과 두 shape를 잇는 attached stroke path
2. source-supported container 1개와 child shape 2개 이상
3. titled container와 source-supported 반복 child group

각 객체와 path는 앞 단계의 독립 증거 조건을 이미 통과해야 한다. 개수만 맞추어 component를 통과시킬 수 없다.

- 여러 component 중 일부만 통과하면 그 일부만 출력한다.
- 통과 component가 없으면 blank PPTX로 기권한다.
- 고립 box, plot frame, table cell, 사진 texture component는 출력하지 않는다.
- low-connectivity diagram이 container+children 증거를 가지면 전역 ratio 때문에 버려지지 않는다.

Hard-negative scene cue도 함께 적용한다.

- shared border로 빽빽하게 채워진 row/column grid에 connector attachment가 없으면 table-like로 거절한다.
- 긴 두 axis, 반복 tick, curve/scatter mark가 중심이고 shape-to-shape path가 없으면 plot-like로 거절한다.
- raster/texture mask가 component 내부의 대부분을 차지하면 photo/illustration-like로 거절한다.

이 cue는 독립 source evidence를 지우는 임의 blacklist가 아니라, 새 non-diagram dev annotation에서 false positive 유형별로 검증하고 holdout 전에 동결한다.

## 7. 데이터와 annotation 계약

### 7.1 기존 자료의 역할

- `input.png`, 공개 5종, 기존 real benchmark/holdout은 모두 **소비된 development evidence**다.
- regression과 디버깅에는 사용할 수 있지만 Phase 16 승인에는 사용할 수 없다.
- 기존 min/max object-count annotation은 의미적 정답으로 간주하지 않는다.

### 7.2 새 split

구현 시작 전에 다음 manifest를 먼저 만든다.

```text
benchmarks/phase16_dev_v1/manifest.json
benchmarks/phase16_holdout_v1/manifest.json
```

최소 구성:

- dev: diagram 20개 이상 + non-diagram 20개 이상
- confirmatory holdout: diagram 12개 이상 + non-diagram 12개 이상

Diagram은 다음 세 strata를 균형 있게 포함한다.

1. simple/direct orthogonal
2. nested/gradient/shadow hierarchy
3. connector-dense orthogonal/elbow

Holdout diagram에는 low-connectivity지만 정당한 diagram을 최소 2개 포함한다. Non-diagram은 plot, table, application screenshot, photo, multi-panel illustration을 각각 포함한다.

같은 논문, 같은 figure의 crop/variant, perceptual near-duplicate는 dev와 holdout에 나뉘어 들어갈 수 없다. source revision, row, content SHA-256, perceptual hash, redistribution 조건을 manifest에 고정한다.

### 7.3 annotation v2

각 diagram은 최소 다음을 수동 annotation한다.

- structural object: `id`, `role(node/container)`, `shape_kind`, `bbox`, `parent_id`
- importance: `core`, `secondary`, `excluded`
- label: 원문, legibility, editable 필요 여부
- connector: source/target, direction, path class, core 여부
- excluded region: icon/logo/photo/illustration/decoration
- 허용되는 omission과 ambiguity note

Core는 사용자가 그림의 구조를 이해하거나 다시 그릴 때 반드시 필요한 객체/관계다. Secondary는 복원되면 좋지만 제품 통과를 좌우하지 않는다. Excluded는 출력하면 false positive다.

두 번째 annotation pass에서 object role, connector endpoints, excluded region을 재검토하고 disagreement를 해소한다. annotation validator는 dangling endpoint, containment cycle, bbox 범위, duplicate id, source hash를 검사한다.

## 8. 평가 계약

### 8.1 `edit_cost_v2`

기존 `edit_operations_lower_bound`를 다음 vector로 확장한다.

- missing core/secondary object creation
- wrong object deletion
- geometry move/resize/kind correction
- missing/wrong connector creation/deletion
- connector reroute/direction correction
- endpoint rebind
- label retype/delete
- redundant text deletion

Raw vector는 항상 보존한다. 하나의 점수로 합칠 weight는 임의로 정하지 않고, 실제 PowerPoint에서 각 작업을 최소 10회 반복해 측정한 median seconds를 `operation_time_calibration.json`에 동결한 뒤 사용한다. calibration이 없으면 단일 weighted score를 승인 근거로 쓰지 않는다.

### 8.2 구조 지표

객체 개수 대신 annotation match로 다음을 보고한다.

- core/secondary object precision, recall, bbox IoU
- container precision/recall과 hierarchy accuracy
- connector topology precision/recall
- emitted direction precision와 coverage
- label exact precision와 coverage
- unbound endpoint count
- excluded-region false positive count
- non-diagram emitted object count

Precision은 이 프로젝트의 우선순위상 recall보다 먼저 gate한다.

### 8.3 육안·실사용 평가

모든 공식 sample은 원본, Phase 15 render, Phase 16 render를 같은 크기로 만든다. A/B 위치와 이름은 lock의 seed로 가린다.

육안 판정 항목:

- 잘못된 구조가 새로 생겼는가
- 핵심 구조가 충분히 남았는가
- topology를 다시 그려야 하는가
- label을 다시 입력해야 하는가
- blank보다 유용한가
- 실제 수정 출발점으로 선택할 것인가

Confirmatory diagram 중 최소 6개는 실제 PowerPoint correction task를 counterbalanced 순서로 수행해 completion time과 작업 vector를 함께 기록한다.

## 9. 단계별 실험과 중단 규칙

### Phase 16.0 — preregistration/data freeze

완료 조건:

- dev/holdout manifest와 annotation v2 동결
- baseline commit/bundle/output 재생성
- operation calibration과 visual A/B rubric 동결
- 모든 hash를 experiment lock에 기록

이 단계가 끝나기 전에 Phase 16 algorithm tuning을 시작하지 않는다.

### Phase 16.1 — proposal ceiling

Emit하지 않고 모든 scale의 raw geometry/stroke proposal을 annotation과 비교한다.

개발 gate:

- core object proposal recall `>= 0.90`
- solid orthogonal connector의 endpoint-pair proposal recall `>= 0.80`
- 모든 proposal에 source evidence overlay와 provenance 존재

이 ceiling을 통과하지 못하면 selection threshold를 만지지 않는다. Multi-scale classical evidence 가설을 종료하고, real mask-supervised learned proposal은 새 Phase로 preregister한다.

### Phase 16.2 — hierarchy selection

개발 gate:

- object precision `>= 0.90`
- container precision `>= 0.90`
- core object recall `>= 0.65`
- excluded-region false positive `0`
- `input.png`에서 Phase 15의 잘못된 대형 region을 유지하지 않음

### Phase 16.3 — stroke graph

개발 gate:

- 지원 범위 내 connector topology precision `>= 0.90`
- solid orthogonal topology recall `>= 0.60`
- direction을 emit한 connector의 direction precision `>= 0.90`
- container border를 connector로 만든 사례 `0`
- Phase 15보다 unbound endpoint count가 증가하지 않음

Dotted sub-gate가 별도로 실패하면 dotted 출력만 닫고 solid graph 결과는 유지한다.

### Phase 16.4 — OCR consensus

개발 gate:

- emitted label exact precision `>= 0.95`
- legible core label coverage `>= 0.60`
- unsupported-language/불일치 문자열의 추측 출력 `0`

실패하면 Phase 16 OCR을 blank fallback으로 닫고 geometry/topology만 다음 단계로 보낸다.

### Phase 16.5 — integrated development decision

개발 gate:

- Phase 15 대비 median calibrated edit cost `>= 25%` 감소
- diagram의 `>= 70%`에서 Phase 16 cost가 더 낮음
- non-diagram 전부 blank
- blinded visual audit에서 misleading structure `0`
- warm-cache wall time median이 Phase 15의 `2배` 이내

통과 후 모든 setting을 잠그고 holdout을 실행한다. 이 시점 이후 feature, threshold, OCR rule을 변경하지 않는다.

### Phase 16.6 — one-shot confirmatory holdout

최종 GO 조건:

1. 실행 실패 `0`
2. non-diagram reject `100%` (최소 표본 구성에서는 `12/12`)
3. pooled object precision `>= 0.90`, connector topology precision `>= 0.90`
4. median core object recall `>= 0.65`, solid orthogonal topology recall `>= 0.60`
5. emitted label exact precision `>= 0.95`
6. Phase 15 대비 median calibrated edit cost `>= 30%` 감소
7. holdout diagram의 `>= 75%`에서 Phase 16 cost가 더 낮음
8. 실제 correction task median completion time `>= 30%` 감소
9. blinded visual audit에서 misleading structure `0`, usable partial 이상 `>= 75%`
10. Phase 15보다 unbound endpoint와 excluded-region false positive가 증가하지 않음

하나라도 실패하면 Phase 16은 NO-GO로 종료한다. 같은 holdout에서 threshold를 고치거나 표본을 제외하지 않는다. 새 가설은 새 Phase 이름, 새 preregistration, 새 holdout을 요구한다.

## 10. 필수 diagnostics

각 sample은 최소 다음 artifact를 남긴다.

```text
00_source.png
01_scale_maps/<scale>/*.png
02_raw_region_proposals.json
03_region_proposal_overlay.png
04_containment_graph.json
05_selected_regions.json
06_selected_regions_overlay.png
07_stroke_graph.json
08_stroke_graph_overlay.png
09_ocr_candidates.json
10_scene_ir.json
11_output.pptx
12_powerpoint_render.png
13_edit_cost_v2.json
14_visual_audit.json
run.lock.json
```

Accepted object/connector를 클릭하지 않아도 어떤 scale과 pixel evidence 때문에 남았는지 overlay와 JSON으로 추적할 수 있어야 한다.

## 11. 테스트 요구사항

### Unit fixtures

- gradient-filled panel
- partial border occluded by text
- nested panel with two children
- one-child false container
- small document/icon exclusion
- scale-stable and scale-fragile rectangle
- direct/elbow/multi-segment connector
- connector crossing a panel border
- text-occluded collinear gap
- dotted aligned components
- uncertain arrowhead -> undirected fallback
- OCR multi-view agreement/disagreement
- component-level partial output and blank abstention

### Integration

- default CLI가 Phase 15 provider를 그대로 사용함
- Phase 16은 explicit opt-in 없이는 호출되지 않음
- Phase 15 regression fixture의 canonicalized IR가 변하지 않음
- all Phase 16 accepted primitives have provenance
- PPTX objects are native editable shapes/text/connectors
- PowerPoint rerender and endpoint movement smoke test
- `git diff --check`와 전체 `pytest`

## 12. 구현 순서와 deliverables

1. manifest/annotation v2 schema, validator, experiment lock
2. evidence pyramid와 raw proposal ceiling runner
3. region fusion/containment solver
4. source-resolution stroke graph
5. component abstention
6. OCR consensus
7. `edit_cost_v2`, render contact sheet, blinded audit form
8. explicit Phase 16 provider/CLI integration
9. development freeze
10. one-shot holdout 및 Phase 16 freeze report

예상 주요 파일:

```text
docs/phase16_multiscale_evidence_graph_spec.md
benchmarks/phase16_dev_v1/manifest.json
benchmarks/phase16_holdout_v1/manifest.json
src/image_to_editable_ppt/ml/phase16/*
tools/validate_phase16_annotations.py
tools/run_phase16_proposal_ceiling.py
tools/run_phase16_benchmark.py
tools/calibrate_edit_operation_time.py
tests/test_phase16_*.py
```

## 13. Definition of Done

Phase 16은 코드를 많이 추가했다고 완료되지 않는다. 다음이 모두 충족돼야 한다.

- Phase 15 baseline이 재현되고 기본 경로가 변하지 않는다.
- 새 데이터·annotation·threshold·실험 lock이 holdout 전에 동결된다.
- geometry, hierarchy, topology, OCR arm의 결과와 실패가 분리돼 있다.
- 원본 대비 PowerPoint 재작도량과 실제 correction time이 Phase 15보다 줄어든다.
- non-diagram과 excluded region은 계속 공백이다.
- 육안 audit와 정량 gate가 같은 결론을 낸다.
- holdout 실패 뒤 rescue tuning 없이 GO 또는 NO-GO로 동결한다.

최종 원칙:

> **해상도를 높여 더 많이 잡는 것이 아니라, 여러 scale에서 관측된 근거를 graph로 합쳐 사용자가 실제로 고칠 구조만 남긴다.**
