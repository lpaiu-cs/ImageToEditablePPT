# R14 v3 독립 fresh43 감사: 회색 사진 내부 생략 회귀

v3는 icon-flow의 Input과 내부 몸통 후보를 생략했지만 gray-flow에서 Photo와 단색 채움이 다시 출력됐다. 새 양성4건 중3건이 빈 테두리 목표를 충족하고1건은 실패한다. 음성7건의 카드는 기권하며 기존32건의 출력 구조는 R11과 동일하다. v3도 완전한 내부 생략 정책 달성을 주장할 수 없다.

## 고정 실행

- root commit: `cd036c33247353f0071c80a9ec684e1776955507`
- artifact: `artifacts/r14-flow-fresh-v3`
- lock SHA256: `dac424203760594392a81ac768a7388161521afaaddeb8bd641da2e1f7cca8f5`
- 기존43 records를 그대로 사용하고 새11건부터 실행했다. source/RGB 해시 검증을 모든 건에서 통과했으며43건 모두 exit0이다.
- RGB부터 OCR·추론을 새로 실행했다. 이전 scene/PPT/정답 metadata를 입력하지 않았다. 고정 spatial/compact/flow flags이며 raw-branches는 껐다.

이번에는 전체43건이 완료되어 results.json을 정상 저장했다. v2의 중단된 부분 실행을 합쳐 완성한 결과가 아니다. 제품 코드·기준·입력은 수정하지 않았다.

## 결과와 원인

china-flow/flower-flow/icon-flow는 각각3도형·2라벨·2연결로 카드 내부를 비웠다. gray-flow는3도형·3라벨·2연결로 Photo가 남았다. 음성6개는 Read/Check만 남고 standalone은 완전 공백이다. 기존 양성12개44box/44label/24edge와 단독 사진20개의 빈 출력은 유지된다.

gray-flow closed:2의 raw_unexplained_fraction은 `.5183821125809053`이나, 경계 접촉 성분 제외 후 `.003617582321790485`가 되어 flat_owned_interior로 판정된다. 기존 texture fraction도 `.19968061747288576`으로 no-veto여서 frame 보완 대신 일반 경로로 출력한다. 경계와 연결됐다는 조건이 사진 내용까지 제거하는 반례다. v2에서 해결한 회색 사진이 v3에서 재실패했으며, fixture나 cutoff를 바꿔 숨기지 않았다.

icon-flow는 closed:3 frame을 보완하고 내부 closed:2를 omitted에 기록했다. 최종 XML에 내부 Input이나 몸통 도형이 남지 않는다. 이는 이 단순 아이콘 대조에 대한 확인이며 모든 무라벨 내부 조각이 비구조라는 증거는 아니다.

## 내부 구조·mutual 단위 검토

`tests/test_flow_frames.py`를 독립 실행해14 passed를 확인했다. 반복 내부 후보2개는 parent 보완을 거절하고, 상호 보완 후보는 frames에서 거절하는 동시에 omitted에 넣는 테스트를 포함한다.

추가 정책 단위 검사에서 무라벨 child `[120,175,150,195]`와 native로 표현 가능한 child→seed 연결을 scene_pair에 넣었다. parent 보완은 기권하고 child는 omitted에 들어가지 않았다. 두 texture통과·nontext 후보 mutual의 경우 omitted가 frame/seed 둘 다이며, probe처럼 ordinary admitted_ids에서 이를 빼면 빈 집합이 됨을 확인했다. v2의 ordinary fallback 문제는 이 단위 범위에서 수정됐다.

코드 읽기에서 probe의 emit 전후 keep 모두 omitted를 빼는 것, 라벨 없는 단일 조각만 생략 대상으로 남기는 것, 라벨 seed·native 연결 child·내부 후보2개 이상은 보호하는 것을 확인했다. 단위 scene 검증을 실제 RGB/OCR에서 모든 구조를 보호한다는 일반 보장으로 확대하지 않는다.

## native 검증

43개 실제 PPT XML을 검사했다. 보완3건은 noFill·빈 텍스트이며 승인에 사용한 두 연결의 stCxn/endCxn ID가 각각 seed→frame/frame→seed와 일치한다. 모든 출력 picture0이다. 기존32건은 emitted_scene 전체 JSON이 R11과 동일하다. `verify.py`와 `verification.json`에 검증을 보존했다.

사진 원본2개·합성 아이콘1개의 파생 대조라는 제한은 유지한다. root 복잡7개 결과는 별도 검증이며 이 보고서에서 직접 수행했다고 주장하지 않는다. v1/v2/v3 실패는 각각 보존했다.

## 실제 COM43 완료

root 슬롯 반환 후 기존 POWERPNT guard를 통과해43개 전체를800×450으로 렌더했다. 모든 PPT/PNG receipt 해시가 일치하고 기존 단독 사진20개는 전 픽셀이 흰색이다. COM manifest SHA256은 `94b007395d19698eb5078b47472aafc7f874ce9e95622d7590ee103a2065f294`다. 실제 gray-flow PNG에서 Photo와 짙은 채움을, icon-flow PNG에서 내부가 완전히 빈 테두리를 직접 확인했다. 완전43 receipt는 verification.json 및 renders/powerpoint_render_manifest.json에 보존했다. COM은 즉시 반환했다.
