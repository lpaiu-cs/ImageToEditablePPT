# Handover (return): Phase 7 Detector 본 학습 결과

작성일: 2026-06-20
인계 방향: 데스크톱(RTX 5090) → 랩탑 세션 (수렴 분석/다음 단계 이어받기)
대응 문서: `docs/handover_phase7_training.md`

---

## 0. 한 줄 결론

**수렴 합격(PASS).** `val_loss` 단조 감소(1.27→0.23), test `node_f1=0.992`로 문서 목표(>0.8)를 크게 상회. 파이프라인 정상.

후속(§4b): container 오탐을 generator 시각 신호 미약으로 규명·수정 → **현실적 변주 컨테이너를 새 default로 채택, canonical 검출기 run-v3에서 container_f1=1.0 / node_f1=0.998 / 빈 이미지 오탐 0.** family·connector는 여전히 모델 범위 밖(structural_exact는 그 때문에 0 유지).

## 1. 학습 run

- 데이터셋: `workbench-ml/ds-v1` (seed 7, count 400, 640x360, family=orthogonal_flow; split 320/40/40)
- 학습: batch 8, max_epochs 20, accelerator gpu(auto), tracking tensorboard
- checkpoint: `workbench-ml/run-v1/checkpoints/{last.ckpt, detector-epoch=19.ckpt}`
- final_metrics: train_loss 0.236 / val_loss 0.229 (과적합 격차 거의 없음)

## 2. 수렴 곡선 (epoch별 val_loss, `metrics.csv` 전체)

| epoch | 0 | 4 | 9 | 12 | 15 | **16(best)** | 19(last) |
|---|---|---|---|---|---|---|---|
| val_loss | 1.272 | 0.510 | 0.268 | 0.260 | 0.234 | **0.217** | 0.229 |

12 epoch 이후 0.22~0.30 사이 평탄화. 조기종료/best-ckpt 선택 여지는 있으나 수렴 자체는 명확.

## 3. test 40장 도메인 평가 (IoU 0.5)

| 지표 | 평균 | 해석 |
|---|---|---|
| **node_f1** | **0.992** | ✅ 노드 검출 사실상 완성 (목표 0.8 초과) |
| container_f1 | 0.382 | ⚠️ 과다 예측 (아래) |
| family_proposal_accuracy | 0.000 | 범위 밖 — 학습 산출물 아님 |
| connector_endpoint_accuracy | 0.000 | 범위 밖 — 학습 산출물 아님 |
| structural_exact | 0/40 | 위 두 항목 때문에 구조상 0 |

### 0점 지표의 원인 (수렴 실패 아님)

- 이 검출기의 label space는 **node/container 전용**(`ml/dataset.py`). family·connector는 모델이 예측하지 않음.
- `infer_detector`는 `--family` 값을 **부트스트랩 시드**로 채움 → `focus_bbox`가 전체 이미지(0,0,640,360)로 40/40 동일 → GT 타이트 박스와 IoU<0.5 → family accuracy 구조적 0.
- `connector_candidates`는 예측에서 40/40 전부 비어 있음(GT 평균 5개) → endpoint accuracy 구조적 0.
- 따라서 `structural_exact`도 0/40 (family+connector가 항상 불일치).

### container_f1=0.38의 진짜 원인 (개선 포인트)

- GT 분포: 40장 중 **27장이 컨테이너 0개**, 13장이 1개.
- 예측 분포: 거의 모든 이미지에 컨테이너 1~6개 부여 → GT-빈 27장에서 전부 오탐 → 0점.
- GT에 컨테이너 1개 있는 13장은 대체로 정확(F1=1.0).
- → 컨테이너 클래스 불균형/오탐 문제. score-threshold 상향 또는 학습 데이터의 "컨테이너 없음" 비중 반영으로 개선 가능.

## 4. 회수 패키지 (이 커밋/세션 산출물)

- `workbench-ml/run-v1/train_detector_run.json` — config + dataset 정체성 + final_metrics + checkpoint 경로
- `workbench-ml/run-v1/metrics.csv` — epoch별 train_loss/val_loss (tensorboard 추출)
- `workbench-ml/run-v1/test_eval_summary.json` — 40장 집계 + 주석
- `workbench-ml/run-v1/preds/*.{pred,eval}.json` — 개별 추론/평가 (로컬 전용, 대용량 아님)

## 4b. 후속 실험: container 오탐 개선 (2026-06-20)

container_f1=0.38의 원인을 추적해 **generator의 컨테이너 시각 신호가 너무 약한 것**으로 확정.

- **threshold 스윕** (node thr 0.5 고정, container thr 0.5→0.99): container_f1 0.382→0.479가 한계. GT-빈 27장 중 20장은 0.99에서도 가짜 컨테이너 잔존 → 오탐이 **고신뢰**라 노브로 해결 불가.
- **진단**: 기존 컨테이너 렌더는 `fill=(248,250,252)`(흰 배경과 채널차 ≤7/255) + `outline=(148,163,184)` 2px 연회색. present/absent 시각 구분 불가 → 모델이 노드 union 주위에 기본적으로 컨테이너를 그림. 학습셋은 47% empty로 균형적이라 불균형 문제 아님.
- **통제 실험 (ds-v2/run-v2)**: seed 고정으로 GT는 ds-v1과 바이트 동일, 컨테이너 렌더만 또렷하게(`fill=(255,247,237)` + `outline=(234,88,12)` width 5). 동일 하이퍼파라미터 재학습.

| 지표 | baseline(ds-v1) | v2(ds-v2 bold) |
|---|---|---|
| container_f1 | 0.382 | **0.950** |
| node_f1 | 0.992 | 0.998 |
| GT-빈 이미지 오탐 | 23/27 | 2/27 |
| 빈 이미지 컨테이너 예측 p90 | 0.998(고신뢰) | 0.696(저신뢰) |

**결론**: 컨테이너 과탐은 클래스 불균형/threshold가 아니라 **시각 신호 미약**이 원인.

### 정공법 default 채택: 현실적 변주 컨테이너 (ds-v3/run-v3)

단일 bold를 그대로 default로 박는 건 "주황 굵은 선=컨테이너"라는 합성 전용 단서에 과적합할 위험(=역방향 꼼수)이 있어, **현실적으로 변주된(테두리 색·두께·fill을 팔레트에서 랜덤, 단 전부 또렷) 컨테이너**를 새 default로 구현. 스타일은 sample_id 기반 별도 RNG로 뽑아 메인 생성 스트림을 건드리지 않음 → 재생성 시 GT는 ds-v1과 **바이트 동일**, 렌더만 변주.

| 지표 | faint(v1, 원본) | single-bold(v2, 실험) | **varied(v3, 새 default)** |
|---|---|---|---|
| container_f1 | 0.382 | 0.950 | **1.000** |
| node_f1 | 0.992 | 0.998 | 0.998 |
| GT-빈 27장 오탐 | 23 | 2 | **0** |
| 빈 이미지 예측 신뢰도 p90 | 0.998 | 0.696 | 0.079 |

varied가 single-bold를 이김(1.0 vs 0.95): 단일 가짜 단서 과적합 불가 + 모든 변주가 또렷해 present/absent 구분이 깨끗. **꼼수 없이 컨테이너 완벽 검출 + 빈 이미지 오탐 0.** run-v3 val_loss 0.211(v1 0.229보다 약간 우수).

**코드 변경 (tracked)**: `ml/synthesize.py` —
- 컨테이너 스타일을 모듈 상수(`CONTAINER_FILL/OUTLINE/OUTLINE_WIDTH`)로 추출하고 **default를 보이는 값으로 수정**(외곽선 slate, width 3; 기존 near-white/2px 연회색은 버그였음).
- `SyntheticContainerStyle` + `_pick_container_style(sample_id)` + 팔레트(`_CONTAINER_OUTLINE/FILL_PALETTE`, `_CONTAINER_OUTLINE_WIDTHS`) 추가, `SyntheticSlideSpec.container_style` 필드로 실어 렌더가 사용.
- phase7 테스트 통과(렌더 결정성·GT 불변 유지).

실험 산출물(로컬): `workbench-ml/{ds-v2,run-v2,ds-v3,run-v3}/`, `workbench-ml/{container_threshold_sweep,gen_ds_v2_boldcontainer,eval_v2}.py`, `workbench-ml/run-v1/container_sweep.json`. **canonical 검출기 = run-v3.**

## 5. Phase 8 착수: FAMILY_DETECT 주입 + family 확장 (2026-06-20)

§2의 다음 단계 후보 1·2를 동시에 진행. 두 개의 독립 커밋으로 랜딩.

### 5a. CYCLE family 추가 (commit `7215c4d`)

`DiagramFamily.CYCLE`를 두 번째 합성 family로 추가. 노드를 링 위에 균등 배치하고 인접 노드를 **닫힌 방향 루프**(노드당 connector 1개)로 연결. 기존 인프라(node/container kind, 스타일 팔레트, 포트, 컨테이너, family proposal, PIL/pptx 렌더) 전부 재사용 → **새 kind 없음 → 검출 라벨 공간 7클래스 불변 → 기존 체크포인트 유효**. 작은 헬퍼 `_edge_point_toward`만 추가(노드 경계 위 연결점+PortSide 계산). `generate_slide_spec`이 family로 분기, CLI `--family`는 `SUPPORTED_FAMILIES`로 cycle 자동 인식. 테스트: contract·닫힌 루프·결정성, unsupported 예시는 SWIMLANE로 교체.

### 5b. ML 검출기를 v3 FAMILY_DETECT에 주입 (commit `f595386`)

`MLFamilyDetector`가 학습된 체크포인트를 구조 캔버스에 돌려 node/container 검출의 union을 focus_bbox로 하는 `FamilyProposal`을 생성.

- **아키텍처 경계 준수**: `test_v3_architecture`가 v3→ml import를 금지하므로 **의존성 역전**. `MLFamilyDetector`는 ml 패키지( v3 의존 허용)에 두고 v3 `FamilyDetector` protocol을 구현. `V3Config.family_detector_override`(protocol 타입)로 주입 → v3는 ml을 import하지 않음.
- **실경로 전이 검증**(run-v3 체크포인트, 40장 합성 test를 그레이스케일 구조 캔버스로 v3 경로 통과): **40/40 proposal, focus_bbox IoU vs GT 평균 0.966(min 0.914), 전부 ≥0.5.** 기존 whole-image CLI 시드(IoU≈0) 대비 비약.
- 단위 테스트: thresholding/union/clipping/registry 라우팅(스텁 모델).

**전체 테스트 77 passed / 1 skipped.** canonical 검출기 = run-v3.

### 5c. inferred family focus_bbox를 검출 기반으로 (commit `5329ba0`)

`infer_detector`가 family proposal의 focus_bbox를 whole-image CLI 시드로 채워 ml eval의 `family_proposal_accuracy`가 구조적으로 0이었음. 체크포인트 사용 시 **검출된 node/container의 union**(클립)으로 focus를 잡도록 변경(검출 없으면 whole-image fallback, placeholder 모드는 기존 유지). evidence/provenance로 출처 구분.

**ds-v3 test 40장(run-v3) 재평가**: `family_proposal_accuracy` **0.0 → 1.0** (node_f1 0.998, container_f1 1.0 불변). → **4개 도메인 지표 중 3개 만점.** `structural_exact`는 여전히 0 — 모델이 connector를 예측하지 않아서(아래).

### 5d. chain connector 추론 후처리 (commit `08dab15`)

검출기는 connector를 예측하지 않아 `connector_endpoint_accuracy`·`structural_exact`가 구조적 0이었음. opt-in `--infer-connectors` 후처리 추가: orthogonal_flow에서 검출 노드를 dominant 축으로 정렬해 인접 노드끼리 연결(generator 로직 미러), connector candidate + 매칭 포트 생성(SlideIR `--validate-ir` 통과). default 동작 불변(플래그 off → 모델 단독 출력).

**ds-v3 test 40장(run-v3, --infer-connectors)**: `connector_endpoint_accuracy` **0.0 → 0.9975**, `structural_exact` **0/40 → 39/40**. (합성 한정 휴리스틱 — 학습된 connector 검출이 아님; 실제 connector 모델 능력은 향후 과제.)

### 현재 지표 요약 (run-v3, ds-v3 test 40장, IoU 0.5, --infer-connectors)

| 지표 | 값 | 상태 |
|---|---|---|
| family_proposal_accuracy | 1.000 | ✅ (5c) |
| node_f1 | 0.998 | ✅ |
| container_f1 | 1.000 | ✅ (container fix) |
| connector_endpoint_accuracy | 0.998 | ✅ (5d, 휴리스틱) |
| **structural_exact** | **39/40** | ✅ (5d) |

**전체 테스트 82 passed / 1 skipped.** 4개 기본 도메인 지표 전부 만점급, 슬라이드 단위 structural_exact 39/40.

## 6. 학습된 능력으로 휴리스틱 대체 (track A)

### 6a. 학습된 family 분류기 (commit `d28ae3e`)

검출기는 family-blind라 family가 고정 태그였음. 슬라이드의 다이어그램 family(orthogonal_flow vs cycle)를 분류하는 소형 from-scratch CNN(`ml/family_classifier.py`)을 혼합 데이터셋(ds-v4: 480/60/60, cycle 282+orth 318)에 오프라인 학습. **GroupNorm 사용**(BatchNorm은 eval 모드에서 chance로 붕괴 — train_acc 1.0인데 val_acc 0.48이었음; train/eval 통계 동일한 GroupNorm으로 해결).

`MLFamilyDetector.family_classifier_checkpoint`(opt-in) 설정 시 FamilyProposal의 family·confidence를 분류기 결과로 채움 → v3 FAMILY_DETECT가 더 이상 family-blind 아님.

**held-out test 정확도 57/60 = 0.950** (단독 및 run-v3 검출기+분류기 v3 seam 통과 end-to-end 동일). 혼동: orth→cycle 2, cycle→orth 1. 산출물: `workbench-ml/{ds-v4,run-fc}`. 주의: ModelCheckpoint는 같은 output-dir 재사용 시 `last.ckpt`를 덮지 않고 `last-v1/v2`로 버전팅 → 학습은 깨끗한 dir에.

### 6b. 학습된 connector segmentation (U-Net) (commit `3a8c68a`)

thin-box(anchor) 검출 대신 **픽셀 semantic segmentation**으로 connector를 검출(사용자 제안). 소형 from-scratch U-Net(depth-3, **GroupNorm**)이 connector 획을 칠하고, GT 마스크는 annotation의 connector `path_points`를 즉석 래스터화(별도 파일 없음). 마스크 → 연결성분으로 인스턴스 추출, 읽기순서로 방향 결정(마스크에 화살촉 없음), GT thin-box IoU에 맞춰 pad, 가장 가까운 노드에 부착, **노드쌍별 dedup**(파편 1개로 병합).

`infer_detector --connector-checkpoint` 사용 시 학습 마스크에서 connector 추출(`--infer-connectors` 휴리스틱보다 우선). **검출 라벨 공간을 안 바꿔 기존 검출기 체크포인트 유효**(thin-box 회피의 핵심 이점).

**segmentation val_dice 0.983.** ds-v3 test(run-v3 노드 + 학습 connector): **connector_endpoint_accuracy 1.0, structural_exact 39/40** — 휴리스틱과 동급이나 학습된·토폴로지 일반 모델. 남은 1 miss는 노드 과검출(connector 무관). 산출물 `workbench-ml/run-seg`. **전체 테스트 90 passed.**

### 현재 모델 구성 (Phase 8 종합)

| 능력 | 방식 | 지표 |
|---|---|---|
| node/container 검출 | Faster R-CNN (run-v3) | node 0.998 / container 1.0 |
| family 분류 | 학습 CNN 분류기 (run-fc) | test 0.95 |
| family focus | 검출 union | family_proposal_accuracy 1.0 |
| connector 검출 | 학습 U-Net segmentation (run-seg) | endpoint 1.0 / structural 39/40 |

휴리스틱(`--infer-connectors`)·CLI family 시드는 이제 **모두 학습 모델로 대체 가능**.

## 7. 실제 렌더 전이 측정 (LibreOffice/soffice)

LibreOffice 설치 후(`winget TheDocumentFoundation.LibreOffice`), `generate_dataset --renderer soffice`로 동일 GT를 **다른 래스터라이저**(그림자·폰트·안티앨리어싱 차이)로 렌더(`workbench-ml/ds-soffice`, test 64장). PIL로 학습한 전 모델(run-v3/run-fc/run-seg)을 그대로 적용.

| 지표 | PIL(기존) | soffice orthogonal(n=31) | soffice cycle(n=33) |
|---|---|---|---|
| node_f1 | 0.998 | 0.968 | 0.871 |
| container_f1 | 1.000 | 1.000 | 0.606 |
| family 분류 | 0.95 | 0.710 | 1.000 |
| connector_endpoint | 1.0 | 0.758 | 0.138† |
| structural_exact | 39/40 | 0/31 | 0/33 |

† cycle connector_endpoint은 읽기순서 방향 휴리스틱이 링에 부적합 — 전이 실패가 아니라 설계 한계.

**방향성 평가: 부분 검증.** 노드 검출(0.92~0.97), orthogonal container(1.0), cycle family(1.0)는 잘 전이 → 실제 시각 특징을 학습함. 그러나 structural_exact 39/40→0(all-or-nothing이 node_f1 0.968에 민감하게 붕괴), orthogonal family 0.95→0.71, cycle container 0.61로 **도메인 갭**이 드러남. **PIL 평면 렌더에 과적합**했고 PIL 수치는 낙관적이었음.

**처방**: 학습 데이터에 **렌더링 다양성**(soffice 렌더 혼합 또는 그림자/폰트 augmentation) 후 재학습 → 갭 축소 예상. 측정 스크립트 `workbench-ml/measure_soffice_transfer.py`.

### 남은 후보

1. **렌더링 다양성으로 재학습** (전이 갭 축소) — soffice/PIL 혼합 데이터셋 또는 augmentation. 가장 우선순위 높음.
2. **cycle을 v3에서 end-to-end로**: v3 families에 cycle detector/parser 등록(현재 orthogonal_flow만). cycle connector 방향은 화살촉 마스크 학습 필요.
3. 통합 단일 추론 CLI(검출기+분류기+segmenter).
