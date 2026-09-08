# R8-A 결과: native 부착 지원 확인, 구조 복원 후보는 미채택

## 판정

**text-only native owner에 실제 연결을 부착하는 표현은 동작한다. 그러나 전체 복원
후보는 제품에 채택하지 않는다.** 기존 OCR과 변경 OCR의 고정 scene 각각 15개를
같은 어댑터에 통과시키고, 총 30개 실제 PowerPoint 렌더를 원본과 육안 대조했다.

새 검출·추적·OCR·GT 추론은 없었다. 모든 owner/경로/방향을 고정했으므로
이번 차이는 native 출력 지원의 효과이며 모델 성능 향상이 아니다.

## 2×2 대조 결과

관계는 TP / FP / FN, 라벨은 일치 node의 정답 / 오답 / 공백이다.

| OCR / native 출력 | 최종 관계 | 라벨 | 상태 |
|---|---:|---:|---|
| R8-P 기존 OCR / 기존 writer | 22 / 2 / 45 | 62 / 0 / 29 | 동결 기준선 |
| R8-T 변경 OCR / 기존 writer | 22 / 2 / 45 | 82 / 1 / 8 | 미채택 진단 |
| A-P 기존 OCR / attachment | 26 / 5 / 41 | 62 / 0 / 29 | 미채택 진단 |
| A-T 변경 OCR / attachment | 26 / 5 / 41 | 82 / 1 / 8 | 미채택 진단 |

기존 text-only 연결 기권 14개 중 7개가 출력됐다. 나머지 7개는 기존 native preset의
4px 적합 기준에 걸렸다. 전체 추적 51개 중 최종 31개 출력, 20개 fitting 기권이다.
증가한 7개는 **관계 정답 4개와 오답 3개**다. 연결을 더 내보내는 것만으로 확실성이
개선되지는 않았다. 각 source scene의 추적 성적은 35 / 16 / 32로 불변이다.

## 육안과 오류 경계

- A-P의 트리들은 글자 없이 선만 일부 생긴다. native binding이 있고 bbox가 검출됐어도
  사용자가 읽을 수 있는 노드가 없으므로 유용한 트리 복원으로 세지 않는다.
- A-T의 `tree_1302_00036`은 상단 중복 CP/CP.와 중앙 연결 1개만 보인다.
  도착 node V가 OCR 공백이라 끝점의 의미도 표시되지 않는다.
- A-T의 `tree_1302_00079`는 라벨 8개가 맞아도 ROOT–runs 연결 1개만 나온다.
  추적된 대각선 6개는 적합 오차 약 4.81–6.18px로 탈락한다. 원본은 단순한 트리인데
  추적 polyline/끝점과 native 직선 사이에서 손실이 난다. 기준 완화만으로 해결했다고 하지 않는다.
- A-T의 `tree_1302_00149`는 VP 아래 두 가지와 오른쪽 세로 가지가 보인다.
  상단 Adj–PP에는 겹친 owner와 연결이 겹친다. 중복 문자 PP/Adj도 그대로 남는다.
- 두 arm의 나머지 12장씩, 총 24개 non-tree 렌더는 각각 자기 기준선과 PNG SHA까지 같다.

신규 관계 FP3개는 모두 끝점 중 최소 하나가 일대일 평가에서 매칭되지 않은 **중복
검출 owner ID**에 묶인 사례다. CP→공백(V) 1개, 중복 Adj→PP 2개다. 이번 adapter가
방향을 뒤집은 것으로 분석하지 않는다. 첫 사례는 시각적으로 올바른 위치에 선이 있을
수 있어도 endpoint 객체 identity 계약에서는 실패이며, 중앙 두 선은 실제 중복 연결로
겹쳐 보인다. 기존 매칭 규칙을 사후 바꿔 정답 수를 늘리지 않는다.

## 검증

- 30개 source_scene 전체가 각 기준선과 동일함을 확인했다.
- 30개 emitted semantic shape(ID/종류/bbox/문자 등)가 각 기준선과 동일하다.
- 30개 PPT의 실제 객체 ID, stCxn/endCxn owner binding, PPT/render SHA 확인. 래스터 0.
  원래 owner만 borderless native geometry로 표현하며 별도 helper object를 추가하지 않았다.
- 각 worker의 Python open allowlist 위반 0. 추론에 annotation/offline target을 넣지 않았다.
- 어댑터 전용 및 기존 runtime 40개 통과, 전체 458 passed / known failure 2 xfailed /
  기존 경고 9개. xfail 두 개는 별도 v1 provider의 알려진 화살표 반전이다.
- 제품 emitter/enum/writer와 동결 R8-P/R8-T 산출물은 변경하지 않았다.
- 실제 렌더/재열기 확인은 완료했지만 사용자의 이동·reroute·후편집 시간은 측정하지 않았다.

학습 작업의 adapter 커밋 `6a9d974`를 루트 `fe1930c`로 통합했다. 원래 문자열/폰트/wrap은
semantic reference의 text frame을 보존하며, blank/overlap 정책은 adapter 명세대로다.
`visible_label_count`는 정답 라벨 수나 중복 없는 객체 수가 아니다.

## 다음 우선순위

1. text-only 중복 검출을 source evidence 기반으로 정리하고 owner identity를 안정화한다.
   GT ID나 문자열로 합치지 않으며 서로 다른 가까운 라벨을 합치는 반례가 필요하다.
2. 대각선의 source trace와 실제 직선 fitting 불일치를 시각 진단한다. 허용 오차를
   느슨하게 만들어 통과시키기 전에 glyph/owner 경계·투영·분절 경로의 원인을 분리한다.
3. OCR의 CP→CP. 및 작은 글자/공백은 별도 과제다. adapter의 성공으로 감추지 않는다.

두 트랙은 입력/출력 계약과 실패 근거를 공유했다. 이 단계에서는 신규 학습이나
제품 승격을 진행하지 않는다. 이미 본 합성 validation의 진단을 미관측 일반화 또는
인간 시간 절감으로 보고하지 않는다.
