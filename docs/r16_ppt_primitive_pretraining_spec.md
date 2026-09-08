# R16-PG: PPT 기본 도형 선학습 — 최초 실행 계약

2026-09-09. R15 및 Phase16 formal holdout과 분리된 새 연구 실험이다. 사용자 승인: PGDPNet 연구를 참고해 PPT 도형 선학습을 진행한다. 제품 기본값은 변경하지 않는다.

## 참고 연구와 적용 범위

[PGDPNet, IJCAI 2022](https://arxiv.org/abs/2205.09363)의5.3절은 픽셀 의미 분할과 instance embedding을 결합해 가늘고 겹치는 기하 요소를 추출한다.5.4절은 시각·위치·종류 정보를 이용해 요소 관계를 학습한다. [공식 구현](https://github.com/mingliangzhang2018/PGDP)은 평면기하의 점/선/원과 수학 기호를 대상으로 하며, 데모의 텍스트 내용은 GT에 의존한다고 명시한다. 이를 PPT 변환 모델이나 실제 OCR 성공으로 해석하지 않는다.

가져올 원리는 요소 추출/관계 예측을 분리해 감독하고 각각의 손실을 관측하는 것이다. 수학 기호 체계, GT 텍스트, 원본 데이터셋·가중치·옛 CUDA/DGL 환경은 가져오지 않는다. 이번은 **닫힌 도형 영역 선학습의 최소 대조 실험**이며 PGDPNet 재현, instance embedding 또는 GNN 구현으로 부르지 않는다. 연결의 픽셀/끝점/관계 학습은 후속 단계다.

## 최초 데이터 계약

1. 실제 source PPT6종: rectangle, rounded rectangle, ellipse, diamond, parallelogram, cylinder. 각 preset은 구조 역할을 부여해 작성한다. 모든 native 도형이 구조라는 일반 규칙은 아니다.
2.800×500 source PPT를 실제 PowerPoint COM에서320×200으로 렌더한다. 각 입력과 동일 geometry/adjustments를 가진 occupancy mask용 PPT도 같은 COM에서 렌더한다. 입력에는 원래 스타일, mask에는 흰색 불투명 채움/선 없음/검은 배경을 사용한다. 서로 겹치지 않는 source bbox 안의 purewhite 점유 픽셀을 해당 도형 class palette로 변환한다. 소유자 bbox 밖 purewhite, bbox overlap은 오류다. mask는 **도형 점유 영역**이지 원본 잉크·화살표·문자 픽셀 GT가 아니다. source내 문자에 대해서는 amodal owner영역이다.
3. 원본 ID/도형종류/bbox/adjustments, source 및 mask PPT SHA, 두 render SHA, 변환 palette mask SHA, generator SHA를 묶는다. 검정0/순백점유 외의 antialias 경계는 ignore255로 처리하고 도형1..6 palette는 변환된 정답파일에만 둔다. 같은 source의 input/mask는 동일 split이다. 최초v1의cyan cylinder mask는 PPT preset의 topface lighten을 AA로 오인해 학습 전에 사용중지했다. v1은 보존하고 white occupancy pass를 쓰는v2로 새로 생성한다. 결과를 보고 정답을 바꾸는 수정이 아니다.
4. stage `primitive`: train24장, 매장 단독 도형1개(종류별4). stage `scene`: train24/calibration8/eval8장, 매장 겹치지 않는 도형6개(종류별1), 배치 순서 독립 shuffle. scene마다 위치·크기·색·선폭·선택적 글자 변화. split별 seed/scene ID 분리, 파생 이미지의 cross-split 분리 금지.
5. 음성 `negative`: train4/calibration2/eval2장, 텍스트와 열린 선만 포함하고 구조 mask는0. 자연사진의 독립 음성 데이터가 없으므로 사진 의미 일반화는 이번에 주장하지 않는다. 총72장×input/mask=144개의1slide PPT. duplicate RGB SHA를 검사한다.
6. 초기 실험은 회전/가림/overlap/connector 없는 도형 학습으로 제한한다. 이 조건을 충족하지 못하는 복잡 이미지의 성능은 별도 외부 진단이다. 기존 Phase16 holdout/val/test payload는 열지 않는다.

## 모델과 비교

기존 `ml.connector_segmenter._UNet`을 재사용하고 마지막 head만 background+6종으로 바꾼다. 입력은 전체 RGB320×200, source bbox를 crop 입력으로 주지 않는다. 학습은240×152로 resize(8의 배수), 추론 역시 동일 크기를 사용한다. target은 nearest resize한다. 점유 영역의 full-frame semantic segmentation이며 touching/overlap instance 분리는 지원하지 않는다.

CPU PyTorch 환경에서 seed1601,4threads,batch4,AdamW(lr.001),class-balanced cross entropy(train pixel빈도 inverse sqrt, ignore255)로 고정한다. augmentation/hyperparameter search는 하지 않는다. 아래3개 arm을 동일 초기 state에서 시작한다.

- `scratch80`: scene+negative80steps.
- `pretrain80_scene80`: primitive80steps 후 새 optimizer로 scene+negative80steps.
- `scene80_scene80`: scene+negative80steps 후 새 optimizer로 scene+negative80steps. 동일 추가 계산량 대조.

각 stage의 데이터 추출 RNG를 고정한다. 마지막 scene80steps의 batch 순서는 세 arm에서 같게 한다. 같은 scene80을 반복하는 compute control도 데이터 다양성 증가와 초기화 효과를 구분할 필요가 있다는 한계를 기록한다. eval은 모든 학습/선택 후에만 사용한다. calibration에서 각 arm의 score threshold를 {.50,.70,.85,.95} 중 정한다: object precision1을 만족하는 후보 중 recall 최대, 동률은 높은 threshold. 만족 후보가 없으면.95를 쓰되 calibration gate 실패로 표시한다.

## 출력과 평가

각 pixel의 argmax class map에서 confidence≥threshold인 connected component를 얻는다. 최소 면적16px, bbox가로세로≥4px, 경계 clipping/해상도 오차를 공개한다. 도형종류별 component bbox를 같은 native PPT preset으로 출력한다. 객체별 shape로 쓰며 raster 삽입·GT 라벨·GT bbox·GT source PPT 입력은 금지한다. 최초 출력은 라벨/연결 없는 도형-only이므로 최종제품 성능이라고 부르지 않는다.

GT matching은 kind동일+IoU≥.5 one-to-one. pixel macro IoU, preset별 object precision/recall, 빈 음성의 false positives를 따로 보고한다. 일치 class의 bbox만 맞은 성공이 원래 곡률/조절값 복원을 의미하지 않는다. 단색 기본preset의 adjustment회귀·fill·OCR는 이번 미구현이다. geometry 오차1px 단독으로 실패처리하지 않는다.

선학습 효과는 `pretrain80_scene80`이 `scratch80`뿐 아니라 같은 계산량 `scene80_scene80`에 비해 precision을 떨어뜨리지 않고 recall이 증가했는지로 판단한다. 단일 seed·작은 합성 자료의 결과이므로 통계적 일반화 주장 금지. 기준미달이면 원본/예측/mask 및 실제 출력COM을 확인하고 그대로 실패기록한다. 수치 결과를 보고 학습량이나 threshold 집합을 바꾸지 않는다.

별도 독립 트랙은 source/GT mask/receipt/분할을 감사한다. 최종 PPT는 대표 eval최소2개와 음성1개를 COM으로 렌더하여 육안 검증한다. 모델은 연구 artifact로만 저장하고 제품CLI에 붙이지 않는다.
