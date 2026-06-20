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

### 남은 후보

1. family focus_bbox **회귀**를 모델 자체에 학습(현재는 검출 union으로 근사). connector/port 추출 추가 → connector_endpoint·structural_exact 지표 활성화.
2. cycle을 **포함한** 데이터셋으로 재학습 + v3 cycle detector/parser 등록(현재 v3 families 레지스트리는 orthogonal_flow만; cycle은 generator에만 존재).
3. **실제** PPT 렌더 이미지(합성 아닌)로 전이 측정 — 진짜 도메인 검증.
