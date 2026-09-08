# R17: 객체 전체 윤곽으로 PPT 도형 종류 선학습

2026-09-09. 사용자 후속 진행 승인. R16 실패와 기존 제품 기본값을 보존하는 별도 실험이다. 기존 Phase16 formal holdout/val/test는 열지 않는다.

## 가설과 변경

R16의 배경/도형 분리는 높지만 객체 내부의 종류가 섞였다. 이번에는 **공통의 고정 점유 영역 검출기 → 예측 객체 crop → 객체당 종류 하나**로 분리한다. 고신뢰 class 내부 조각으로 bbox를 줄이지 않는다. 원본 GT bbox를 추론 crop으로 쓰지 않는다.

공통 검출기는 R16의 `scene80_scene80.pt` (SHA `ae597e2fac851708caa3502457bc18cda1d21f0064f354da519a60c5581759d4`)이다. 해당 모델을 이번 데이터로 재학습하지 않는다. 확률 `1-P(background) >= .5`의 연결요소를 구한다. 면적16px/최소변4px는 R16과 같다. 이는 알려진 R16 개발 결과로 선택한 검출기이며 공정한 신규 architecture-from-scratch 비교가 아니다. 세 classifier arm에는 완전히 동일한 검출기와 예측 crop이 들어간다.

분류기는 기존 `ml.family_classifier._build_cnn`을 재사용한다. 첫 Conv만 2채널, 마지막 공간 pooling은4×4, 마지막 Linear는1024→6으로 바꾼다. 입력은 예측 bbox에 각 방향 10%(최소2원본px) 여백을 둔64×64 crop의 grayscale RGB 관측과 예측 occupancy 두 채널이다. 색상 이름·배치좌표·source 종류·GTmask를 feature로 주지 않는다. grayscale은 색상을 지워도 남는 밝기 정보라서 모든 스타일 shortcut을 제거했다고 주장하지 않는다.

## 학습과 양성 대조

R16 v2 manifest의 train만 사용한다: primitive24, scene24, negative4. GT는 예측 candidate와 IoU≥.5인 일대일 객체 label 감독/평가에만 쓴다. 후보와 매칭되지 않은 GT, unmatched 후보는 따로 기록한다. 분류 target은6종이며 unmatched를 억지로 정답 종류로 배정하지 않는다. 음성은 후보 false positive 검사에 사용하고, 종류 없는 patch에 임의 도형 label을 주지 않는다.

seed1701, CPU4threads, AdamW lr.001, batch12(6종별2개 균등추출), 각 stage300steps, augmentation/search 없음. 세 arm은 동일 초기값에서 시작한다. 첫 stage RNG1702, 마지막 scene stage RNG1703을 공유하며 단계마다 optimizer reset. primitive-only와 scene-first checkpoint도 보존한다.

1. primitive300 양성 대조를 먼저 실행한다. **24개 모두 후보에 매칭되고 training top1 종류24/24**여야 다음 calibration/eval을 실행한다. 이는 학습가능성 검사이지 일반화 성공이 아니다. 실패하면 결과를 보존하고 새 eval payload를 열지 않는다. train 진단을 바탕으로 별도 버전 수정은 가능하지만 같은 run을 연장하거나 성공할 때까지 예산을 몰래 바꾸지 않는다.
2. 통과 시 scratch_scene300 / pretrain300_scene300 / scene300_scene300 세 arm의 classifier를 비교한다. primitive300 양성 대조의 checkpoint가 그대로 pretraining stage다. 다른 두 arm도 동일 초기값을 사용한다.
3. 학습 scene accuracy, primitive accuracy 및 후보 coverage를 단계별로 보고한다. train 성공을 unseen 성능으로 대체하지 않는다.

## 독립 데이터와 판정

독립 작업이 source PPT와 white-occupancy companion을 만들고 실제 COM800×500→320×200으로 렌더한다. 새 calibration은 scene12+negative4(3×2grid), 새 eval은 scene12+negative4(2×3grid)이다. 종류6개를 독립 shuffle하며 색·선폭·문자도 독립 추출한다. 새로운 seed17022/17032/17023/17033을 쓴다. eval은 세로3행에 맞춰 source 높이95..130을 사용하므로 배치와 종횡비 이동이 함께 있고 이 둘의 영향을 분리하지 않는다. 무회전·무중첩·채움 있는 기본preset 조건이며 사진/outline-only/관계 일반화는 아직 아니다.

데이터 감사는 source/mask geometry·adjustments 일치, COM/SHA, 흰 점유 owner bbox 검증, cross-split 및 R16 입력 SHA 중복 부재를 확인한다. root는 train과 calibration 보드만 미리 보고, eval 그림은 선택 동결 뒤에만 본다.

모든 classifier arm의 threshold {.50,.70,.85,.95}를 새 calibration에서 먼저 고정한다. `TP>0 및 FP=0`인 후보 중 recall 최대, 동률 높은 threshold. 없으면 .95 진단 fallback이며 gate 실패다. 이후에만 새 eval 입력을 읽는다. R16 old calibration/eval은 새 성능의 근거로 재사용하지 않는다.

정답 매칭은 종류 동일+IoU≥.5 일대일, per-kind precision/recall, candidate class-agnostic coverage, 음성FP를 함께 기록한다. 선학습 이득은 동일 계산량 대조보다 precision을 떨어뜨리지 않고 recall이 증가해야 한다. 최소 실용성의 연구 gate는 eval precision1, 전체 recall≥.8, 각종류 recall≥.5, 음성FP0으로 고정한다. 이 통과도 복잡도식/편집시간 검증 없는 production 승인은 아니다.

출력은 원래 예측 후보 bbox의 native preset outline-only PPT다. OCR/연결/원본fill/adjustment회귀/임의fallback 도형은 없다. **16이미지×3arm=48 PPT**를 실제 COM 렌더하고 대표2장+음성1장 이상 직접 육안 확인한다. 중간 양성 대조는 training crop과 예측을 그림으로 확인한다. 입력·source·weights·spec SHA를 실행 전후 확인하며 실패결과를 덮어쓰지 않는다.
