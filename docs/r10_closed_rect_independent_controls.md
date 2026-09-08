# P 독립 RGB geometry 대조군

## 실행 경계

`tools/r10_closed_rect_independent_controls.py`는 Pillow로 96 RGB를 먼저 저장하고 manifest/생성기 SHA를 잠근 뒤, root의 `closed_rect_proposals.py`를 복사한 snapshot의 `propose(rgb)`만 실행했다. OCR, detector, GT, holdout, PowerPoint 실행은 포함하지 않는다. 모든 입력 SHA와 RGB 불변성을 확인했다. root 연구 코드는 수정하지 않았다.

- source snapshot: `d045ed4ebc1657e69a53826c7a04250549c83471811b6a38096005be2c20bc55`
- fixture manifest: `8a4a6a95562c235102365ee43c42505b7f635e9243271d9474c434d2136b1482`
- fixture lock: `150d9471e53e58177cbb4dc2124cd95aa5b90c6384085abe7052a75381211124`
- builder/runner: `beb58e583a284ee5320dd80839c6dc0bf197e37a64ae16e2c30317e1676b09be`
- artifacts: `artifacts/r10-p-independent-v1-fixtures`, `artifacts/r10-p-independent-v1-results/results.json`

12 종류 × 배율 1/2 × AA 1/4 × 선 두께 1/3이다. 주 사각형은 캔버스의 7.5%이며 25% 면적 상한 안에 있다. 실행 당시 formal 기대값은 유지한다: 72개 중 56 pass, 16 fail; 나머지 24개는 semantic diagnostic이며 pass/fail을 부여하지 않았다.

## 결과와 해석

| 종류 | 8 RGB의 선택 개수 분포 | 해석 |
|---|---|---|
| rectangle | 1개×3, 0개×5 | 정상 사각형 누락 |
| colored_rectangle | 1개×3, 0개×5 | 정상 유색 사각형 누락 |
| adjacent | 2개×3, 0개×5 | 두 사각형 모두 누락하는 5개 |
| open / ellipse / diamond / shadow | 각각 0개×8 | 이 대조군에서 잘못된 사각형 승인 없음 |
| nested_white | 2개×5, 0개×2, 1개×1 | 아래 해석 참조 |
| nested_blue | 2개×6, 0개×2 | 단일 경계로 축소 없음 |
| glyph_hole | 2개×8 | 의미 분류 없이 검출되는 사각형 경계 |
| photo_frame | 1개×3, 0개×5 | 사진을 둘러싼 프레임도 후보가 됨 |
| table | 6개×7, 2개×1 | 실제 닫힌 cell; 자동 오검출 판정하지 않음 |

일반 양성의 15 fail은 모두 abstention이다. 각 종류에서 두께 3의 네 조합은 near-boundary ambiguity로 탈락하고, scale2/AA1/width1은 후보 자체가 없다. 이 결과는 유용한 복원량의 한계이며 잘못된 구조 생성 증거는 아니다.

`nested_white-s1-aa1-w1.png`는 원본 RGB를 직접 확인했다. 실제 외부/내부 사각형은 분리되어 있다. 선택된 bbox `[84,84,197,137]`는 내부 사각형에 대응하며, 후보 audit에는 이것 하나만 존재한다. 따라서 frozen `not_single` 기대값에는 실패하지만 **서로 다른 경계의 오합병은 입증되지 않았다**. 내부 구조만 복원하고 외부를 누락한 부분 복원이다. 사후에 raw verdict를 PASS로 바꾸지 않는다.

사진 프레임/글자 구멍/표는 생성 전부터 diagnostic으로 고정했다. photo_frame은 seeded RGB texture를 검은 테두리 안에 배치한 이미지다. 선택된 프레임의 폐사각형 기하가 참이어도, 그것을 구조적 다이어그램 노드로 승인하는 의미 판단은 별도이다. glyph_hole 역시 검은 블록의 사각 구멍이며 기하만으로 글자/노드를 구별할 수 없다. 표 cell은 실제 구조가 될 수 있으므로 단순 검출을 오류라고 하지 않는다. 이러한 관찰은 semantic 범위의 한계이지 본 fixture에서 검출한 모든 사각형이 잘못되었다는 뜻이 아니다.

이 실행은 synthetic geometry 대조군에 한정된다. OCR의 줄 완전성, 실제 여섯 개발 이미지의 유용성, 원본 입력의 최종 PPT 편집 시간, 사진/글자 의미 판별, 미관측 이미지 성능을 검증하지 않았다. 숫자를 production 승인율로 해석하지 않는다.
