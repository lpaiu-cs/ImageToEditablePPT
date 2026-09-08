# R10-O 및 O+C 실제 RGB→PPT 중간 결과

중복 글자 문제는 이 개발 집합에서 해결했다. 연결 누락은 아직 해결되지 않았으므로 이 기록은 종료 보고서가 아니라 다음 수정의 비교 기준이다.

## 분리된 실제 결과

| arm | node TP/FP/FN | native 관계 TP/FP/FN | label 정답/오답/공백 |
|---|---|---|---|
| 고정 A-T | 91/3/0 | 26/5/41 | 82/1/8 |
| O 단독 | 91/0/0 | 27/2/40 | 82/1/8 |
| O+C-v2 | 91/0/0 | 33/2/34 | 82/1/8 |

15개 모두 별도 subprocess에서 원본 RGB의 OCR을 새로 실행했다. 정답 없이 기존 bbox 중 유일한 완전 지지 후보만 남겼다. tree00036 CP는 det5, tree00149 Adj는 det1, PP는 det11을 유지했고 중복 det7/det10/det9를 제거했다. 원래 높은 점수를 받은 잘못 잘린 PP가 제거되었으며 점수나 정답 ID는 선택 근거가 아니었다. 생존 객체의 모든 필드는 기존과 동일하다. 객체 선택 뒤 연결선을 새로 추적했다.

원본 source trace는 36TP/15FP/31FN이며 O와 O+C에서 동일하다. native에서만 비교하면 일부 잘못된 trace가 writer에서 제외되는 효과가 섞이므로 이를 구별한다. 남은 native2FP와34FN, label오답1/공백8은 해결되지 않았다. container11TP/0FP/0FN은 불변이다. graph 도형 kind에는 legacy 정답 bbox/실제 ellipse 계약 문제가 있어 exact-kind 집계를 외형 정확성으로 해석하지 않는다.

## 육안 확인

각 arm의 contact0~2를 전부 열어 15개를 관찰하고, O의012/014 및 O+C의013을 확대 확인했다. CP/Adj/PP 이중 인쇄는 없어졌다. O+C의 무방향 트리는7개 native 연결이 보이고, C-v2가 추가한 대각선6개가 원본 관계를 복원한다. 반면 directed tree00036은 여전히 글자 일부만 있고 연결선이 전혀 없으며, tree00149도 가지가 많이 비어 있다. block_flow의 대각선·graph의 관계 누락, 글자 공백, 연한 테두리도 남아 있다. 전체적으로 만족스럽다는 판정은 하지 않는다.

실제 PowerPoint COM으로15개씩 렌더했다. native 객체/endpoint binding과 raster absence는 별도 evaluator가 검사했다. 사람의 drag 편집과 수정시간 감소는 측정하지 않았다. 입력은 이미 본 합성 validation/dev 집합이다. 실제 논문/미관측 holdout 일반화 승인과 동일하지 않다.

## 근거 고정

`benchmarks/r10_spatial_ocr_results.json`에 각 실행 lock/results/evaluation SHA를 보존한다. 최초 코드·runner 잠금은 `fcbae87`. 이후 runner 확장은 Git으로 분리되어 있고, 이 두 arm의 출력은 다시 쓰지 않는다. Python audit hook 구간 정답 파일 접근은 없지만 OS sandbox라고 주장하지 않는다.

O 기본메커니즘18개 및 실제OCR RGB8개 대조를 통과했다. D-v3 공통41개도 통합 후 재검증했고672개 결과 파일SHA 및 개별PASS를 확인했다. D-v3는 PP identity 해결이 아니라 안전 veto이며 불필요한 추가기권96개가 있기에 O에 무조건 적용하지 않았다.

다음 수정은 `r10_source_rays_spec.md`의 원본 직선/화살촉 관측이다. 기존 morphology가 가지를 합치고, 가장자리 최단경로가 직선을 굽은 경로로 바꾸며, 팽창된 폭이 화살촉 대비를 약하게 하는 문제를 다룬다. writer 4px gate를 넓혀 성공을 만들지 않는다.
