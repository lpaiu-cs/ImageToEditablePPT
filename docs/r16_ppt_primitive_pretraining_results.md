# R16-PG: PPT 도형 선학습 실험 결과 및 다음 설계

2026-09-09. **실험 완료, 선학습의 추가 이득 미확인, 품질 미달로 제품 승격 불승인.**

## 결론

실제 PowerPoint에서 만든 72개 이미지-정답 쌍으로 3개 arm을 학습하고, 새 평가 장면 8개와 음성 2개에서 비교했다. 30개 결과 PPT를 실제 PowerPoint COM으로 다시 렌더했다. 원본/세 arm을 나란히 놓은 10개 보드를 모두 직접 확인했다.

선학습 arm은 마름모 8개만 복원하고 나머지 40개 도형을 빠뜨렸다. 동일 계산량 대조군도 정확히 같은 개수와 종류를 복원했다. 따라서 scratch80 대비 개선만 보고 선학습 성공이라고 부를 수 없다. **이번 실험은 도형 선학습 전반의 불가능성을 증명하지 않으며, 이 작은 데이터·모델·고정 학습량 조합의 실패다.**

제품 기본 CLI, 기존 R15 출력 및 Phase16 formal holdout은 변경하지 않았다. 이번 결과는 OCR·연결·색 채움 없는 닫힌 도형-only 연구 출력이다.

## 참고 연구에서 가져온 것과 가져오지 않은 것

[PGDPNet 논문](https://arxiv.org/abs/2205.09363) 5.3절의 기하 요소 의미 분할, 5.4절의 시각·위치·종류를 이용한 관계 학습에서 출발했다. [공식 분할 손실 구현](https://github.com/mingliangzhang2018/PGDP/blob/main/geo_parse/modeling/geo_seg/loss.py)과 [관계 특징 구현](https://github.com/mingliangzhang2018/PGDP/blob/main/geo_parse/modeling/geo_rel/graph_feature_extractors.py)도 확인했다.

이번은 의미 분할을 이용한 최소 선학습 대조 실험이다. 논문의 multi-label binary mask/instance embedding/GNN 전체를 재현한 것이 아니다. 겹침 없는 PPT의 6개 닫힌 영역에는 기존 U-Net의 7-class softmax head를 사용했다. 공식 데모의 GT 텍스트 사용은 가져오지 않았다. 기존 코드와 설치된 CPU PyTorch를 재사용했고 외부 가중치·데이터·추가 학습 프레임워크는 설치하지 않았다.

## 데이터 경계

- source PPT와 mask companion PPT 144개를 320×200으로 실제 COM 렌더했다. primitive train 24개, scene train/calibration/eval 24/8/8개, negative 4/2/2개다.
- v1에서는 원통 윗면의 preset 밝기 변화가 정답 영역 459px를 ignore로 만들었다. **학습 전에 육안으로 발견해 사용 중지**했고 v1은 보존했다.
- v2는 흰색 점유 영역을 COM 렌더한 뒤 source bbox로 정답 class palette만 부여한다. 원통 윗면도 포함된다. v1/v2 입력 이미지 72개 및 source geometry/adjustments는 동일하다.
- source bbox·정답 mask·source PPT는 모델 입력이 아니다. 별도 `predict` 모드에 RGB와 checkpoint만 전달했고 평가기의 동일 이미지 예측 객체와 정확히 일치했다.
- split마다 seed/이미지는 다르지만 scene의 3×2 배치 계열을 공유한다. 회전·가림·겹침·연결·사진 음성·다른 renderer 일반화는 검증하지 않았다.

## 동결 비교 결과

동일 초기값, 마지막 scene80 배치 순서, batch4, optimizer reset 및 class weights를 독립 트랙이 읽기 전용 감사했다. 학습 무효화 버그나 GT 추론 누출은 발견되지 않았다. 모든 arm의 threshold를 calibration에서 결정한 뒤 eval을 열었다.

| arm | 학습 steps | 선택 threshold | calibration 통과 | eval TP / FP / FN | precision | recall | 도형별 pixel macro IoU |
|---|---:|---:|---|---|---:|---:|---:|
| scratch80 | 80 | .95 | 아니오 | 0 / 2 / 48 | 0% | 0% | 22.34% |
| primitive80 → scene80 | 160 | .70 | 예 | 8 / 0 / 40 | 100% | 16.67% | 18.93% |
| scene80 → scene80 | 160 | .50 | 예 | 8 / 0 / 40 | 100% | 16.67% | 25.45% |

세 arm 모두 eval 음성 2장의 false positive는 0이다. 선학습 및 계산량 대조군의 8 TP는 모두 마름모다. 다른 다섯 종류는 각각 0/8이다. 엄격한 calibration을 만족하더라도 유용한 복원량은 부족하다. 높은 precision만으로 생산 준비 완료를 선언하지 않는다.

scratch80의 fallback .95 결과는 안전성 승인이 아니라 calibration 실패 상태의 진단 출력이다. 그 threshold를 높일수록 항상 안전해지는 것도 아니다. 고신뢰 내부 조각만 남으면 bbox가 작아져 기존의 올바른 도형이 잘못된 작은 도형으로 판정될 수 있다.

학습 step 수는 고정했으며 eval을 본 뒤 재학습·threshold 탐색을 하지 않았다. 단일 seed이므로 통계적 우월성은 주장하지 않는다. 같은 step/batch/architecture는 계산량 대조이지 벽시계 시간 대조가 아니다.

## 실제 육안 확인

[대표 장면 000 보드](C:/vs/ImageToEditablePPT/artifacts/region-image-only-r16/primitive-com-v1/scene-eval-000.png)에서 왼쪽은 source RGB, 이후 scratch80/선학습/계산량 대조 순서다. [장면 001](C:/vs/ImageToEditablePPT/artifacts/region-image-only-r16/primitive-com-v1/scene-eval-001.png) 및 나머지 6개 장면에서도 선학습과 계산량 대조는 마름모만 남겼다.

- 원통·직사각형·둥근 직사각형·타원·평행사변형은 눈에 분명히 보이지만 PPT에는 없다. **미관의 작은 차이가 아니라 5/6 도형 전체 누락**이다.
- 선학습 마름모는 대조군보다 작게 나온 예가 있다. 이는 단순한 1px 실패 분류가 아니라 confidence로 영역을 잘라낸 bbox 추정 한계다. TP 기준은 종류 동일 및 bbox IoU≥.5다.
- scratch80의 장면 005/007에는 원래 마름모보다 훨씬 작은 마름모만 남는다. 이 둘이 FP 2개다.
- 두 음성 장면은 모든 arm에서 비었다. 이 negative는 대상 닫힌 도형이 없다는 검사이며, 제품에서 열린 선을 버려도 된다는 승인이 아니다.
- native XML에서 30개 PPT의 객체 수가 예측 수와 같음을 검증했다. 총 18개 native shape이고 raster로 위장하지 않았다. COM receipt의 source PPT/render SHA도 일치한다. 직접 사람의 편집 시간을 측정한 것은 아니다.

## 실패 원인 분리: 배경 분리보다 도형 종류 판별

eval을 동결한 뒤 추가 학습 없이 argmax를 재측정했다. 아래는 scene-only 진단이며 위 공식 IoU는 음성까지 포함하므로 수치 범위가 다르다.

| arm | eval 도형 점유 영역 IoU, 종류 무시 | eval 도형 내부 종류 정확도 | scene train 내부 종류 정확도 |
|---|---:|---:|---:|
| scratch80 | 97.80% | 30.88% | 37.27% |
| primitive80 → scene80 | 99.00% | 36.17% | 33.92% |
| scene80 → scene80 | 99.47% | 26.85% | 42.10% |

**확인된 사실:** 배경과 도형 점유 영역은 이 단순 합성 분포에서 잘 분리된다. 그러나 같은 객체 내부가 서로 다른 종류로 칠해지고, 종류별 confidence로 component를 만들면서 많은 도형이 사라진다. 선학습 arm은 학습 scene에서도 종류 정확도가 약34%에 그친다. 따라서 현 실패를 오직 미지 이미지의 일반화 문제로 돌릴 수 없다.

**가설:** 색이 평탄한 도형 내부 각 픽셀에 전체 도형 종류를 예측시키는 학습 목표가 현재 모델·학습량과 잘 맞지 않는다. 객체 전체 윤곽을 판별하는 감독이 부족할 수 있다. 짧은 학습·종류당 primitive 4장·축소 해상도·색 우연 상관·망각도 후보 원인이다. 이번 결과만으로 이들 중 하나를 인과적으로 확정하거나 학습량 증가만으로 해결된다고 주장하지 않는다. primitive-only 단계 checkpoint를 저장하지 않았으므로 선학습 직후의 인식 능력과 scene 학습 후 망각을 분리할 수 없는 한계도 있다.

## 다음 연구선 설계: 영역과 객체 종류를 분리

다음은 별도 버전에서 검증할 설계이며, 현재 결과에 적용한 후처리 구제가 아니다.

1. **양성 대조 먼저:** 고정된 작은 primitive train에서 6종 전체를 학습 가능한지 확인하고 primitive 단계 checkpoint를 남긴다. 이 단계부터 실패하면 새 eval을 열지 않고 손실·입력 해상도·학습량 문제부터 해결한다. train 암기 성공은 일반화 성공과 구분한다.
2. **후보 영역 검출과 종류 판별 분리:** RGB에서 class-agnostic occupancy/객체 후보를 얻고, 예측 후보의 전체 윤곽을 보는 객체 단위 분류기에 6종을 예측시킨다. bbox는 낮은 class confidence로 깎은 내부 조각이 아니라 전체 후보 영역에서 추정한다. 추론 crop에 source GT bbox를 넣지 않는다.
3. **선학습의 직접 대상 변경:** PPT 단독 도형으로 객체 수준 종류·윤곽을 먼저 학습하고 scene으로 이전한다. 기존 U-Net encoder/features와 native preset exporter를 재사용한다. 불확실한 종류는 여전히 생략하고, 임의 rectangle로 모두 대체하지 않는다.
4. **다음 대조도 사전 고정:** 선학습 없음/있음/동일 계산량 대조를 유지하고 단계별 checkpoint·종류별 recall·예측 후보 coverage·정밀도를 기록한다. 새로운 seed와 배치 계열을 분리한 eval을 만든다. 이번 eval은 이후 개발용 진단으로만 사용하고 새 최종 성능으로 재사용하지 않는다.
5. **확장 순서:** 빈 채움/색·선폭·텍스트 변화에서 6종이 먼저 통과한 뒤, 회전·가림·인스턴스 분리, 다음으로 선/커넥터와 관계 감독으로 확장한다. PGDPNet의 관계 모듈은 객체 인식이 미달인 현재 단계에 바로 붙이지 않는다. 프로덕션 승인은 복잡 이미지 육안 확인과 실제 수정량/시간 개선까지 확인한 뒤 별도로 한다.

## 코드 감사 수정 및 회귀

독립 감사에서 `FP=0`만으로 calibration gate를 통과시키는 경계조건을 발견했다. `TP=0/FP=0`인 완전 기권은 precision1 성공이 아니므로, 실행 완료 후 `TP>0` 조건과 회귀 테스트를 추가했다. 실제 이번 calibration의 세 arm에는 이 경계조건이 없었다. 새 선택 함수로 기존 checks를 재검사해 **선택 threshold와 gate 세 쌍이 모두 정확히 동일**함을 확인했다. weights/예측/정답/평가 결과는 수정하지 않았다.

- 최초 동일 범위 회귀: `test_source_centerline.py` 제외 1374 passed / 2 xfailed.
- gate 수정 후 **제외 없는 전체 회귀: 1404 passed / 6 failed / 2 xfailed**, 기존 경고9개. 전체 녹색이라고 보고하지 않는다.
- 6개 실패는 기존 `test_source_centerline.py`의 scale .75 수평/수직 및 scale1.5 역대각선의 양방향 사례다. 해당 테스트와 구현은 R15 기준 `0f90209`에서 변경되지 않았다. 이전 R15 보고서도 이 파일을 제외한 범위였음을 명시한다. 이번 도형 학습에서 이 별개 동결 연구선의 구현·허용오차를 바꾸지 않았다.
- R16 신규 테스트5개는 통과했다. 독립 데이터 감사, RGB-only 예측 동일성, 30 PPT/native 및 COM 검증도 통과했다. 테스트 통과와 시각 품질 통과는 별개다.

## 동결 증거와 재현 경계

실행 모델/runner/spec의 Git 기준은 `fb78876`이다. 이후 calibration 빈 기권 버그 수정은 기존 실행의 code SHA와 다르다. 기존 lock 검증을 무시하지 말고 역사 실행은 해당 기준으로 재현하거나, 수정된 코드로 새 artifact 폴더에 새 run을 만들어야 한다. 데이터/학습 결과 폴더는 덮어쓰지 않았다.

데이터 manifest:
`C:/Users/lpaiu/.codex/worktrees/9cae/ImageToEditablePPT/artifacts/r16-ppt-primitive-data-v2/dataset_manifest.json`

SHA: `bbbaa437653631cc8d3ef96874dd0387ced57fbb57ade8f5b051723b515328bb`

root 실행 증거는 `C:/vs/ImageToEditablePPT/artifacts/region-image-only-r16/` 아래에 있다.

| 증거 | SHA256 |
|---|---|
| primitive-training-v1/lock.json | bec379b74da240ae4649110d092749c70952f5959b2b997e7076f60220f37bde |
| primitive-training-v1/training.json | 750d48579c5e51849c81137cc555ea401ecfe7defafe1197067345da7fc35ae8 |
| primitive-eval-v1/calibration.json | 1ca8eeaf4c9089df06bf00905163d3f48d3caa06b2debe7132bdea2625275351 |
| primitive-eval-v1/results.json | 5b416af59d34a061ac762972a373e83035e9913a116b2b1e871ca6662a5b6000 |
| primitive-diagnosis-v1/diagnosis.json | 9c4dcb3ac75e753f96aa335e49d8203c35c2469ab1f753c19bc21305b57cf505 |
| primitive-com-v1/audit.json | e30f32c857286976e8a64345eab5f2f718fd3ac24fb9ea8f6f0fc13832429a20 |
| primitive-rgb-only-v1/result.json | f8dfddfa7bc547b13fe0df020824fb44e5b3eb2fdd40e7a47864b5b151fec094 |

세 checkpoint SHA는 `results.json`에 기록되어 있다. 학습 입력/코드 파일별 SHA는 `lock.json`, source PPT/mask/render 증거는 데이터 manifest, 최종 PPT/render/보드 연결은 `primitive-com-v1/`에 보존했다. 수치 실패와 육안 미달 결과 모두 그대로 동결한다.
