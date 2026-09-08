# Dark-boundary 독립 96 RGB 감사

기존 fixture를 변경 없이 `propose(rgb,dark_boundaries=True)`로 실행했다. `inner_boundaries=False`이며 Canny 경로와 혼합하지 않았다. 기본 P1/inner 기존 결과는 덮어쓰지 않았다.

- source snapshot SHA: `d468789cf1345ed4aa838e185fb33d2c41d787eb5cf30acd1d81491b106638e8`
- fixture lock SHA: `150d9471e53e58177cbb4dc2124cd95aa5b90c6384085abe7052a75381211124`
- runner SHA: `276b63c903404996049ac9a7edd9d12124a61293431f1a6e2b543e6f8dfbfb86`
- artifacts: `artifacts/r10-p-independent-dark-v1-results`

총 64 pass / 8 formal fail / 24 diagnostic이다. 모든 입력 SHA와 RGB 불변성을 확인했다.

| 종류 | 8개 RGB의 결과 |
|---|---|
| rectangle / colored_rectangle | 각각 전부 1개 선택 |
| adjacent | 전부 2개 선택 |
| open / ellipse / diamond / shadow | 각각 전부 abstain |
| nested_white / nested_blue | 각각 width1 네 개 abstain, width3 네 개 inner 하나 선택 |
| photo_frame | 전부 1개 선택 |
| glyph_hole | 전부 1개 선택 |
| table | 전부 6cell 선택 |

기존 양성 rectangle/colored/adjacent의 누락은 이 suite에서 사라졌다. 열린 테두리, ellipse, diamond, shadow에서 false closure는 관측되지 않았다. 이는 해당 32 negative entry에 한정되며 새 실이미지 phantom 부재를 증명하지 않는다.

formal8fail은 모두 중첩 fixture의 `not_single` 계약이다. 선택 bbox는 scale1에서 `[83,83,198,138]` 또는 `[83,83,197,137]`, scale2에서 `[167,167,394,274]` 또는 `[167,167,393,273]`다. 실제 안쪽 hole에 대응하므로 이를 새 구조 생성이나 오합병으로 부르지 않는다. 특히 width3에서는 외부 stroke와 안쪽 stroke가 붙을 수 있어, 생성 객체 둘이라는 사실만으로 두 개의 분리된 최종 래스터 경계를 보장하지 않는다. 기존 formal verdict는 사후 PASS로 바꾸지 않는다.

사진 frame과 glyph hole도 실제 폐윤곽이므로 dark 경로에서 선택된다. 이것이 diagram 의미 적격성을 검증한 결과는 아니다. 표 cell은 실제 구조일 수 있으므로 자동 FP 판정을 하지 않는다. 현재 채택하지 않는 content gate를 적용해 수치를 개선하지 않았다.

root runtime은 수정하지 않았다. 감사 runner에 `--dark-boundaries` 선택 인자만 추가했다. OCR, native PPT, 실제 reasoning-full 출력의 육안 평가는 이 실행 범위 밖이다.
