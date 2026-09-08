# D-v2 독립 래스터 감사: 136건을 문자 손실로 해석하지 않는다

## 범위와 결론

worker의 첫 D-v2 결과는 4,328건 중 4,192 pass / 136 fixture gate 위반이었다.
이 작업은 observer를 다시 실행하거나 expectation을 변경하지 않고, 고정 원본 RGB와
동일 scale/AA의 clean fixture를 직접 비교했다. 원 G2 결과를 통과로 바꾸는 감사가 아니다.

**136건 모두를 실제 문자·객체 손실이라고 부르는 것은 부정확하다.**
이 값은 생성기에서 설정한 preserve 기대값 위반 수다. 다음 구분이 필요하다.

| 원 실패 records의 분류 | 건수 | 직접 확인한 의미 |
|---|---:|---|
| clean과 RGB 완전 동일 | 12 | 추가 점은 rasterization에서 소실됨. 모델의 점 삭제 아님 |
| 추가 dark pixel이 tight bbox 내부에 모두 남음 | 80 | 해당 추가 획을 잃었다는 기대 전제 불성립 |
| touch 획의 낮은 contrast 경계 번짐 일부만 밖에 남음 | 16 | .75/AA1, contrast 최대1/2/2/5. 핵심 획 손실 증거 아님 |
| bright12 별도 획 | 24 | 원본에 추가 픽셀은 있으나 mask가 못 봄. 아래 원인 분리 |
| 가까운 speck의 희미한 AA 잔여 | 4 | 원본 contrast 최대8. weak12 밖. 문자/잡음 의미 미확정 |

이들은 34개 geometry group의 order/score 4변형이다. 독립 실패 이미지136개가 아니다.
위 분류는 픽셀 보존 감사이며 사용자 가독성·문자 인식·PPT 사용성 측정이 아니다.
특히 '추가 dark pixel이 밖에 있음'도 곧바로 사람에게 의미 있는 문자 손실은 아니다.

초기 일부 사례만 보고 touch96건 모두 획 보존일 수 있다고 worker에 전달했으나,
전체 조합 감사 후80건 완전 보존과16건 AA 경계 번짐으로 정정했다. 최종 표에는 전수
집계만 사용한다. 알고리즘·기대값·고정 결과는 이 과정에서 수정하지 않았다.

## 정확히12인 밝기 경계 결함

`v2-bright12_separate-s1.0-aa0`의 원본 흰색은 RGB255, 별도 획은 RGB243이다.
실제 observer crop `(228,85,415,246)` 배열에서 luminance를 계산하면 다음과 같다.

- 배경 median: `254.99999999999997`
- 획 luminance: `243.0`
- 계산된 차이: `11.999999999999972`
- `contrast >= 12`: False

따라서 명세상 포함해야 할 경계값이 floating 연산에서 탈락한다. 단일 1D dot에서는
12.0이 나왔으므로 재현은 실제 crop 배열 경계에서 해야 한다. 이는 1px 위치 오차나
일반적인 모델 한계가 아니라 수치 비교 구현의 결함이다. 원 observer는 수정하지 않았다.

bright12 AA-off 3scale × order/score4 =12건은 이 경계 문제에 해당한다.
AA-on12건은 추가 획의 실제 최대 contrast가10으로 낮아졌다. 후자는 반올림 경계가
아니라 관측 cutoff 밖의 지원 영역 문제이며 생성기 설정값12와 실제 입력10을 혼동하면 안 된다.

## 기대값과 구현 계약의 남은 경계

생성기는 base의 preserve 기대값을 scale/AA 뒤에도 그대로 운반한다. 실제 래스터에서
추가 정보가 남는지, 어느 bbox가 그것을 보존하는지 별도 검증하지 않았다. 다음 수정은
예측 결과에 맞춰 기대값을 바꾸는 방식이 아니라, 관측 호출 전에 최종 RGB/정답 component
지원과 bbox 보존 관계를 검증하는 fixture 생성 계약이어야 한다.

source code에서 candidate eligibility는 veto 여부만 보며 padding 음수 여부를 명시적으로
차단하지 않는다. 행 grouping과 shaft-glyph contact도 명세에 비해 구현 확인이 더 필요하다.
이 점들은 현재136건의 측정 원인으로 단정하지 않고 별도 계약 점검 항목으로 남긴다.

## 기존 보호와 실제 유용성

이전 v1 replay3,656건의 원 preserve/selection 조건 위반은0건이었다. 그러나 기존
positive288건의 선택은0, 기권288건이다. 새 clean2개 기본 장면의 order/score8개는
모두 선택했다. 범위 축소로 얻은 안전성과 이전 선택 능력 손실을 분리해야 한다.

고정 PP full control4개는 `orientation_unobservable`, `possible_information_loss`,
`shaft_glyph_uncertain`로 둘 다 유지한다. crop4개는 `crop_too_large`로 유지한다.
따라서 실제 중복 PP를 해결했다는 증거가 없다. G2 실패와 fixture/계약 문제 때문에
실제15장 D-S, C+D 결합, 제품 승격에 진입하지 않았다.

## 증거

감사기: `tools/audit_d_v2_raster_support.py` — observer import/호출 없음.
감사 산출물: `artifacts/region-source-evidence-r9/d-v2-raster-audit/audit.json`.
SHA256: `67be8925bbb651fd4c475a5ea80562768a1bfa77377b3db2a573cdf8616ff815`.
worker 원 G2 results SHA256: `c1bcb51f39eb79f5459e4bed7ed5fd428e4d132f7bb1996f73e241dc70bc38a4`.
고정 observer commit `0279bdc`를 root `57911fd`로 통합했고 입력경계11개를 재검증했다.
평가분리17개+C-v2 43개와 합쳐71 passed. 이 숫자가 G2의136건 위반을 대체하지 않는다.

clean, bright12, 소실된 punctuation의 원본 RGB도 직접 열어 확인했다. 밝은 획은
가시성이 낮았으며 의미 글자 손실을 육안으로 확정하지 않았다. 새 실제 PPT는 만들지 않았다.
