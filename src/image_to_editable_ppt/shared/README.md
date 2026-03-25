# shared Namespace Rules

`shared/`는 여전히 최소한만 유지한다.

현재 실제 추출물:

- `BBox`
- `Point`
- `ImageSize`

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

원칙:

- 애매하면 shared로 올리지 않는다.
- 재사용 가치보다 설계 오염 위험이 더 크면 v3 내부에 남긴다.
