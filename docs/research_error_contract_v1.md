# 연구 오류 분류 계약 v1: 좌표 차이와 구조 손실 분리

## 승인 및 적용 범위

사용자는 1px 위치 차이를 그 자체로 복원 실패로 취급하지 말고, 다음 버전의
픽셀/평가 계약을 수정해 계속 연구하는 방향을 승인했다. 이 문서는 그 구분을
고정 owner/ID 대조용 별도 평가기로 구현하기 전 작성한 계약이다.
기존 C-v1, C-v2, D-v1 결과와 사전 기준은 소급 변경하지 않는다.

## 서로 다른 네 가지 판정

1. **실행 오류**: import/구문/IO 등으로 의미 있는 관측이 수행되지 않음.
2. **좌표 계약 불일치**: 실제 래스터 생성 좌표와 기대 좌표의 체계가 다름.
   C-v1의 1px 차이 두 건이 해당한다. 테스트 실패 이력이지 제품 품질 실패가 아니다.
3. **기하 차이**: 객체·글자·관계가 같은 상태의 위치/경로 차이.
   source px와 이미지 대각선 대비 비율을 연속값으로 보고한다. 0.8px 또는 1px 하나로
   제품 pass/fail을 결정하지 않는다. native 4px fit gate는 별도 구현 조건이며 유지한다.
4. **구조/내용 차이**: 객체 추가/삭제, 종류·텍스트·owner·방향·연결 관계 변경.
   좌표가 완전히 같거나 작게 달라도 별도 표시한다. 이것도 대조 방향에 따라 개선일 수
   있으므로 단순히 차이가 있다는 이유로 실패라고 부르지 않는다. GT 별도 평가와 육안
   확인을 통해 실제 손실/개선을 판단한다.

한 결과에 기하 차이와 구조 차이가 함께 있을 수 있다. 둘을 하나의 점수로 합쳐 숨기지 않는다.
작은 점이 실제 구두점인지 잡음인지는 픽셀 수만으로 확정하지 않는다. 의미가 모호한 관측은
미확정으로 보고하며, '1px이므로 버린다'와 '1px이므로 의미정보다' 모두 금지한다.

## 제한된 평가기

`research.revision_assessment`는 동일 이미지 좌표계·동일 ID 체계에서 scene 두 개의
변화를 비교하는 offline 전용 도구다. RGB→PPT 추론 함수에서 import하지 않는다.
GT와 prediction 사이 일반 객체 매칭기로 사용하지 않는다. 특히 D-S가 의도적으로 지운
ID를 잘못된 삭제로 판정하는 용도로 사용하지 않는다.

입력은 scene JSON 두 개다. 중복 ID, 비유한 좌표, 서로 다른 이미지 크기는 오류다.
shape의 label/kind/owner kind와 connector의 source/target/arrow flags/kind를 비교한다.
connector ID가 같아도 관계를 뒤집으면 구조 차이로 기록한다. ID 기반 제어 대조이므로
source/target 표기의 역전도 표시하며 그래프 동형성/일반 의미 동등성을 주장하지 않는다.
shape bbox의 최대 corner 이동, connector의 두 endpoint 최대 이동을 원본 px로 보고한다.
endpoint가 같고 내부 경로만 바뀐 경우에도 geometry 변경으로 표시하지만, endpoint 측정이
전체 경로 오차라고 주장하지 않는다. path sample 수가 달라도 비교 가능해야 한다.

출력은 structural_changes, geometry_changes, metadata_changes와 단위 명시다.
confidence/provenance 차이는 metadata이지 품질 판정이 아니다. pass/production 승인 필드는 없다.
typed EmitScene의 shape/connector와 별도 texts/residuals도 누락 없이 비교한다.

## 구현 전 고정 대조

- 완전 동일 scene: 변화 없음.
- 동일 ID/내용/관계를 유지한 1px 전체 평행 이동: 기하만 변경.
- 큰 이동: 기하 차이가 커짐. 임의 자동 품질 pass/fail 없음.
- 같은 endpoint와 다른 내부 경로: path 변경과 endpoint 0px를 함께 기록.
- endpoint 숫자는 같지만 target ID 변경: 구조 차이.
- 방향 반전, connector 삭제, shape 삭제, CP→CP., 종류 변경: 각각 구조 차이.
- confidence 변경: metadata만 변경.
- 중복 ID, NaN, 서로 다른 이미지 크기: 입력 오류.

대조 통과 후 동결 A-T→C-v2 source scene과 emitted scene 각각에 적용한다.
원래 GT 기반 native TP/FP/FN 성적을 덮어쓰지 않고, 기하6개 변경과 실제 출력 연결6개
증가라는 서로 다른 경계를 명시한다. 이것은 새 모델 개선 실험이 아니라 결과 해석 검증이다.
