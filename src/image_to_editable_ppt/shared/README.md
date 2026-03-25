# shared Namespace Rules

`shared/`는 비어 있어도 정상이다.

허용 기준:

- 순수 데이터 구조
- 저수준 IO helper
- v2 heuristic 가정이 전혀 없는 순수 helper

금지 대상:

- geometry scoring
- fallback logic
- selection heuristic
- reconstruction logic
- detector/parser decision code
- legacy stage semantics에 묶인 schema

현재 phase에서는 실제 이동을 하지 않고, 후보만 문서화한다.
