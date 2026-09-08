# D-v3 revision 1: 공통 결함 수정 검증과 실제 PP 해결 연결

## 완료된 검증

정수 밝기·접촉·support 경계 공통 함수 **41 tests passed**. 최종 raster에서 재구성한 안전성 대조 **672/672 passed**. 과거 D-v1/v2 원 기록은 변경하지 않았다. 이번 PASS는 **공통 안전 메커니즘과 frozen V2 제안에 대한 veto 검증**이며, 새로운 PP/CP identity 검출이나 실제 15개 개선 성적이 아니다.

최초 실행 전 코드/기대값은 `3513f067a3c9b5e7ef852a5b93b7b01b8aebbaa5`에 잠갔다. 명세는 `r9_d_v3_revision_contract.md`. observer SHA `1cd7dbe834394d386e2393ddcb65fd2e7cbb3a566b823da848a8a887db00c68f`, expectation SHA `fd89e0aceb245606c7b0ecc4f5a85cab4afa0021dc03db33c36cf538f8526291`, lock SHA `644d39ca8e02aa20e29882423343f6efe268f131fa65912f211bc6ab1bf27ff5`.

## 고친 경계

1. `integer_contrast`: RGB weighted luminance를 int64로 계산하고 background median도 2배 단위로 정확히 유지한다. gray243/white255의 contrast12가 scalar·crop·Fortran·stride 배열에서 동일하게 weak12에 포함된다. ε/threshold tuning을 사용하지 않았다. 색 극값과 짝수 median도 검증했다.
2. `shaft_glyph_contact_guard`: 원 mask의 8-neighbour 접촉, overlap, 동일 connected component가 owner 내외에 걸치는 불확실성을 명시적으로 반환한다. 선을 제거한 뒤 glyph가 없다고 판단하는 실수를 막는 데 사용할 수 있다. owner 경계를 지나는 선이 곧 글자라는 주장은 아니며 보수적 uncertainty다.
3. `candidate_support_check`: eligibility를 하나의 함수로 계산한다. negative cell padding 자체는 실패가 아니다. pixel center가 모두 보존된 -.25px padding 예는 통과한다. 전체 tiny/orphan 소실은 veto, 같은 core-containing component의 경계 fringe는 기존 coverage와 1px band 조건으로 평가한다. 음수 padding을 별도 숨은 gate로 적용하지 않는다.
4. `background_speck_mask`: 멀고 낮은 contrast의 작은 background speck에 한정한 예외다. 행 가까운 같은 점은 미확정으로 보호한다. 모든 1px을 의미정보라고 강제하지 않는다.

이 함수들은 `research/duplicate_owner_v3.py` 한 곳에 있으며 OCR·GT·파일 IO나 owner identity 결정은 하지 않는다. 향후 수정은 이 모듈의 Git revision으로 추적하고 복제한 v3a/v3b를 늘리지 않는다.

## fixture/evaluator 수정

v2의 신규 672개 입력 RGB/owner는 그대로 사용한다. observer 실행 전에 reference raster와 perturbation raster의 exact luminance delta를 계산해 기대값을 새 버전으로 고정했다. body는 added signal 상대 반치폭으로 정의했으며 observer weak12와 독립이다. 의미 문자를 보증하는 ground truth는 아니다.

| raster-valid 분류 | records |
|---|---:|
| 기존 structure/scope 계약 유지 | 336 |
| 최종 raster로 검증한 먼 speck | 24 |
| rasterization에서 추가 정보 소실 | 12 |
| 일부 후보 선택 시 feature body 손실 가능 | 204 |
| 모든 후보가 feature body 보존 | 96 |

body를 잃지 않는 기존 bbox 선택 또는 둘 다 유지하는 선택을 허용한다. 생성 의도만으로 `preserve`를 강제하지 않는다. 원 v2의 136건 실패를 수정해 지운 것이 아니라, 새 evaluator에서 별도로 평가했다. 실제 body 소실과 낮은 halo 차이를 분리했다.

## 안전성과 기권 비용

frozen V2 선택 중 새 raster-valid 계약을 위반하는 제안은 **28건**이었다. V3 veto 적용 후 위반은 **0건**이다. 그러나 전체 veto는 **124건**이며, 나머지 **96건은 새 계약상 안전했던 제안도 기권**시킨 것이다. 672개 중 단일 owner를 남긴 경우는 248→124건으로 줄었다.

추가 기권은 row_clean/font 36건, touch 48건, speck_far 4건, crop/full 8건이다. 예를 들어 `.75 scale + AA`의 row_clean은 주 glyph core/weak를 모두 보존하지만 bbox 경계 밖의 미약하고 분리된 residual 성분 때문에 `whole_component_loss`로 기권한다. 관측만으로 이를 punctuation과 구별하지 못한 비용이다. 이 96건을 실제 오류를 고친 96건이라고 보고하지 않는다.

clean 기본 두 장면의 order/score 8건은 **8/8 선택 유지**했으므로 all-abstain은 아니다. 그래도 실제 짧은 PP의 두 glyph를 선택하는 능력이 생긴 것은 아니다. 해당 지원 범위는 루트 R10-O의 image-derived OCR polygon/원본 획 분석과 별도 연결한다. 기존 positive 288건의 D-v2 기권 결과도 유지된다.

## R10 연결용 API와 주의

- `integer_contrast(rgb, ring)` → integer masks와 exact contrast. 원본 ROI 좌표/배경 provenance를 유지한다.
- `candidate_support_check(core, weak, residual, bbox, origin=...)` → 후보별 eligibility, core/weak coverage, whole/partial loss, boundary 차이. masks는 **같은 원본 RGB에서 관측된 대상 영역**이어야 한다. 전체 slide의 다른 글자까지 넣으면 해당 bbox가 다른 객체를 잃었다고 잘못 비교할 수 있다.
- `shaft_glyph_contact_guard(shaft, glyph, original_ink=..., owner_mask=...)` → 명시적 contact/uncertainty. OCR polygon 면 전체를 glyph ink로 넘기지 않고 polygon∩원본 ink 같은 공간 근거를 사용해야 한다. 이 guard의 safe는 identity 정답 보장이 아니다.

R10-O가 새로운 spatial OCR 근거로 PP의 대표 후보를 결정할 때 이 공통 보호 함수를 사용할 수 있다. OCR polygon 밖의 tiny 정보를 무조건 버리는 근거로 사용하면 안 된다. residual 추가 기권을 해소하려면 원본 획과 공간 관측 근거를 검토해야 하며, 숫자를 낮추거나 noise라고 일괄 명명해 없애지 않는다. 실제 15개/C 결합/COM 실행은 루트가 조정한다.

## 산출물

`benchmarks/r9_d_v3_revision1_lock.json`, `benchmarks/r9_d_v3_revision1_results.json`에 SHA와 집계가 있다. 전체 관측은 `artifacts/r9-d-v3-revision1-results`의 `results.json`과 `audits`, 새 기대값과 feature-body mask는 `artifacts/r9-d-v3-controls-lock`에 있다. Python observer 구간 file-open denial 0. 원 데이터와 v1/v2는 변경하지 않았다.

```powershell
rtk proxy C:/vs/ImageToEditablePPT/.venv/Scripts/python.exe -m pytest tests/test_duplicate_owner_v3_mechanisms.py -q
rtk proxy C:/vs/ImageToEditablePPT/.venv/Scripts/python.exe -c 'import sys,runpy;sys.path.insert(0,"src");sys.path.insert(0,"tools");sys.argv=["r9_d_v3_raster_controls.py","run","--fixtures","artifacts/r9-d-v3-controls-lock","--out","artifacts/r9-d-v3-reproduction"];runpy.run_path("tools/r9_d_v3_raster_controls.py",run_name="__main__")'
```

checkpoint를 실제 문제 해결 완료로 오해하지 않는다. 현재 완료는 공통 계산/보호 결함 수정과 controls 검증이며, 루트의 PP identity/대표 bbox 및 실제 native 대조와 연결해 남은 문제를 해결한다.
