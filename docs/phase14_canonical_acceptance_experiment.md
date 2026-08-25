# Phase 14. Canonical 모델 acceptance 실험

실험일: 2026-08-25

결론: **NO-GO. 현재 결과는 실사용 기준에 큰 폭으로 미달하며 near-miss가 아니다. 모델 bundle은 연구용 candidate로만 유지하고 canonical로 승격하지 않는다.**

편집 가능한 객체를 생성한다는 최소 기술 조건은 만족하지만, 원본 구조를 보존해 사용자의 재작도량을 실질적으로 줄인다는 제품 조건은 만족하지 못했다. 현재 candidate를 실제 사용자용 변환 품질로 추천해서는 안 된다.

## 질문과 판정 원칙

합성 데이터에서 학습한 detector/family classifier와 작은 real-figure gate를 checksum-bound bundle로 묶었을 때, 실제 논문 도식에서 사용자의 재작도량을 충분히 줄이면서 비도식을 공백으로 남길 수 있는가를 검증했다.

판정은 다음 순서로 고정했다.

1. 합성 test split에서 detector와 family classifier를 독립 평가한다.
2. 6 diagram + 5 non-diagram 개발 benchmark에서 detector threshold를 선택한다.
3. 선택한 설정으로 OCR 포함 PPTX를 만들고 Microsoft PowerPoint 렌더를 육안 검토한다.
4. 설정을 더 바꾸지 않고, 미리 동결한 5 diagram + 9 non-diagram holdout을 한 번만 실행한다.
5. 정량 관문과 육안 관문을 모두 통과할 때만 canonical로 승격한다.

## 데이터와 모델

- detector 데이터: PIL 350장 + LibreOffice 210장을 합친 560장, seed 1301/1302, train/val/test = 448/56/56.
- detector: Faster R-CNN 계열, seed 1303, CPU, batch 4, 15 epochs. 최종 epoch 14 checkpoint SHA-256은 `e6a6926e...a1a6f58`이다.
- family classifier 데이터: 독립 seed로 확장한 1,120장. test accuracy는 `97/112 = 0.8661`이지만 `orthogonal_flow`는 `8/16 = 0.5`였다.
- gate 데이터: 공개 figure 47장 중 diagram 19, non-diagram 28. 선택 checkpoint SHA-256은 `d7b2291c...15d9eba`이다.
- 실제 figure는 `yousefg-codes/research-paper-figures`의 revision `3e8a1a190f814b48a358e5be60e69de28e886110`에서 row와 원본/이미지 SHA-256을 고정했다. 외부 이미지 자체는 커밋하지 않았다.
- 개발 benchmark manifest: `benchmarks/real_v1/manifest.json`, SHA-256 `711fef61...ae30ea9`.
- confirmatory holdout manifest: `benchmarks/real_holdout_v1/manifest.json`, SHA-256 `c63d9239...d7448a`.

외부 dataset의 재배포 라이선스는 이 실험에서 확정하지 못했다. 따라서 manifest와 provenance만 추적하고 이미지는 로컬 materialization으로 제한했다.

## 고정 bundle 설정

개발 benchmark와 합성 test 결과를 함께 보고 다음 설정을 동결했다.

- detector threshold: `0.6`
- node/container cross-kind NMS IoU: `0.7`
- lower-score node containment suppression: `0.85`
- diagram gate threshold: `0.6`
- connector strategy: `morphological`
- bundle status: `candidate`
- candidate bundle SHA-256: `d9d232c4...740023ac`

cross-kind NMS는 같은 실제 박스가 서로 다른 node kind로 중복 출력되는 현상을 제거한다. containment suppression은 큰/작은 중복 node 중 낮은 점수의 예측을 버리되, node와 container의 정상적인 중첩은 보존한다.

## 정량 결과

### 합성 detector test

고정 threshold 0.6에서:

| 대상 | Precision | Recall | F1 |
|---|---:|---:|---:|
| Node | 0.9760 | 0.9849 | 0.9805 |
| Container | 0.9706 | 0.9429 | 0.9565 |

### 개발 real benchmark

- diagram pass: `5/6 = 0.8333` (요구 0.8)
- non-diagram empty/reject: `5/5 = 1.0` (요구 1.0)
- 미통과 diagram: `public-chat-plugin`
- 모든 출력 connector endpoint는 native PowerPoint 도형에 결속됐다.

수치상 개발 관문은 통과했다. 그러나 이 관문은 최소 개수와 과검출 상한을 보는 screening 지표이지 의미적 구조 정확도의 완전한 측정이 아니다. 실제 렌더와의 불일치는 이 screening 기준이 지나치게 느슨했음을 보여준다. 이후에는 이 수치를 품질 승인 근거로 단독 사용하지 않는다.

### 동결 holdout

- diagram pass: `1/5 = 0.2` (요구 0.8)
- non-diagram empty/reject: `6/9 = 0.6667` (요구 1.0)
- 유일한 통과 diagram: `holdout-transformer-encoder`
- false positive non-diagram: application screenshot, framework table, perturbation-distribution plots
- `holdout-worker-model`은 primitive 상한을 넘었고, word graph/GCN receptive fields/convnet topology는 구조 recall이 부족했다.

holdout은 이 결과 뒤에 재튜닝하거나 재실행하지 않았다.

## PowerPoint 육안 검토

개발 benchmark와 holdout의 모든 PPTX를 Microsoft PowerPoint로 직접 PNG 렌더한 뒤 원본과 나란히 비교했다.

좋았던 점:

- 비도식으로 올바르게 거절된 표본은 완전히 빈 슬라이드였다.
- 검출된 박스, 텍스트, 커넥터는 raster가 아니라 개별 editable object였다.
- 중복 윤곽은 초기 detector 출력보다 크게 줄었고 connector endpoint 결속도 유지됐다.

실패한 점:

- chat/DDSP/3-phase/CTI와 여러 holdout 도식에서 핵심 node와 관계가 대량 누락됐다.
- 일부 검출 박스는 서로 겹치거나 실제 의미 단위보다 지나치게 컸다.
- connector가 원본 topology를 충분히 보존하지 못해 사용자가 상당 부분 다시 그려야 한다.
- UI/table/distribution plot을 구조적 diagram으로 오인한 gate 실패가 있었다.

따라서 개발 benchmark의 개수 기반 통과와 달리, 실제 사용자 시간 절약이라는 최종 기준은 충족하지 못했다. 출력 일부를 고치는 수준이 아니라 누락된 핵심 구조와 관계를 다시 그려야 하므로, 현재 품질은 기준에 가까운 상태가 아니라 상당한 재학습·평가 설계 수정이 필요한 상태다.

## 확인된 한계

- 합성 detector F1 `0.98`은 실제 figure의 구조 보존 성능을 대표하지 못했다.
- primitive/connector 개수 coverage는 의미적으로 틀린 객체와 topology도 통과시킬 수 있어 승인 지표로 불충분하다.
- family classifier의 전체 accuracy가 `0.8661`이어도 핵심 `orthogonal_flow` accuracy는 `0.5`에 불과했다.
- 47장 규모 gate 데이터는 UI, table, multi-plot 같은 실제 비도식 다양성을 포괄하지 못했다.
- 현재 connector는 endpoint 결속이라는 편집성은 보장하지만 원본 관계의 정확성은 보장하지 못한다.
- 실제 사람의 PowerPoint 편집 시간은 아직 직접 측정하지 않았다. 다만 렌더에서 핵심 구조가 대량 누락되어 현재 결과가 시간 절약 기준을 통과할 가능성은 낮다.
- 모델 checkpoint와 외부 이미지는 로컬 ignored artifact라 clean checkout 재현이나 배포가 불가능하다.

## 구현 및 재현 산출물

- `model_bundle.py`: checkpoint/training/evidence hash 검증 및 candidate fail-closed 로딩
- `create_model_bundle.py`: bundle 생성
- `materialize_real_benchmark.py`: revision/row/hash 고정 외부 이미지 materialization
- `run_real_benchmark.py`: 입력·bundle·PPTX hash와 native object acceptance 기록
- `evaluate_detector_checkpoint.py`, `evaluate_family_checkpoint.py`, `evaluate_diagram_gate.py`: 독립 평가 artifact 생성
- `detection_postprocess.py`: production/evaluator 공용 중복 제거

로컬 ignored evidence:

- `workbench-ml/model_bundle.candidate.json`
- `artifacts/real-v1-final/run_manifest.json`
- `artifacts/real-v1-final/contact-sheet.png`
- `artifacts/real-holdout-v1-final/run_manifest.json`
- `artifacts/real-holdout-v1-final/contact-sheet.png`

## 다음 관문

이번 holdout은 앞으로 개발셋으로 재사용하지 않는다. 다음 라운드는 다음 조건을 먼저 만족해야 한다.

1. 실제 논문 diagram/non-diagram의 다양성을 늘린 학습·검증 데이터로 gate와 detector의 domain gap을 줄인다.
2. `orthogonal_flow` family 분류 정확도 0.5와 실제 connector topology recall을 우선 개선한다.
3. 개수 기반 coverage 외에 의미적 node/topology annotation 또는 실제 편집 시간 측정을 추가한다.
4. 새 설정을 확정한 뒤에는 별도의 새 confirmatory holdout을 동결하고 한 번만 평가한다.

새 family와 장식적 style 확장은 이 관문 뒤로 계속 보류한다.

## 회귀 검증

- 전체 테스트: `171 passed`, `9 warnings`
- `git diff --check`: 통과
- 경고는 Lightning의 pytree deprecation과 smoke-test dataloader worker 권고이며 실패는 아니다.
