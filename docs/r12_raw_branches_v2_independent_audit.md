# R12 raw-branches v2 독립 재검증

v1의 회색120 교차 반례는 v2에서 기권한다. 동일32 RGB fresh 회귀는 R11과 같은 native 구조를 유지했다. 이번 검토 범위에서 추가 코드 결함은 확인하지 못했으나, 새 분기 복원의 효과나 일반 교차 검출 안전성을 확정하는 결과는 아니다.

## 고정 경계

- root: `b400dc305b0b80d12b41e92b7d9b92777bf1319b`
- worker cherry-pick: `eab393e`
- artifact: `artifacts/r12-raw-branches-v2`
- lock SHA256: `a32aa9e4304a9c335d719dc83b7e3dbbc4ec6a5cc609ab20a367be972034490e`
- R11/R12v1과 동일한32 records를 사용했다. 매 건 RGB/source 해시를 검증했고 이전 모든 R11 flags에 `--raw-branches`를 추가해 RGB부터 OCR·추론을 새로 실행했다.

코드 읽기에서 raw_components=True만 정수 luminance<130 mask로 바뀌었음을 확인했다. 이는 B-v1 및 H의 mask 식과 일치한다. raw_components=False는 기존 stroke_mask와 closing/dilation을 그대로 사용한다. `_fit`과 H의 수치 기준, LINE fallback은 변경되지 않았다. 단순히 방향 판정 실패를 막는 수정이 아니라 곁선이 fit 이전에 제거되던 원인을 수정했다.

## 회색 교차 반례

v1에서 보존한 재현 생성 코드를 사용하고 기대 결과만 기권으로 검사했다. 원본 RGB SHA256은 동일한 `07815a30b1b6c092b164f5fdbe79f02c849ffedfe4c09c7450fff14bce114cb2`다.

v2는 added0, seed_pixels741, seed_max8, nonlinear_or_competing_seed로 기권한다. 같은 RGB의 B-v1 원본 mask 결과와 일치한다. `gray-crossing-repro.py`, `gray-crossing.png`, `gray-crossing.json`을 새 v2 artifact에 보존했으며 v1 파일은 수정하지 않았다. 이 반례는 두 owner를 직접 제공하는 기하학 단위 검사다.

독립적으로 `python -m pytest tests/test_raw_branch_completion.py -q`를 root에서 실행해 **9 passed**를 확인했다. 회색 교차·검정 교차·끊김·곡선·중복·제3 owner 및 default 경로 비교가 포함된다. root가 보고한 더 큰 테스트 합계와 혼동하지 않는다.

## fresh32 native 검증

모두 exit0이며 전체 emitted_scene이 R11과32/32 동일하다. 새 raw 추가 연결은0이다.

| 입력 | 건수 | box | label | edge |
|---|---:|---:|---:|---:|
| 양성 도식 |12|44|44|24|
| 사진 변형 |20|0|0|0|

양성12개 PPT XML의 실제 shape ID와 connector stCxn/endCxn을 대응해 각각 Read–Build, Build–Check를 확인했다. 사진20개 XML에는 shape/edge/picture가 없다. `verification.json`에 각 건의 JSON 동등성·XML pair·raw 추가 수를 보존했다. 이 작업에서는 **COM을 사용하지 않았으며**, 이전 렌더를 새 실행 증거로 재분류하지 않았다.

## 남은 범위

사진은 원본2개의 파생20개이며 이32건에는 새로운 분기 추가 양성이 없다. 따라서 이 결과는 회귀 유지와 특정 안전성 반례 수정의 증거다. 복잡7개에서의 추가 연결과 실제 렌더는 root의 별도 검증 범위다. luminance cutoff 밖의 낮은 대비 곁선, 모든 교차·분기 의미, 방향 모호 LINE의 일반 안전성은 검증하지 않았다. spec은 cutoff 밖 제한을 명시하고 있으며 이를 새 결함으로 중복 보고하지 않는다.

제품 코드나 판정 기준을 수정하지 않았고 새 holdout·학습·다운로드를 사용하지 않았다. 고정 CLI 채택 판단은 root의 별도 복잡 입력 검증과 합쳐 내려야 한다.
