# P2v2 및 inner_boundaries 독립 재검사

기존 fixture를 변경 없이 새 snapshot에 실행했다. root runtime 변경 없이 감사 runner에 `--inner-boundaries` 옵션만 추가했다. 기본 호출 경로는 그대로 유지하며 과거 결과를 덮어쓰지 않았다.

- owner SHA: `64df060f5a3c93198fb877a35f6f7d9f47c1fcb503d7e547349bf1b5d7b07766`
- proposal SHA: `e7e1b6a82a49c811eee305f3fa6b327f753b5622e4c48987b5f5340454f1b925`
- owner 24 결과: `artifacts/r10-owner-region-p2-v2-results`
- geometry 기본 96 결과: `artifacts/r10-p-independent-p2-default-results`
- geometry 옵션 96 결과: `artifacts/r10-p-independent-p2-inner-results`

## 부모 영역

얇은 자식 scale2 두 RGB는 자식 text bbox 100% 제외, 자식 내부 부모 소유율 0%로 수정됐다. 실제 raw closed hole이 높이 gate에서 탈락했던 두 반례의 해결이다. scale1 두 RGB는 여전히 text bbox 제외 0%, 자식 내부 부모 소유율 100%다. 이 두 입력에서는 기존 raw contour 감사가 자식 전체에 대응되는 hole을 찾지 못했다. 따라서 **얇은 자식 4개 전체 해결은 아니다.**

나머지 닫힌 자식 16 RGB는 이전과 동일하게 자식 영역 전체 제외/정확한 부모색이다. 열린 outline 진단은 scale1 둘 정상, scale2 둘 누출과 pink 색 오염으로 이전과 같다. 부모 제목은 24개 모두 제외되지 않았다. 모든 RGB 불변성을 확인했다. 실제 OCR 및 PPT는 실행하지 않았다.

## 새 내부 경계 옵션

동일 proposal snapshot 기본 호출은 56 pass / 16 formal fail / 24 diagnostic으로 기존 결과와 같다. `inner_boundaries=True`는 65 pass / 7 formal fail / 24 diagnostic이다. 기존 기대값을 바꾸지 않았다.

| 종류 | 기본 선택 개수 분포 | 옵션 선택 개수 분포 |
|---|---|---|
| rectangle / colored_rectangle | 각각 1개×3, 0개×5 | 각각 1개×7, 0개×1 |
| adjacent | 2개×3, 0개×5 | 2개×7, 0개×1 |
| nested_white | 2개×5, 0개×2, 1개×1 | 2개×5, 0개×1, 1개×2 |
| nested_blue | 2개×6, 0개×2 | 2개×6, 1개×2 |
| photo_frame | 1개×3, 0개×5 | 1개×7, 0개×1 |

옵션의 일반 양성 실패 3건은 모두 scale2/AA1/width1의 누락이다. 나머지 formal 실패 4건은 nested white/blue의 scale1/AA1/width1과 scale2/AA4/width1이다. 선택 bbox는 각각 `[84,84,197,137]`, `[168,168,393,273]`이며 실제 내부 경계에 대응한다. `not_single` 계약 위반은 보존하지만 이를 오합병으로 부르지 않는다. 부모 외부 경계까지 복원했다는 주장도 하지 않는다.

open / ellipse / diamond / shadow는 옵션에서도 각각 8개 모두 abstain이다. glyph_hole은 8개 모두 2경계, table은 7개 6cell / 1개 2cell로 변하지 않았다. photo_frame 선택이 3개에서 7개로 늘어났으므로 geometry 복원 증가를 semantic diagram 판별 개선으로 해석하지 않는다.

이 결과는 기존 합성 fixture에 한정된다. 일반적 경계 안전성, 실제 OCR 단어 승인, PPT 편집 시간 및 미관측 이미지 성능은 검증하지 않았다.
