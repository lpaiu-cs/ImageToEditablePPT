# R15.1-A 원본 픽셀 이웃의 폐경계 보완

사용자 R15 실행 승인 후 첫 독립 arm. 고정 preset closed-native-v4는 바꾸지 않는다.

## 원인과 가설

RGB-only `inspect_closed_boundaries.py` 진단에서 original Working Memory/LTM/Slow API의 외곽과 일치하는 긴 Canny contour가 있었지만 parent=-1, contour area≈35–43픽셀로 닫힌 내부를 만들지 못했다. Reflection은 한 dark threshold에서만 폐윤곽이며 Canonical DB는 다른 shape family다. 모두 같은 원인이라고 묶지 않는다. 수동 장부는 이 진단의 평가에만 사용했고 후보 생성 입력이 아니다.

## 고정 보완 계약

원본 해상도의 각 Canny mask에 3×3 cross kernel(상하좌우1픽셀)의 morphological closing을1회 적용해 별도 제안 mask를 만든다. 크기를 이미지나 특정 누락 박스에 맞춰 늘리지 않는다. 원본 RGB/OCR/texture/연결 추적 mask는 변경하지 않는다. 이 연산은 후보 경계의 작은 디지털 끊김 보완이며 원본 픽셀을 다시 그리는 기능이 아니다.

기존 dimensions/면적/사각 경계/두 threshold의 원본1픽셀 합의/중복 제거 조건을 그대로 적용한다. 기존 union 후보는 먼저 유지하고 새 후보는 기존 후보와 중복하지 않을 때만 뒤에 붙인다. 기존 ID/기하를 바꾸지 않는다. 단독 open line/큰 틈을 폐박스로 받아들이지 않는 테스트와, 작은 틈을 보완해도 무근거 사진 프레임을 최종 승인하지 않는43개 회귀가 필요하다.

반경1 closing이 모든 종류의 틈을 정확히1픽셀까지만 메운다고 주장하지 않는다. 디지털 배열에 따라2픽셀 폭 틈도 합쳐질 수 있다. 따라서 아래 raw 지지 검사를 추가한다: 선택된 보완 contour의 모든 점이 해당 원본 Canny edge에서 Euclidean 거리≤sqrt(2) 안에 있어야 한다. 작은 틈에서도 이 검사를 넘으면 기권한다. 이 bound는 원본 픽셀 셀의 대각 이웃 범위이며 fitted bbox와 GT 사이의 오류 허용치를 늘리는 것이 아니다.

각 새 후보에 source arm, bbox, raw contour support max distance를 기록한다. 형상 내부/라벨/구조 역할 판정은 기존 R14 그대로 둔다. 부분 경계를 근거로 근거 없는 채움을 만들지 않으며, 모든 조건을 통과한 닫힘 복원만 기존 내부 채움 검사로 넘긴다.

## 판정

우선 작은 인공 기하 양성/음성 테스트 후 original fresh RGB→PPT를 실행·직접 렌더한다. 후보 ceiling과 실제 출력의 차이를 기록한다. 유용한 node/edge 손실이나 새 잘못된 관계가 있으면 기본 채택하지 않는다. 이후 복잡7/독립43을 같은설정으로 확인한다. 사진·icon·OCR cutoff는 변경하지 않으며 한 단계가 실패하면 실패를 남기고 원인을 좁힌다.
