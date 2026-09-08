# R8-A: text-only native attachment의 고정 scene 대조

## 사전 결정 및 비교군

어댑터 커밋 `6a9d974`(루트 `fe1930c`)의 실제 PPT 검증이다. 새 검출/추적/OCR을 하지
않는다. 두 동결 source_scene 각각 15개를 사용하여 출력 단계만 바꾼다.

| OCR | 기존 writer | attachment adapter |
|---|---|---|
| 기존 OCR | 동결 R8-P | 이번 A-P |
| 변경 OCR | 동결 R8-T, 미채택 진단 | 이번 A-T |

source는 두 동결 benchmark가 결합한 results.json SHA로 검증한다. 모든 source shape의
ID/의미/좌표/문자와 모든 추적 연결/경로/방향을 그대로 유지한다. R8-T의 오인식1개와
중복 문자3개를 교정하지 않는다. GT는 변환 이후 별도 evaluator에서만 읽는다.
offline source PPT target 역시 이번 변환에 사용하지 않는다.

기존 label_anchor attachment 필터를 제거하고 정규화된 전체 scene을 연구 adapter에
넘긴다. adapter는 writer 경계에서만 borderless/noFill rect owner를 사용하고 semantic
text frame을 보존한다. 기존 native 4px fitting 기준/끝점 검증은 바꾸지 않는다.
추가 보조 객체/래스터/자유선 우회는 금지한다. 빈 owner 및 중복 owner는 이 대조에서
삭제하거나 합치지 않는다. 빈 문자에 연결이 생기는 것은 인식 성공이 아니다.

## 평가

두 arm 각각 15개 실제 PowerPoint 렌더를 원본과 대조한다. 방향 관계 TP/FP/FN,
최종 fitting 기권, node/라벨 불변, 실제 shape/connector ID 및 attachment binding,
래스터 0을 검사한다. adapter를 쓰지 않는 12장의 native render SHA도 비교한다.

최종 관계가 증가해도 참/거짓을 분리한다. 특히 기존 14개 text-only 기권이 제거되면서
잠복한 추적 오답이 드러날 수 있다. 이를 출력 지원 성공과 구조 복원 성공으로 혼동하지
않는다. 파일 재열기와 native binding 검증은 사용자 이동/재라우팅·수정 시간 실험이 아니다.

이미 본 합성 validation의 cached scene 대조이며 미관측 일반화가 아니다. 제품 승격을
하지 않고 결과에 따라 다음 병목을 선택한다. 두 기존 arm과 이번 산출물은 덮어쓰지 않는다.
