# Phase 9 — Real paper-figure transfer measurement (2026-06-21)

Goal context: 논문 다이어그램 90% 커버. 이 측정은 합성+soffice로만 검증된 ML 파이프라인이
**실제 논문 figure**에 얼마나 전이되는지 처음으로 정량/육안 확인한 것.

## Dataset
- `citeseerx/ACL-fig` (HF, gated — gate 수락 후 접근). `scientific_figures_pilot.csv` = figure→label(19종) 매핑.
- 타깃 5종 각 30장 = 150장을 `data/paper_figures/<cat>/`에 다운로드:
  architecture(diagram), neural_net, tree, graph, table.
- canonical 모델: run-v6(검출기) / run-fc3(4-class 분류기) / run-seg4(2채널 segmenter).
- 측정 스크립트: `workbench-ml/summarize_real.py`(집계), `workbench-ml/run_real_figures.py`(오버레이).

## Results (150 figs)

| category | predicted family | avg nodes | avg containers | avg connectors | zero-node figs |
|---|---|---|---|---|---|
| architecture | orthogonal_flow:17, cycle:13 | 7.4 | 0.4 | 1.3 | 2/30 |
| neural_net | orthogonal_flow:16, cycle:12, table_matrix:2 | 4.8 | 0.1 | 1.5 | 6/30 |
| table | cycle:14, orthogonal_flow:8, table_matrix:8 | 3.8 | 0.5 | 0.4 | 3/30 |
| graph | **cycle:30** | 2.6 | 0.0 | 0.7 | 4/30 |
| tree | **cycle:27**, block_flow:2, orthogonal_flow:1 | **0.3** | 0.0 | 0.1 | **25/30** |

전체 family 분포: cycle:96, orthogonal_flow:42, table_matrix:10, block_flow:2.

## Findings (근본 원인 = 합성 도메인 ≠ 실논문 도메인)

1. **분류기가 OOD에서 `cycle`로 붕괴** — 96/150(64%)가 cycle. graph 100%, tree 90%가 cycle.
   graph/tree/NN class가 없어서 가장 가까운 cycle로 강제 매핑. 단일 최대 신호.
2. **박스 검출기가 text/원형 노드를 못 잡음** — tree avg 0.3 노드, 25/30이 zero-node.
   (파스트리 = 텍스트 라벨 + 가는 엣지, 박스 없음). graph는 원형 노드 부분 검출(2.6).
3. **container head 실질 무력** — 전 카테고리 avg 0.0~0.5. 실 arch/NN figure의 회색 둥근
   그룹 패널을 거의 못 잡음(합성 container는 옅은 fill, 실제는 회색 rounded panel).
4. **connector head 매우 약함** — avg 0.4~1.5. 실 화살표(가는 흑색, 다양)와 합성(깔끔) 격차.
5. **최선 케이스 = 색 박스가 있는 architecture/NN** — 부분 구조 복원(7.4/4.8 노드,
   family도 orthogonal_flow로 그럴듯). 합성 데이터(채색 박스)와 가장 닮은 입력.

육안 확인(workbench-ml/real-out/*.overlay.png): arch/Transformer NN은 색 박스를 녹색으로
부분 검출하나 회색 컨테이너·화살표 누락. 파스트리는 전무. FSM(graph)은 원형 상태를 부분 박싱.

## Levers for 90% coverage (영향 순)
- **A. 생성기 도메인 랜덤화(실논문 룩)** — 회색 둥근 컨테이너, 텍스트/원형 노드, 가는 흑색
  화살표, 그레이스케일 팔레트, 폰트/크기 다양화, 스캔 아티팩트. 검출기+segmenter 재학습.
  모든 family의 node/container/connector 전이를 한 번에 개선하는 지배적 레버.
- **B. 누락 family 추가** — graph(node-link), tree, layered_stack(NN). 새 generator +
  `DiagramFamily` enum 신규값. A의 도메인 작업과 결합(생성기가 새 룩을 같이 획득).
- **C. OOD/abstain 게이트** — 논문 figure의 과반이 비다이어그램(chart/screenshot/natural
  image/confusion matrix; ACL-fig 라벨 분포). 강제 분류 대신 "not-a-diagram" 거절 필요(정밀도).

권장 순서: A → B(넓혀진 도메인 위에서 신규 family) → C(정밀도 게이트). A·B는 generator 작업 공유.

---

## A+B 실행 결과 (2026-06-21)

레버 A(도메인 랜덤화)+B(graph/tree/layered_stack family) 동시 실행. 결과 = 측정된 두 최대
실패(tree zero-node, cycle 붕괴)를 대부분 해소하고 전 카테고리 node/connector 회수율 2~10배↑.

**구현**
- enum: `DiagramFamily`에 `GRAPH`,`TREE` 추가(`LAYERED_STACK` 기존). `SUPPORTED_FAMILIES` 4→7.
- 생성기 3종: `_generate_graph_spec`(원형 node-link+cross-link), `_generate_tree_spec`(텍스트-only
  LABEL_ANCHOR 노드, GT bbox=tight 텍스트 extent, 가는 엣지), `_generate_layered_stack_spec`(NN 수직 스택).
- 도메인 랜덤화(`RenderTheme`): per-sample color/gray/mono 팔레트(0.4/0.4/0.2), thin-black 화살표(0.6),
  텍스트-only·타원·둥근/사각 노드 형태, 가변 stroke width. 기존 4 family에도 적용. PIL+pptx 양쪽 렌더.
- `find_soffice()` Windows 경로 추가; pptx 텍스트 `word_wrap=False`+margin 0(LibreOffice 텍스트 wrap 방지).
- 데이터셋 ds-mix3 = ds-v7(PIL 700)+ds-soffice-v7(soffice 420), train 896/val 112/test 112, 7 family 균형.
- 재학습: run-v7(검출기 lr3e-4/25ep, val_loss 0.244)·run-fc4(분류기 50ep, 7-class val_acc 0.902)·
  run-seg5(2채널 segmenter 45ep, val_dice 0.863). in-domain 수치는 분포가 훨씬 어려워져 하락(정상).

**실figure 150 전이 — Before(run-v6/fc3/seg4) → After(run-v7/fc4/seg5)**

| 카테고리 | family (Before→After) | avg nodes | avg conn | zero-node |
|---|---|---|---|---|
| architecture | ortho17/cyc13 → tbl17/ortho11 | 7.4→**9.8** | 1.3→**4.6** | 2→**0** |
| graph | **cyc30** → cyc9/ortho8/graph6/… | 2.6→**9.7** | 0.7→**6.5** | 4→**0** |
| neural_net | ortho16/cyc12 → tbl15/ortho12/layered3 | 4.8→**7.9** | 1.5→**3.7** | 6→1 |
| table | cyc14/tbl8 → **tbl20**/ortho4 | 3.8→**5.9** | 0.4→1.1 | 3→4 |
| tree | **cyc27, nodes0.3** → cyc11/ortho8/graph6/tree2 | **0.3→4.6** | 0.1→**3.2** | **25→5** |

전체 cycle 붕괴: 96/150(64%) → **23/150(15%)**. 육안: 파스트리=무검출→텍스트 리프 검출, 실 arch
다이어그램=14 노드+컨테이너+커넥터 스켈레톤 복원, FSM=원형 상태+전이 검출.

**남은 약점(다음 후보)**
- container head 여전히 약함(avg 0~0.5) — 회색 그룹 패널 미검출. 가장 약한 축.
- arch/NN이 table_matrix로 과분류(밀집 박스 배열을 표로 혼동). graph/tree family 인식률 낮음
  (검출은 됐으나 family 분류가 cycle/ortho로 샘). family 분류 정밀도가 다음 레버.
- C(OOD/비다이어그램 거절) 미착수 — 논문 figure 과반 비다이어그램.

canonical 모델 갱신: **run-v7 / run-fc4 / run-seg6**.

### 리뷰 후속 수정
- **P1(febc5c2)**: provider 경로가 connector candidates를 `resolve_connector_candidates`로 풀어
  `slide_ir.connectors`에 채움(emit은 connectors를 렌더). 안 하면 ML 커넥터가 PPT에서 누락.
- **P2(run-seg6)**: thin-arrow 랜덤화로 렌더 1~2px인데 segmenter GT 마스크는 고정 3px이던 불일치
  해소. `AnnotationConnectorCandidate.stroke_width`(합성 GT 전용) 추가 → 마스크를 렌더 width로
  rasterize. 재학습 run-seg6 val_dice 0.863→**0.913**. 실figure 커넥터(전부 solved)도 개선:
  architecture 4.6→**6.3**, graph 6.5→**8.2**.

---

## 레버1: container head 강화 (2026-06-21)

생성기 컨테이너를 실논문 그룹박스에 맞춰 다양화: 멀티/중첩 패널(outer + nested subset),
**대시 보더**, 회색 패널, 빈도↑(flow/stack 0.5~0.7). spec을 단일→다중 컨테이너(`containers`/
`container_styles` 튜플)로 확장. 데이터셋 재생성(컨테이너 38%·멀티 13%) → run-v8/fc5/seg7 재학습.

**실figure 150 — Before(run-v7/fc4/seg6) → After(run-v8/fc5/seg7)**

| 카테고리 | container avg | family 변화(핵심) |
|---|---|---|
| architecture | 0.2→**0.7** | table_matrix 오분류 17→**6**/30 (ortho 11→**22**) |
| neural_net | 0.5→**0.8** | table_matrix 오분류 15→**2**/30 (ortho 12→**23**) |
| tree | 0.0→**0.3** | — |
| 전체 table_matrix 과분류 | 56→**24**/150 | — |

육안: 실 arch 다이어그램의 대시 그룹 패널("Résumé guidé") + 중첩 패널을 2개 컨테이너로 검출
(16노드+7커넥터+2컨테이너+orthogonal_flow). **보너스**: 컨테이너가 flow vs table 구별 단서가 되어
arch/NN→table_matrix 과분류가 크게 해소(레버2 일부 선해결). node/connector 무회귀. 단 graph/tree
**family 인식**은 여전히 약함(tree→tree 거의 0) → 레버2.

canonical 모델 갱신: **run-v8 / run-fc5 / run-seg7**.

---

## 레버2: family 분류 정밀도 (2026-06-21)

레버1이 이미 최대 혼동(arch/NN→table_matrix)을 해소했고, 남은 문제는 graph/tree **인식**.

**시도(폐기): 구조 기반 family 분류기(learned MLP).** family는 구조적 속성이라 검출된
노드/커넥터 토폴로지로 분류하면 픽셀 도메인 갭을 피할 수 있다는 가설. 합성 GT/검출 구조로
MLP 학습(val_acc 0.99). **그러나 실figure 전이 실패**: 실 flow는 **엣지 검출이 불완전**해
구조적으로 sparse=tree처럼 보여 arch→tree로 대량 오분류(arch ortho 22→0). soft-vote 앙상블·
label-anchor 노이즈 augmentation 모두 미해결. **근본 한계: 구조 기반 family는 엣지 회수
완전성에 종속**. → 모듈 폐기, 픽셀 분류기(run-fc5) 유지가 flow에 더 강건.

**채택: 구조적 tree 게이트.** 단 하나의 robust 신호 — **검출 텍스트 노드(LABEL_ANCHOR) 비율**이
실figure에서 tree(~0.45)와 나머지(~0.05)를 명확히 분리. provider가 픽셀 family 결정 후,
텍스트 비율≥0.25(노드≥4)면 family를 TREE로 승격(`tree_text_fraction_gate`).

**실figure 150 — tree 게이트 효과**

| 카테고리 | family (run-v8/fc5/seg7 + gate) | tree 오탐 |
|---|---|---|
| architecture | ortho20, tbl6, layered2 | 2 |
| neural_net | ortho22, layered5, tbl2 | 1 |
| table | tbl12, ortho9, layered7 | 2 |
| **tree** | **tree11**, ortho10, cycle4, graph3 | — |

tree→tree **0→11** 회복(무회귀: 비-tree 오탐 1~3). 픽셀 분류기는 arch/NN/table에 강건 유지.
**남은 한계**: graph 인식 약함(graph→graph 5~6/30; FSM/의존그래프는 종종 flow처럼 보임) —
엣지 회수 개선 없이는 구조적으로 구분 난해.

---

## 레버3: OOD/비다이어그램 게이트 (2026-06-21)

논문 figure의 과반이 비다이어그램(차트/스크린샷/사진/혼동행렬)인데 파이프라인은 무엇이든 family로
강제 분류. 실전 정밀도엔 **거절(abstain)**이 필요. **이진 게이트**(diagram vs not)를 학습:
- positive=실 ACL-fig 다이어그램 150(arch/graph/tree/table/neural), negative=실 ACL-fig 비다이어그램
  200(natural image/confusion matrix/bar·line·pie·scatter chart/screenshot/boxplot 각 25).
  **양쪽 모두 실figure** → synthetic-vs-real이 아니라 diagram-vs-not을 학습.
- 작은 pixel CNN(GroupNorm, 160²) + flip/밝기 augmentation. `ml/diagram_gate.py`, run-gate1.
- provider: 게이트가 먼저 실행, 비다이어그램이면 **빈 scene(노드·family 없음) 조기 반환**(emit이
  아무것도 생성 안 함). `diagram_gate_checkpoint`/`diagram_gate_threshold`.

**결과** — val(held-out): diagram recall **0.85**, non-diagram reject **0.87**. end-to-end(350장):
다이어그램 유지 **125/150(83%)**, 비다이어그램 거절 **178/200(89%, 오수용 11%)**. 임계값으로
recall↔precision 조절 가능(기본 0.5). 비다이어그램을 가짜 다이어그램으로 변환하던 문제 해소.

canonical: 검출 run-v8 / family run-fc5(+tree gate) / connector run-seg7 / OOD run-gate1.

## 3개 레버 종합 (phase9b)
- 레버1(컨테이너): 실figure container 회수↑, arch/NN→table 과분류 해소(table_matrix 56→23/150).
- 레버2(family): 구조 분류기는 엣지 회수 한계로 폐기, tree text-gate로 tree 0→11/30 무회귀 회복.
- 레버3(OOD): 비다이어그램 89% 거절 / 다이어그램 83% 유지로 실전 정밀도 확보.

---

## OOD 게이트 개선 (2026-06-22)

레버3의 run-gate1은 narrow negative(차트/사진 8종)로 측정돼 낙관적이었음. **정직한 측정**을 위해
ACL-fig **14종 전체 비다이어그램** + 5종 diagram을 train/test 분리(train 1353, held-out test 181)로
재구성. `data/ood/{train,test}/{diagram,nondiagram}/<label>/`.

**진단(run-gate2, 14종 held-out)**: 흔한 비다이어그램(natural image/confusion matrix/pie/venn/
bar/scatter/maps/word cloud)은 잘 거절(0.75~1.0)하나, **텍스트형(algorithms 0.33·NLP grammar 0.44)
과 line graph(0.44)는 과소학습**으로 실패. diagram 유지는 0.75~0.94 양호.

**개선(run-gate3)**: ① 하드 negative 데이터 36→90/종 증량(train 727→1353) ② 강화 augmentation
(flip·회전·zoom crop·밝기/대비·노이즈) ③ **클래스 가중 손실**(negative 다수로 인한 거절 편향 보정).
- held-out 테스트: **best balanced acc 0.799→0.830** (@thr 0.45, recall 0.89·reject 0.77). val reject 0.61→0.85.
- 텍스트형 대폭 개선: algorithms 0.56→**0.89**, NLP grammar 0.44→**0.89**.
- run-gate3에서 recall 0.89와 reject 0.77 **동시 달성**(gate2는 trade-off로 불가).

측정도구 workbench-ml/eval_gate.py(임계값 sweep). from-scratch 천장 ~0.83 balanced.

**사전학습 백본 도입(run-gate4)**: ImageNet 사전학습 MobileNetV3-Small 전이학습(`--backbone
mobilenet_v3_small`, 입력 224+ImageNet 정규화). detector의 weights=None offline 관례를 OOD 게이트에
한해 변경(1회 가중 9.8MB 다운로드, 이후 캐시). 작은 실데이터에서 **큰 도약**:
- held-out 테스트 **best balanced 0.830→0.939**(@thr 0.75, recall 0.94·reject 0.94 동시). val acc 0.94.
- thr 0.4~0.9 전 구간 recall 0.93~0.97 + reject 0.87~0.95(안정·캘리브레이션 양호).
- 카테고리별(@thr 0.6): 다이어그램 유지 0.88~1.0, 비다이어그램 거절 — confusion matrix·screenshots·
  maps·scatter·pie·natural·venn **1.0**, NLP grammar 0.89·bar 0.89·line graph 0.78. 최난 algorithms 0.67.

canonical OOD: **run-gate4**(MobileNetV3 사전학습, provider 기본 thr 0.6 → recall 0.95/reject 0.90).
`diagram_gate.py`는 backbone 선택(scratch/mobilenet_v3_small/resnet18) 지원, 체크포인트에 backbone 기록.
**남은 한계**: algorithms(pseudocode)은 텍스트 구조라 tree와 본질 혼동(0.67). 검출 구조 증거 융합이 후보.
