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

canonical 모델 갱신: **run-v7 / run-fc4 / run-seg5**.
