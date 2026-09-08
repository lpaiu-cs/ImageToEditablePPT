# R15 육안 손실 감사 — 구조가 너무 적게 남는 문제

## 결론

**현재 closed-native-v4는 사용자 기준 미달이다.** 원본 CogBot에서 핵심 노드17개 중9개(52.9%)가 없고, 명확히 추적해 장부에 올린 연결20개 중16개(80%)가 없다. 남은 노드8개도 본문까지 유지한 것은4개, 설명문 일부 누락3개, 승인 정책상 빈 카드1개다. 편집할 수 있는 객체가 있다는 사실과 수작업을 충분히 줄였다는 사실은 다르다.

R14의 사진 대조군 통과는 위양성 방어 검증이었다. 복잡한 도식의 구조 재현율 또는 사용자 수정시간에 대한 합격 판정으로 사용할 수 없다. 이번 감사는 이 구분을 수치와 실제 렌더로 명확히 한다.

## 1. 무엇을 실제로 봤는가

- 변환 구성: `closed-native-v4`; 감사 시작 checkout `7c21f42` 이후 변환 코드 변경 없음.
- 원본: `artifacts/region-image-only-r10/complex-inputs/original-rgb.png`, SHA `ca69631098693305962aa48fbbeab3c3353079d45fa56332451b8aa09b1e77b5`.
- 최종 사용자 PPT: `artifacts/region-image-only-r14/cli-v4/original/native/result.pptx`, SHA `f8ec7c648e9b922948e084a4177c33a60bef7111ef81b69c29228e2e71b7719b`.
- 실제 PowerPoint 렌더: 같은 폴더의 `renders/result.png`, SHA `28059bc5120db127013f5a60166e106fba50a7c675dad837538510617a32eea1`.
- 복잡7개 모두 `flow-v4-review/*.png`에서 원본/실제 COM을 직접 비교했다. original, blue-flow, reasoning-full, nested-panels4개는 아래처럼 항목을 세었고 나머지3개는 정성 관측으로 분리한다. 7개 전체 정답률로 합산하지 않는다.
- 이번에는 새 추론이나 재렌더를 하지 않았다. 저장된 실제 COM 결과와 원본/PPT SHA를 다시 결합했다.

관측 장부는 `r15_visual_loss_ledger.json`, 재현 도구는 `tools/r15_visual_loss_audit.py`다. `artifacts/region-image-only-r15/visual-loss-v2/summary.json`에 장부·도구·입력·PPT·렌더 SHA를 남겼다. `original-loss-map.png`는 원본 위에 노드 ID와 손실 종류를 표시한 감사용 그림이며, 변환 결과나 추론 입력이 아니다. 도구는 장부에 남았다고 표시한 owner/연결이 실제 emitted scene에 있는지도 검사한다.

이는 **에이전트의 개발 이미지 육안 관측 장부**다. 독립 사람 GT, 미노출 holdout, 사람 편집시간 측정이 아니다. 좌표는 관측 그림에서 수동으로 잡은 대략적 영역이며 정밀 IoU 평가용 annotation으로 사용하지 않는다.

## 2. 분모와 판정 규칙

1. 객체 수는 픽셀·면적이 아니라 사용자가 개별 수정할 구조 단위다. 박스/원통형 DB 등 핵심 노드와 외부 구획을 따로 센다. 아이콘·배경·그림자·그라데이션은 복원 분모에서 제외한다.
2. 닫힌 노드의 단순한 editable 사각형 근사는 존재로 센다. 외형이 다르다는 이유만으로 모두 실패 처리하지 않는다. 작은 위치/굵기 차이도 이번 손실 개수에 넣지 않는다.
3. 제목이 남았더라도 설명이 사라지면 `partial`이다. 철자/단어 손실과 줄바꿈·스타일 차이를 구별한다. 아이콘 제거는 텍스트 불완전으로 세지 않는다.
4. 연결은 같은 출발/도착 구조와 방향이 있어야 존재로 센다. 색/굵기 차이는 존재와 분리하며 점선 의미 손실은 따로 기록한다.
5. original 연결20개는 끝점과 방향을 확실히 읽을 수 있는 **보수적 부분집합**이다. Memory Layer 경계에서 끝나는 선, 혼잡한 하단 피드백은 제외했다. 원본에 연결이 총20개뿐이라는 주장이 아니다. 따라서 실제 누락은 **적어도16개**다.
6. User Input 라벨 생략은 승인된 R14 빈 카드 정책이므로 정책 위반 FN으로 재분류하지 않는다. 다만 사용자가 입력해야 할 정보가 남아 있다는 실제 손실은 따로 보인다. 사진 카드 정책을 사후 변경해 다른 누락까지 성공으로 돌리지 않는다.

## 3. original: 노드별 실제 손실

| ID | 구조 | 최종 상태 | 확인된 최초 손실 단계 |
|---|---|---|---|
| N01 | User Input | 빈 카드만 남음 | R14 의도적 내부 생략 |
| N02 | Fast Model API | 없음 | 선택된 후보에 없음 |
| N03 | Slow Model API | 없음 | 선택된 후보에 없음 |
| N04 | Boundary Redaction | 제목·설명 유지 | — |
| N05 | Sensory System | 제목만 유지 | OCR 설명문 누락 |
| N06 | Identity & Fast Path | 제목·설명 유지 | — |
| N07 | Bot Orchestrator | 제목·설명 유지 | — |
| N08 | Working Memory | 없음 | 선택된 후보에 없음 |
| N09 | QueryPlanner | 제목·설명 유지 | — |
| N10 | LTM Handler | 없음 | 선택된 후보에 없음 |
| N11 | ACT 흐름 박스 | 없음 | 후보 closed:6 → texture 거부 |
| N12 | Boundary Enforcement | 제목만 유지 | OCR 설명문 누락 |
| N13 | SocialManager | 없음 | 후보 closed:7 → texture 거부 |
| N14 | Reflection Handler | 없음 | 선택된 후보에 없음 |
| N15 | Generation Stack | 제목만 유지 | OCR 설명문 누락 |
| N16 | Memory Graph DB | 없음 | 후보 closed:9 → texture 거부 |
| N17 | Canonical State DB | 없음 | 선택된 후보에 없음 |

핵심 노드17 = 직사각형 계열15 + 원통형 DB2다. ACT의 두 줄로 중복 인쇄된 제목은 원본 오류처럼 보여도 하나의 닫힌 흐름 박스로 센다. 이 박스와 그 아래 자식들을 둘러싼 녹색 구획은 다른 객체다.

- 기하 구조 존재: **8/17 = 47.1%**, 부재9/17 =52.9%.
- 부재9개 중 **6개는 후보 부재, 3개는 내용 필터에서 제거**. 이 원본에서는 후자의 세 후보를 전부 살려도 최대11/17 =64.7%다. 필터 완화만으로 해결할 수 없다.
- 남은8개: 제목·설명 유지4, 설명 손실3, 정책상 빈 카드1.
- 주 제목만 보면7/17개가 남고10개가 없다. 그10개 중1개는 정책상 의도적 생략이다. 이58.8%를 그대로 정책 위반 OCR FN율이라고 부르지 않는다.
- PERCEIVE·RETRIEVE·THINK·하단 ACT 자식 구획의 명시적 외곽선4개는 모두 없다. Memory Layer의 배경색 영역은 이 분모에 넣지 않았다.
- 그림 제목과 연결 주석의 손실도 보이지만 이번 정량 분모에는 넣지 않았다. 큰 외곽선·주석까지 포함하면 수작업은 위 개수보다 늘어난다.

### original 연결 장부

| 장부 | 원본에서 직접 확인한 방향 | 출력 |
|---|---|---|
| E01–02 | User Input → Bot, Bot → User Input | 둘 다 유지 |
| E03 | Bot → Boundary Redaction | 없음 |
| E04–05 | Boundary Redaction → Sensory, → Identity | 둘 다 유지 |
| E06–07 | Sensory → Bot, Bot → Working Memory | 둘 다 없음 |
| E08–09 | Fast Model API → QueryPlanner, Working Memory → Fast Model API | 둘 다 없음 |
| E10–11 | Working Memory → LTM, QueryPlanner → LTM | 둘 다 없음 |
| E12–14 | LTM → Slow API, Slow API → LTM, LTM → Bot | 모두 없음 |
| E15 | Bot → ACT | 없음 |
| E16–18 | ACT → Boundary Enforcement, → SocialManager, → Reflection Handler | 모두 없음 |
| E19–20 | Bot → Generation Stack, Generation Stack → Bot | 둘 다 없음 |

이20개 중4개만 남았다. 특히 Bot→검색→LTM→Bot, Bot→생성→Bot, Bot→ACT→세 실행 노드의 주요 경로를 결과물에서 따라갈 수 없다. 작은 외형 차이가 아니라 **흐름 설명 기능 자체가 사라진 것**이다.

## 4. 다른 그림의 손실

| 그림 | 육안으로 센 구조 분모 | 실제 남은 구조 | 손실과 의미 |
|---|---:|---:|---|
| blue-flow | 노드7, 방향 연결7 | 노드6, 연결4 | 노드1(14.3%), 연결3(42.9%) 부재 |
| reasoning-full | 노드24, 방향 연결29 | 노드24, 연결18 | 노드는 모두 있어도 연결11(37.9%) 부재 |
| nested-panels | 외곽·내부 박스33 | 30 | 외곽 CFAPP와 Audio/Text 카드3개(9.1%) 부재 |

### blue-flow

노드7개는 Configuration Space, Pruned Space, Effectiveness Indicator, Large Language Model of Code, Multi-Objective Optimization, Pareto-optimal Configurations, Compact and Green Model of Code다. 마지막 노드가 사라졌고 Large Language Model of Code는 `Large Language`까지만 남았다. 완전한 노드 라벨은5개, 부분1개, 부재1개다.

연결7개는 Configuration→Pruned, Pruned→Effectiveness, Pruned→Multi-Objective, Effectiveness→Multi-Objective, Multi-Objective→Pareto, Pareto→Compact, Large Language→Compact다. Effectiveness→Multi-Objective와 Compact로 들어가는2개가 없다. 외곽 점선 구획 및 박스 밖 Pruning/Sampling & Training/Knowledge Distillation/Configuration Tuning 주석4개도 없다(위 노드·연결 분모와 별도).

### reasoning-full

노드24 = Input/Encoder/Text Embedding3 + Decoder/Program/Executor/Symbolic Prediction 각3개(12) + Predictor/Neural Prediction 각3개(6) + Mixture-of-Experts/Gating/Final3이다.

연결29 = Input→Encoder→Text2 + Text→Decoder/Predictor6 + Text→Gating1 + Decoder→Program→Executor→Symbolic9 + Predictor→Neural3 + Symbolic/Neural→Mixture6 + Gating→Mixture1 + Mixture→Final1이다.

누락11개는 Text Embedding에서 나가는6개 분기와 Mixture로 모이는6개 중5개다. 유일하게 남은 Neural Prediction1→Mixture도 원본 점선이 실선으로 바뀌었다. Mixture-of-Experts 제목은 없고 Symbolic Prediction1은 `Symbolic`만 남았다. 나머지22개 노드 제목은 유지됐다. 논리/유추 구획 배경과 제목은 이24개 노드 분모와 별도다.

### nested-panels

33개 = Causal Reasoning 계층4 + Price Prediction5 + History/LLMs 계층7 + Input Parser 계층7 + Content Summary3 + Risk Management6 + 외곽 CFAPP1이다. 여기에는 박스 역할을 하는 Audio/Text/PDF 카드도 포함하지만 내부 아이콘 자체는 제외한다. Audio/Text2개와 외곽1개가 없다. 남은30개 중 PyPDF + Tokenizer는 PyPDF로 잘렸고 LLM APIs는 LLMAPIs로 붙었다. 이 이미지는 원본 연결선이 없으므로 연결 재현율은 N/A이지100%가 아니다.

### 나머지3개: 정성 확인만

- contrastive: Decoder와 여러 MLP, 수식 토큰이 사라지고 주요 연결 대부분이 없다. 토큰/연산자 의미 판정이 필요한 그림이므로 이번에 전체 GT 수를 억지로 확정하지 않았다. 출력22도형/1연결을 높은 복원율의 근거로 쓰지 않는다.
- dark-transformer: 두 Add & Norm의 박스는 남지만 글자가 없다. 바깥 블록, residual 우회 경로와 입력 분기가 사라졌다. 남은 두 세로선에는 원본의 화살표 의미가 보존되지 않았다. 보라색 무라벨 요소는 역할이 불확실해 이번 FN 개수에서 제외한다.
- fusion: GRU + WA와 LE/HWA 구획, Fusion 연산 구조 및 상단 출력 구조가 없다. 질문→RoBERTa 한 경로만 남아 fusion 과정이 설명되지 않는다. 여기의 원/막대는 장식과 연산 구조를 구별해야 하므로 개별 역할 확정 전 전체 개수를 만들지 않았다.

## 5. 코드상 손실 단계와 육안 반증

| 그림 | 선택 후보→최종 도형 | 추적 후보→owner 선별 후→최종 연결 |
|---|---|---|
| original | 11→8 | 12→7→4 |
| blue-flow | 7→6 | 7→5→4 |
| reasoning-full | 24→24 | 18→18→18 |
| nested-panels | 32→30 | 0→0→0 |
| contrastive | 34→22 | 2→2→1 |
| dark-transformer | 11→7 | 2→2→2 |
| fusion | 5→4 | 1→1→1 |

**후보 개수는 정답 수가 아니다.** 특히 이전 설명의 “native 적합 실패3개”를 복원 가능한 연결3개로 읽으면 안 된다. `rejected-paths.png`에 거부된 경로를 원본 위에 겹쳐 직접 확인했다.

- `connector:r3:0` QueryPlanner→Bot: LTM 근처 박스 경계까지 타고 돌아간다. 원본에 있는 QueryPlanner→LTM과 LTM→Bot을 직접 QueryPlanner→Bot으로 합친 후보를 되살려서는 안 된다.
- `connector:r3:1` User Input→Boundary Enforcement: 원본 Final Response는 반대 방향이다. geometry 지원 폭을 늘리는 것만으로 출력하면 위양성 방향 오류가 생긴다.
- `connector:r3:7` Generation→Bot: 큰 방향 관계는 원본에 있으나 경로가 Generation 박스 가장자리를 돌아간다. 원본 port/연결 경로를 먼저 정리해야 한다.

반면 blue-flow에는 native fitting 오차4.0795로4px 제한을 넘은 후보도 있다. 이것을 구실로 모든 그림의 cutoff를 올리지 않는다. 정확한 원본 경로인데 지원 표현이 없는 경우와 추적 자체가 잘못된 경우를 분리해야 한다.

원인은 단일 “렌더러 한계”가 아니다. 엄격한 폐사각형 후보 조건, 내부 texture와 노드 존재의 결합, OCR에 의존하는 owner 선별, owner가 없는 영역에서의 연결 혼합, 분기/점선 추적 누락, 제한된 native 표현이 단계적으로 겹친다.

## 6. 판정과 설계 인계

현재 원본에서 사용자가 다시 만들어야 하는 것은 **최소 핵심 노드9개, 확인 연결16개, 구획4개**, 그리고 남은 노드3개의 설명문이다. User Input 이름 입력은 승인 정책상 별도 작업1개다. 이는 작업 시간으로 환산한 값이 아니라 재작성 대상 목록이다. 1개 다분기 연결과1개 단순 박스의 편집 비용을 같다고 가정하지 않는다.

실용 기준 미달이라는 사용자 판단은 이 관측과 일치한다. 다음 설계는 `r15_recall_recovery_spec.md`에 분리했다. R14 preset/실패 산출물/Phase16 동결은 그대로 두었으며 새 복원 구현·학습·holdout 평가는 하지 않았다.
