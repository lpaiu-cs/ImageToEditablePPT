# R10-O: 공간 OCR 근거를 이용한 중복 owner 해결

## 질문과 이전 접근의 한계

D-v2의 다중 atom 가로 행 조건은 짧은 CP/PP 라벨을 지원하지 못한다. 기존 positive를
전부 기권해서 얻은 안전성만으로 실제 중복 문제를 해결했다고 할 수 없다. D-v3의
관측/fixture 결함 수정과 독립적으로, 이미 사용하는 RapidOCR의 이미지 검출 위치를
공간 근거로 이용하는 새 연구 arm을 진행한다. 이전 D의 OCR 금지 입력 계약을 소급
변경하지 않는다. 새 arm은 RGB와 예측 owner만 입력으로 받고 OCR을 그 RGB에서 실행한다.

문자열 일치만으로 병합하지 않는다. 원 annotation/PPT/정답 ID/정답 노드 수는 추론에서
읽지 않는다. 기존 라벨은 운반하되 중복 판단에는 쓰지 않는다. 제품 코드는 유지한다.

## 단계1: 실제 관측 진단

동결 A-T의 spatial-overlap label_anchor cluster 전체를 자동으로 찾는다. transitive chain,
4개 초과는 기권한다. 세 알려진쌍을 ID별로 하드코딩하지 않는다. cluster bbox union에
2px padding, median RGB border16px을 적용하고 3배/4.5배 bicubic 확대에서 OCR한다.
각 인식의 원본 좌표 polygon, text, score와 입력/모델/코드 SHA를 기록한다.
이 단계는 관측만 하며 owner/PPT/GT 평가를 바꾸지 않는다. 관측이 유효한지 실제 RGB와
polygon을 육안 확인한 뒤 보수적 선택 조건과 반례를 고정한다.

## 선택의 필수 근거

- 두 확대에서 하나의 동일 공간 text 영역이 안정적으로 나타나야 한다. 여러 별도
  word/row가 있는 cluster는 합치지 않는다. OCR text도 두 확대에서 안정적이어야 하지만
  이것만으로 두 owner가 동일하다고 판단하지 않는다.
- OCR polygon과 원본 support가 서로 모순되면 기권한다. punctuation/부분 glyph를
  잃는 bbox를 단지 작다는 이유로 선택하지 않는다.
- 기존 owner 중 하나만 선택하며 bbox/ID를 GT alias나 평균 bbox로 바꾸지 않는다.
- score 역전/ID rename/순서 변경에 독립적이어야 한다. 근거 없는 representative는 기권한다.
- crop이 글자 일부를 잘라 동일한 단어처럼 보이게 하는 반례, 두 가까운 동일 문자열,
  별도행/세로/회전, 부분단어/점/밝은획, 선과접촉, tie와chain을 검증한다.
- 모델OCR의 오류 가능성은 남는다. 두scale 일치가 정답 보장은 아니다.

## 검증 및 실제 출력

진단→선택규칙/반례 잠금→수정 구현→단위/반례→실제15장 RGB-only 대조→별도 GT 평가→
실제 PowerPoint 렌더/육안 검토 순으로 진행한다. 실패하면 기록하되 끝내지 않고 원인에
따라 다음 build/가설로 이어간다. frozen 버전의 결과를 덮거나 지표를 소급 수정하지 않는다.
명백한 코드/fixture 계약 버그와 잘못된 과학 가설을 구분한다.

먼저 O-only를 기존 A-T와 비교하고, 효과가 확인되면 별도 C+O arm에서 source-centerline
보정을 결합한다. 살아남은 owner로 trace를 재실행하며 endpoint ID만 치환하지 않는다.
실제 duplicate FP 감소, 올바른 owner 보존, 새 관계 오류/누락, OCR 내용, native editability를
각각 평가한다. 개발15장 성공을 미관측 일반화나 실제 인간 수정시간 절감으로 부풀리지 않는다.
