# R14 v4 독립 fresh43·실제 COM 감사

사전 고정한 새11건에서 연결형 양성4건은 모두 내부가 빈 테두리로 출력됐고, 음성7건의 카드는 기권했다. 기존32건은 R11과 동일한 emitted_scene을 유지했다. 전체43개 실제 COM 렌더와 receipt 검증을 완료했다. 이는 노출된 소규모 대조의 회귀 결과이며 일반적인 사진 의미 분류나 production 승인이 아니다.

## 고정 실행

- root commit: `a22bc164ec6db1fb91799526cf72acb95db43c12`
- artifact: `artifacts/r14-flow-fresh-v4`
- lock SHA256: `7b2668f6596bb41df62ee5adc7b1138239be774eba91baa29169002c4bd8b0d1`
- R14 이전 버전과 동일43 records이며 새11건부터 실행했다. source/RGB 해시를 매 건 확인했고 모두 exit0이다.
- 고정 spatial/compact/flow probe를 RGB부터 실행했다. raw-branches는 껐고 source PPT/객체 역할/정답·OCR cache는 추론 입력에 전달하지 않았다.

v1–v3 실패·부분 실행은 각각 보존했다. v4는 별도43건 fresh 실행이며 이전 성공분을 합친 결과가 아니다. worker는 제품 코드나 관측 cutoff를 수정하지 않았다.

## 결과

| 집합 | 건수 | 도형 | 라벨 | 연결 | 관측 |
|---|---:|---:|---:|---:|---|
| 기존 양성 |12|44|44|24|R11 emitted_scene 전체 동일 |
| 기존 단독 사진 |20|0|0|0|실제 COM도 전 픽셀 흰색 |
| 새 연결형 사진/아이콘 |4|12|8|8|카드4개 no-fill·빈 텍스트, seed label 유지 |
| 새 음성 |7|12|12|0|카드 기권, standalone 완전 공백 |
| 합계 |43|68|64|32|picture0 |

새 양성은 china/flower/gray/icon-flow다. 각 카드 내부의 Photo/Input과 그림이 생략되고 관측된 테두리와 두 방향 연결만 남는다. 음성은 both-in/out, one-way, no-arrows, same-port, failed-chain, standalone이다. 음성의 기권은 대상 카드에 적용하며 정상 Read/Check seed는 유지된다.

모든43 PPT XML을 읽었다. 보완4개 카드의 noFill·빈 a:t와 source witness 각각의 실제 stCxn/endCxn attachment ID를 확인했다. icon 내부 몸통 후보도 최종 출력에서 생략됐다. 기존32건은 전체 emitted_scene JSON 동등성으로 정상 라벨과 연결 유지 여부를 확인했다.

## 실제 COM과 증거

root 슬롯 반환 후 기존 POWERPNT guard를 통과하여 전체43개를800×450으로 렌더했다. 모든 PPT/PNG receipt SHA가 일치한다. 새11개 contact sheet를 직접 확인하여 양성4개 내부 생략과 음성7개 카드 기권을 확인했다. 회색 사진과 아이콘의 과거 캡션 재출력 실패가 이번 출력에는 없다. COM은 즉시 반환했다.

- COM manifest SHA256: `cc766fbfadf567454cd6e719118387483192e57101b29082e0601c871fa1fa5c`
- `results.json`, 각 `runs/<id>/native/result.json`: fresh 추론 결과
- `verification.json`, `verify.py`: XML/이전 결과 동등성/receipt 검증
- `renders/powerpoint_render_manifest.json`: 완전43건 receipt
- `new11-contact-sheet.png`: 직접 확인한 실제 새 출력

## 코드·단위 검토와 제한

v4는 경계에 연결된 성분 전체를 삭제하지 않고 원본 마스크 경계로부터 max(2,3s) 거리 이내 픽셀만 제외한다. `_fit`이나 OCR 수치를 조정하는 변경이 아니며 v3의 회색 사진 내용 전체 소실 원인을 제한한다. 단위 `tests/test_flow_frames.py`를 독립 실행해14 passed를 확인했다. 다만 경계 대조의 선 두께가 v3의12에서 v4의6으로 변경됐으므로 동일14 fixture를 그대로 통과했다고 표현하지 않는다. 고정 폭보다 두꺼운 테두리의 일반적인 보호는 검증하지 않았다.

내부 labeled/native-linked child·복수 후보 보호와 mutual ordinary 기권은 v3의 독립 단위 검토 범위가 유지되는 코드다. 이번43개는 그 모든 구조적 경우의 새로운 RGB 대조가 아니다. 단일 무라벨·무연결 조각 생략을 일반 비구조 분류 성공으로 해석하지 않는다.

사진 원본2개와 합성 아이콘1개를 반복 사용하는 개발 대조이며 새 holdout·훈련·다운로드는 없다. root의 복잡7개·편집 probe·전체 회귀 결과는 별도 검증이다. 이 결과는 검토 가능한 부분 초안의 제한된 정책 회귀 근거이며 실제 사용자 수정시간 감소나 무조건적인 채택 승인을 대신하지 않는다.
