# R15.2-A source PPT 분기 대조 4개

`tools/r15_directed_fanout_controls.py`가 기존 deck/rect/label helper로 작성했다. `artifacts/r15-fanout-controls-v1/preregister.json`에 정답 관계와 보수적 arm의 생략 기대를 먼저 저장한 뒤 PPT를 만들었다. source PPT는 정답이며 runtime에는 실제 COM에서 나온 RGB만 전달한다.

모든 사례는 800×450에서 Read `[40,195,160,255]`, Build `[640,65,760,125]`, Check `[640,195,760,255]`, Write `[640,325,760,385]` 네 노드를 공유한다. 직선은 Read 오른쪽 중앙에서 각 leaf 왼쪽 중앙으로 간다. 선폭은 2pt이고 화살표는 leaf 쪽 triangle이다. bent의 위·아래 경로는 x=400에서 꺾인다. 선분을 조합한 bent source의 논리 관계와 개별 XML connector segment 수를 구분해 기록했다.

| 사례 | source 화살표 | arm의 기대 |
|---|---:|---|
| straight | Read→Build/Check/Write 3개 | 올바른 방향 관계 3개 |
| undirected | 0개 | 분기 전체 기권 |
| partial-arrow | Read→Build 1개 | 부분 방향 분기 전체 기권 |
| bent | 3개 | 지원하지 않는 굽은 분기 전체 기권 |

음성의 출력 기권은 source에 관계가 없다는 의미가 아니다. 이번 한정 arm이 승인하지 않는다는 기대다. 노드 후보/OCR 실패로 간선이 없는 경우는 올바른 분기 기권과 별도로 평가한다. 네 사례는 동일 템플릿 계보의 노출된 원인·회귀 대조이며 독립 일반화나 calibration/eval 표본이 아니다.

source XML에서 각 8개 shape(구조 4+텍스트 상자 4), picture 0, connector segment 및 arrowhead 수를 검사했다. 실제 PowerPoint 16.0의 800×450 렌더 4개를 직접 확인했다. 기존 helper의 테마 그림자가 source에 보이므로 그 조건을 포함한 대조이며 추론 전에 제거하거나 교체하지 않았다. RGB 변환 후 픽셀 동일성과 source PPT→COM receipt 해시를 검증했다.

- preregister SHA: `56f1c7e61fd9a161647c049b3f9d019c6b9530e708281c5a1c0f9f651da3044c`
- COM manifest SHA: `4ca75c8b7b8249b49f658d07413844a6d76d7280e434ed79b0f4bf05d3e227dc`
- RGB manifest SHA: `1441501432534bed5003e97a315229afff3812d0db5b78c53ce7628316a360ce`
- source receipt: `artifacts/r15-fanout-controls-v1/source-receipts.json`
- 렌더와 RGB: 같은 artifact의 `renders/`, `rgb/`
- 재검사: 같은 artifact의 `verify_rgb.py`(새 `rgb/` 생성 전용).

새 사진·다운로드·학습·holdout 접근 없이 source 대조 4건만 생성했다. 추론은 root SHA 동결 이후 별도 fresh artifact에서 수행한다.
