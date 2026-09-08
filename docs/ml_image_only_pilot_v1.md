# 이미지 단독 학습·평가 트랙: 첫 baseline과 제한 pilot

## 결론

2026-09-08 현재, v13 detector의 **label 계약 불일치**가 확인됐다. 기존 checkpoint는
7 class지만 현재 enum으로 만든 target은 8 class다. 연구용 legacy adapter로 복구한
실제 PPT 렌더 validation 15개에서 노드 TP91/FP3/FN0, container TP11/FP0/FN0이다.
12-step 실제 렌더 학습 pilot은 노드 개선 없이 container FP를 1개 늘려 **미채택**한다.
이 결과는 합성 validation 검출기 진단이다. 논문 전이·전체 PPT 품질·제품 승인·인간
수정 시간 절감의 증거로 사용하지 않는다.

## 코드·환경·자료 경계

- 초기 worktree HEAD는 `fe2fc992171443e7a49e72e5ad69a0cf9ddb039e`였다.
  R7b `d5373b1` 대비 300파일 차이로 후속 evaluator/native 코드가 빠져 있었다.
  이 전용 worktree만 `codex/ml-image-only-pilot` 브랜치로 R7b에 맞췄다.
- 원 체크아웃 `C:\vs\ImageToEditablePPT`의 데이터와 `.venv`는 읽기 전용 참조했다.
  소스 import는 이 worktree의 `src`를 우선한다. torch `2.13.0+cpu`, CUDA false다.
- 기존 checkpoint/PPT/데이터, Phase16 holdout과 R5/R6/R7 동결 판정은 수정하지 않았다.
  데이터 감사에서 v13 test의 중복 확인용 SHA/기하를 읽었지만 test 추론·점수 계산은 하지 않았다.
- 새 산출물은 이 worktree의 `artifacts/ml-image-only-v1`에 있다.
  `artifacts/ml-image-only-pilot`은 subset 필터 적용 전 감사 산출물이다.

## 출처·분할 감사

`ds-v13-mixed`는 PIL 350개와 LibreOffice가 생성 PPT를 렌더한 210개를 합친 것이다.
실제 사람 제작 논문 PPT 210개라는 뜻이 아니다. PIL manifest에는 PPT 파일이 없다.
soffice 210개는 PPT 파일을 확인하고 SHA를 기록했다. generator seed는 각각 1301/1302다.
두 원 manifest의 SHA가 mixed manifest의 기록과 일치한다.

| 자료 | train | val | test | 합계 |
|---|---:|---:|---:|---:|
| PIL | 280 | 35 | 35 | 350 |
| 실제 PPT 렌더 | 168 | 21 | 21 | 210 |
| mixed | 448 | 56 | 56 | 560 |

560개 전체에서 RGB 크기+내용 SHA의 cross-split 동일본은 0개다. 노드/container의
kind+bbox를 정렬한 구조 서명이 같은 cross-split 그룹은 4개다. 이 서명은 텍스트나
연결을 포함하지 않으므로 전체 정답 동일본이라는 뜻은 아니다. 32×18 RGB 평균 절대차
0.01 미만인 cross-split 후보는 105쌍이다. 배경 비율에 민감한 보수적 스크린이며
일반적인 near-duplicate 검증 완결이나 모든 원본 슬라이드 변종 격리를 보장하지 않는다.

학습 집합과 근접한 실제 렌더 validation 6개를 제외하여 15개를 고정했다.
이 15개는 위 구조 exact train 중복에도 해당하지 않는다. 제외는 baseline 결과를 보기
전에 수행했다. 기존 checkpoint가 validation loss로 선택되었으므로 이 집합은
미관측 holdout이 아니다. 기존 run manifest에는 checkpoint 당시 code SHA와 명시적
class 이름이 없고, 완전한 학습 재현 provenance는 복구되지 않았다.

## checkpoint label 계약 사고

`last.ckpt` SHA: `e6a6926ef4e65e11288d61d3b12723b19322ee0d44e6e94b9075cba11a1a6f58`.
실측 `hyper_parameters.num_classes=7`, classifier weight shape `[7,1024]`다.
Git `a00d61c`의 enum은 box/rounded_box/section/label_anchor, 이후 `3ae7caf`는
그 중간에 ellipse를 삽입했다. 현재 loader는 enum 순서로 label을 매번 만든다.

| 옛 label | 의미 | 현재 label |
|---:|---|---:|
| 1 | box | 1 |
| 2 | rounded_box | 2 |
| 3 | section | 4 |
| 4 | label_anchor | 5 |
| 5 | flow_cluster | 6 |
| 6 | panel | 7 |

이 매핑은 Git 이력 및 head 크기에 근거한 legacy 복구 가정이며 checkpoint 자체에
저장된 이름으로 검증한 것은 아니다. 연구 도구에서만 명시적으로 적용한다.
신규 ellipse target은 명시적 오류로 거부한다. 평가에서 ellipse 정답이 있으면 기존
모델은 이를 예측하지 못하므로 FN으로 남는다. v13 train에는 box/rounded_box/
label_anchor만 있고 이번 validation에도 ellipse는 없다.

처음 무매핑 pilot은 2 step 후 `IndexError: Target 7 is out of bounds`로 중단됐다.
checkpoint는 저장되지 않았으며 legacy pilot은 원 checkpoint에서 새로 시작했다.
무매핑 `baseline_predictions.json`/`baseline_metrics.json`은 **무효 진단**으로만 보존한다.
잘못된 평가값은 nodes TP66/FP28/FN25, containers TP1/FP8/FN10이었다.
이 값을 제품 성능 또는 기존 동결 판정의 정정 근거로 삼지 않는다.

## 추론·평가 격리 및 결과

`rgb_inputs.json`에는 id, 복사된 RGB 경로, 이미지 SHA만 있다. 추론은 GT/PPT를
받지 않고 원본 픽셀 크기 그대로 실행한다. Python audit hook이 원본 dataset과
benchmarks의 PNG 외 파일 열기를 거부하며, 별도 프로세스 회귀 테스트로 확인했다.
이는 Python 파일 접근 검사이지 OS sandbox 보장은 아니다. evaluator는 별도 실행하고
정답 SHA를 확인한다. RGB 폴더에는 정답이 없다. id의 family 문자열은 모델에 입력하지 않는다.
원본 크기·SHA와 원본 pixel 좌표를 예측 JSON에 기록한다.

고정 score=0.5, IoU=0.5, cross-class NMS=0.7, containment=0.85다.

| 조건 | 노드 TP / FP / FN | 노드 F1 | container TP / FP / FN | container F1 |
|---|---|---:|---|---:|
| legacy baseline | 91 / 3 / 0 | 0.983784 | 11 / 0 / 0 | 1.000000 |
| 12-step candidate | 91 / 3 / 0 | 0.983784 | 11 / 1 / 0 | 0.956522 |

91개 노드 중 25개는 label_anchor다. anchor 위치 검출은 글자 인식 성공이 아니다.
GT text_regions는 91개, connector_candidates는 67개다. 검출기 점수에는 라벨 문자열,
부모 관계, 방향·연결·끝점 정확도를 포함하지 않았으며 이 항목은 **미측정**이다.
동일 후보 수 또는 TP 수가 같은 객체·좌표라는 뜻도 아니다. 개별 결과는 JSON에 남겼다.

## 제한 pilot

실제 렌더 train168에서 seed1309 순열의 첫 12개, batch1, CPU8 threads,
AdamW LR=0.00003, 최대12step을 사용했다. 180초가 지나면 새 step을 시작하지 않는
soft wall limit이다. 실제 학습 구간은 7.55초였다. optimizer는 새로 만들고 weight만
이어 학습했으며 마지막 step을 고정 평가했다. validation 기반 추가 선택은 없다.
이 pilot은 렌더 도메인 continuation의 제한된 동작 확인이다. 초기 label 계약 오류
수정 후 다시 실행했으며 학습 개선이 없으므로 더 긴 동일 실험은 진행하지 않았다.

candidate SHA: `646b48121f13043c9e7da42a66b805f54c156ffaf88d1da9b6b9c4ee42d853fe`.
학습 sample id·loss·부모/결과 SHA는 `pilot-legacy/run.json`에 있다.

## native 출력 검증

고정 subset index 0/6/12를 baseline/candidate 각각 native PPT로 만들었다.
기존 ML provider에 동결 RGB 예측을 공급하고 morphology/OCR/style을 켰다.
OOD gate와 학습 family CNN은 사용하지 않은 연구 진단이며 ROI는 사용하지 않았다.
전체 이미지/원래 해상도를 유지했다. 추론 단계와 동일한 GT 접근 검사를 적용했다.
`native-baseline/native.json`, `native-candidate/native.json`이 입력/출력 SHA와 수를 남긴다.
이 출력에는 후처리의 visual geometry와 OCR 동작도 포함되므로 detector 점수와 분리한다.

PowerPoint로 여섯 파일을 실제 열고 PNG로 렌더했다. 작업 직전 기존 PowerPoint는
없었으며 이 작업이 연 프레젠테이션만 닫았다. `native-render.json`은 PPT/PNG SHA를,
`native_contact.png`는 원본/baseline/candidate 3열 비교를 남긴다.

육안 확인 결과:

- block_flow: 외곽 container가 사라지고 대각선 두 연결이 누락됐다. 남은 수직 두
  화살표는 원본과 반대 방향이다. 노드 검출 성공이 올바른 연결 복원을 보장하지 않는다.
- layered_stack: 여러 상자가 이중 테두리로 출력되고 외곽 container가 사라졌다.
  Pool→Dropout 연결이 보이지 않고 첫 연결은 중복돼 보인다. Input이 `nput`으로 남는다.
- tree: 원래 대각선들의 큰 배치는 일부 남지만 화살촉이 사라졌다. CP→V가
  수직+짧은 수평 꺾임으로 바뀌고 V 라벨은 없다. dog 라벨은 baseline에서 잘못
  인식되고 candidate에서는 빠졌다. candidate가 시각적으로 개선됐다는 근거가 없다.

native summary의 texts79/72는 중간 scene의 텍스트 수이며 최종 PPT 텍스트 객체 수가
아니다. 최종 baseline PPT의 shape 수는 7/12/14이고 래스터 picture는 모두 0개다.
비어 있지 않은 문자열은 각각 5/5/6개다(candidate 5/5/5). 빈 텍스트 frame과
최종 단계 필터링이 있으므로 XML과 실제 렌더를 함께 검사했다. tree baseline의
오인식 문자열은 `dos`다. 위 평가는
3개 사례의 수동 관찰이며 15개 전체 연결/라벨의 정량 성적으로 확장하지 않는다.
PowerPoint 렌더 성공은 편집 가능 파일의 기술적 확인이며 내용 정확성 승인이 아니다.

상대 구조 트랙의 R6 전체-ROI 결과와 비교할 때, 제 baseline은 검출기 출력 단계이고
그쪽 점수는 최종 emitted 객체 단계다. 서로 다른 단계를 직접 승패 비교하지 않는다.
이번 native 실패는 학습 점수 이후 추적/소유/출력/라벨 병목을 따로 평가할 필요성을 보인다.

## 재현 명령

PowerShell에서 원 체크아웃 `.venv`의 python을 사용한다. 모든 명령은 이 worktree에서
`rtk proxy C:/vs/ImageToEditablePPT/.venv/Scripts/python.exe`를 앞에 붙인다.
기존 산출물은 덮어쓰지 않으므로 `--out`에는 새 경로를 지정해야 한다.

```text
tools/ml_image_only_pilot.py prepare --data C:/vs/ImageToEditablePPT/workbench-ml/ds-v13-mixed --out <새 감사 폴더>
tools/ml_image_only_pilot.py infer --inputs <감사 폴더>/rgb_inputs.json --checkpoint <checkpoint> --out <새 예측 JSON>
tools/ml_image_only_pilot.py evaluate --inputs <감사 폴더>/evaluator_inputs.json --predictions <예측 JSON> --out <새 metrics JSON>
tools/ml_image_only_pilot.py pilot --data C:/vs/ImageToEditablePPT/workbench-ml/ds-v13-soffice --checkpoint <기존 checkpoint> --out <새 pilot 폴더>
tools/ml_image_only_pilot.py native --inputs <감사 폴더>/rgb_inputs.json --predictions <예측 JSON> --out <새 native 폴더>
-m pytest -q tests/test_ml_image_only_pilot.py tests/test_evaluate_detector_checkpoint.py tests/test_detection_postprocess.py
```

검증: 위 3개 테스트 파일 **8 passed**. 제품 runtime은 변경하지 않았다.
다음 제한 실험은 학습을 더 늘리기 전에 정확한 class-map metadata를 모델 bundle에
명시하고, 양 트랙의 같은 15개 출력에서 후처리 손실·라벨·연결 병목을 분리하는 것이다.
새 데이터는 원본 구조 그룹 기준 분할 및 render 변종 격리를 먼저 고정해야 한다.
