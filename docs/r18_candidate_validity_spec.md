# R18: 후보 해상도와 닫힌 구조 유효성 거부 분리 실험

2026-09-09. 사용자 설계 실행 승인. R17의 합성 성공/복잡 원본 실패를 보존하며 제품 기본값·기존 Phase16 formal holdout을 변경하지 않는다.

## 질문과 고정 요소

1. 같은 검출기의 입력 해상도 범위를 늘리면 온전한 구조 후보가 증가하는가?
2. 같은 후보에서 학습한 닫힌 구조 유효성 검사로 글자·장식·배경 조각을 거부할 수 있는가?

R16 `scene80_scene80.pt` 점유 검출기와 R17 `scene300_scene300.pt`6종 분류기는 고정한다. 후자의 종류 confidence threshold도 기존.95 그대로다. 검출기를 재학습하거나 원본 GT crop으로 후보를 대체하지 않는다. 독립 source PPT의 역할 정답은 train label/evaluator에만 사용한다. 여기서 유효성은 **편집할 닫힌 노드/컨테이너 후보**의 유효성이다. 열린 선·structural label이 도식 전체에서 무의미하다는 뜻이 아니다.

## 데이터

독립 작업이 source1200×750의 실제 PPT72개를 COM640×400으로 렌더한다. train scene32/negative8, calibration scene12/negative4, eval scene12/negative4다. source당 하나의 split만 가진다. scene4family는 colored_fill_white_bg, white_card_color_bg, outline_white_bg, nested_container다. 각 split에서 균등 배정한다. scene은6종 노드 각1개, nested에는 별도 큰rounded container1개가 추가된다. source 객체 종류와closed_structure/structural_label/open_structure/decoration/background 역할을 구분한다.

내부 문단·작은native장식, 바깥 제목/문단/열린 선을 포함한다. 사진 다운로드나 실제 로고는 사용하지 않으며 그 일반화를 주장하지 않는다. train/cal은3×2 node배치, eval은2×3배치 및 별도 어휘/seed다. eval 높이 범위 조정에 따른 종횡비 이동은 함께 기록한다. 글자/장식만의negative에는closed_structure가 없다. source XML bbox/preset/ID/역할과 COM receipt를 감사한다. nested의 겹치는 GT를 union occupancy mask 하나로 축약하지 않는다. 이번 학습에는 정답 pixelmask가 필요 없다.

train/cal 이미지는 중간 육안 점검에 사용한다. eval 이미지는 모든 threshold 선택이 저장된 뒤에만 root가 열며, 이전 R16/R17 eval과 CogBot 원본은 새 독립 성능 근거로 사용하지 않는다.

## 후보 실험

- full: 원래 전체RGB→240×152 검출. class-agnostic `1-Pbg` 후보와 R17 crop 추출을 그대로 사용한다.
- multiscale: full + 폭/높이60%인4개 모서리 타일. 타일마다240×152 검출 후 원본 좌표로 환산한다. 내부 타일 경계2px에 닿는 잘린 후보는 제외한다. 원본 바깥 가장자리 접촉은 이 규칙의 대상이 아니다.
- 중복 제거는 full 우선, 그다음 면적 큰 tile후보 우선으로 IoU>.7인 후속 후보를 제거한다. 포함관계 전체를 제거하는 NMS는 쓰지 않는다. 동일full 후보는multiscale에서도 보존한다. 임의class confidence로 bbox를 축소하지 않는다.
- candidate coverage, extra candidates, family별/node-container별 결과를 종류 무시 IoU≥.5 일대일로 비교한다. full/multiscale 어느 쪽이 좋은지 eval을 보고 정해 다른 결과를 버리지 않는다.

## 유효성 학습

full+multiscale train 후보(같은full의 중복 학습은 피하고 multiscale 집합을 사용)를 고정해 동일 crop으로 학습한다. sourceclosed_structure bbox와 maxIoU≥.7이면positive,≤.2이면negative, 중간은ignore다. 한 GT의 여러 중복 후보를 positive label로 볼 수 있으므로 inference dedup과 평가 일대일 매칭을 별도로 유지한다. GT 역할을 모르는 객체를 정답 구조로 창작하지 않는다.

기존2채널 객체 CNN의 encoder를 R17 checkpoint에서 가져오고 마지막 Linear만1024→2로 새로 초기화한다. seed1801, CPU4threads, AdamW lr.001, batch32(positive16/negative16),450steps 고정. augmentation/threshold 외 탐색 없음. positive와negative가 각24개 이상 있어야 실행한다. 학습 후 positive recall과negative recall 모두.9이상이어야 calibration/eval로 진행한다. 실패 시 train 그림/수치를 보존하고 eval을 열지 않는다. 이는 학습가능성 검사이지 독립 성공이 아니다.

유효성 threshold {.50,.70,.85,.95,.99}는 calibration의 **종류 무시 후보 precision1 및TP>0**을 만족하는 값 중 recall 최대, 동률은 높은 값으로 full/multiscale 각각 고정한다. 만족값이 없으면.95 진단fallback/gate실패다. 분류기 종류 confidence.95는 바꾸지 않는다. 모든 선택을 저장한 뒤 eval을 실행한다.

## 네 결과와 종료 기준

full_raw / full_valid / multiscale_raw / multiscale_valid 네 arm을 모두 보고한다. raw는유효성검사없음, valid는동일후보에학습된거부추가다. geometry coverage, 유효성 통과 후보 및 최종 종류+geometry 성능을 분리한다. 최종 TP/FP/FN/per-kind/음성FP를 기록하고4arm×16eval=64PPT를 native로 출력해 실제 COM 렌더한다.

연구 gate는 최종 precision1, recall≥.8, family별 recall≥.5, negative FP0 및 calibration gate 통과다. 비어 있는 결과의FP0만으로 성공 처리하지 않는다. 개선은 FP감소와 잃은 TP를 함께 판단한다. 실패를 성공할 때까지 조건 변경하는 것으로 구제하지 않는다.

formal 동결 뒤 기존 복잡 CogBot 원본에4arm을 그대로 적용해 실제 COM 및 후보 crop을 직접 확인한다. 수동17node ledger는 inference 뒤에만 읽는 개발용coverage 진단이며 독립정답이 아니다. 실제 원본에서 잘못된 도형이 남으면 제품 승격하지 않는다. OCR·연결·원본fill·adjustment회귀·인스턴스분할 구현은 이번 범위 밖이다. 해시·명세·입력·checkpoint를 실행 전후 확인하고 결과는새artifact폴더에만 저장한다.
