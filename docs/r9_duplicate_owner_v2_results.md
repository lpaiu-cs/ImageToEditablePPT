# D-v2 G0–G2 실패 동결: fixture 위반과 실제 support 관측의 분리

## 판정

**D-v2의 고정 G2는 FAIL이며 실제 15개에 진입하지 않는다.** 4,328 records 중 4,192건 통과, 136건 기대값 위반이다. scope violation은 0이다. **136건을 실제 문자/관계 손실 136건이라고 해석하면 안 된다.** 기대값이 렌더링 뒤 실제 support를 확인하지 않고 base에서 복사됐기 때문이다. 아래 별도 RGB 감사는 원 실패를 설명하며 gate/기대값을 소급 변경하지 않는다.

관측 구현·builder·runner·G0 test·fixture lock은 첫 기하 실행 전에 `0279bdcb466276250893c65a80b802186900917a`에 고정했다. 최초 geometry 결과 이후 이 코드, threshold, fixture, expectation은 수정하지 않았다. 제품 runtime/postprocess/enum, 학습, COM, C 결합, 실제 15개 D-O/D-S는 실행하지 않았다.

## 잠금과 입력 경계

- v1 원본 replay **3,656건** + v2 신규 **672건** = **4,328건**.
- 신규 30 base: 일반 27개×scale3×추가AA2×order2×score2=648, crop3개×scale1×AA2×order2×score2=24.
- observer SHA `181f54ddd11b1f71b145797e94342fa6f459432424b9923dcd9996d1b325aa95`.
- v1 helper SHA `90eb83235e988cecc371794f701fd591dc8fe189193d23e2f70ad1ce50a34846`.
- fixture lock SHA `a06141bd8e39a42e9d72e2208ca16fd384e8464ac36dec3fe52cd9b80f078dcc`.
- expectation SHA `1d18b0053ca881d61f20ffccec0522f3fb4fcd0664eb4c63266158adbd7f2657`.
- font는 고정 Arial SHA, seed901/no additional noise. 세부 사항은 `benchmarks/r9_d_v2_fixture_lock.json`.

초기 생성본은 관측 실행 전에 crop/AA metadata를 검토하면서 보완했다. 전체 frame에 AA를 적용한 후 그 pixel subset으로 crop을 만들도록 고쳤고, final 디렉터리에 다시 잠갔다. 기대값은 동일하며 구 생성본도 보존했다. 이것은 결과 후 fixture 변경이 아니다.

전체 실행에서 crop은 원본 frame SHA와 실제 pixel subset을 검증했다. observer는 RGB/예측 owner/검증된 좌표 context만 받고 Python audit-hook 내 파일 open 시도는 0이었다. 원 annotation/PPT나 OCR 문자열은 observer에 전달하지 않았다. Python hook은 OS/native IO sandbox라는 의미가 아니다.

입력 whitelist/invalid owner/context/no-op 테스트 **11 passed**. 신규 168개 geometry에 대해 ID를 opaque 문자열로 바꿔 추가 검증한 결과 **168/168 결정 동일**. 원래 runner의 score/order invariance, V2-O 불변, V2-O/V2-S 관측 동일, survivor 불변, 충분한 crop/full 동일 관측 위반은 0건이었다.

## 모집단별 성적과 지원 범위 축소

| 모집단 | records | 고정 기대값 위반 |
|---|---:|---:|
| 원 v1 replay | 3,656 | 0 |
| 신규 v2 | 672 | 136 |

원 v1의 376건 실패 기록은 그대로 남는다. v2 replay 결과가 이를 소급 취소하지 않는다. v1의 회전/세로 280건은 당시 scope violation이며 실제 내용 손실로 합산하지 않는다.

**기존 positive 288건은 선택 성공 0, 기권 288건**이다. 원 clean bitmap 기본 4개 order/score 변형도 방향 관측 불충분으로 기권한다. 기존 능력의 축소를 새 positive 성적으로 숨기지 않는다. 신규 clean 기본은 가로 multi-atom과 먼 약한 speck가 있는 **두 장면**이며 order/score 변형을 포함한 8 records 모두 기대한 tight bbox를 선택했다. 따라서 새 지원 범위에서 all-abstain은 아니지만 기존 positive 성능이 유지된 것도 아니다.

## 원 실패 136건의 구성

| base | records 위반 | geometry group |
|---|---:|---:|
| bright12_separate | 24 | 6 |
| bright12/24/32/64_touch | 96 | 24 |
| speck_near | 8 | 2 |
| punct1 | 4 | 1 |
| bbox_shift_loss | 4 | 1 |
| 합계 | **136** | **34** |

이 수치는 runner가 `preserve` 기대값 위반을 `fixture_support_or_owner_loss`로 표시한 결과다. runner는 그 이름만으로 실제 raster 획 손실이나 문자 의미 손실을 입증하지 않는다. `semantic_character_loss=not_inferred_from_RGB`도 함께 기록돼 있다. 다음 감사가 실제 입력 pixel과 후보 bbox를 따로 확인했다.

## RGB 감사: 생성 의도와 실제 입력의 차이

같은 scale/AA의 `row_clean`과 실패 RGB를 pixel 단위로 대조했다. bbox 포함은 원본 pixel-center 규칙을 유지했다. 결과는 `raster-delta-audit.json`; 단순 bbox 안팎의 모든 nonwhite pixel을 세는 초기 감사는 `rgb-support-audit.json`에 별도 보존했다. latter에는 원래 glyph의 AA halo도 포함되므로 추가 정보 손실 근거로 단독 사용하지 않는다.

1. **점이 입력 생성 때 이미 사라진 12건(3 geometry groups).** `speck_near`, `punct1`, `bbox_shift_loss`의 .75 scale/no-extra-AA 각각 4변형은 RGB가 row_clean과 완전히 같다. 보이지 않는 점의 생성 의도를 observer가 복원하지 못했다고 실제 내용 손실로 세면 안 된다. 원 gate 위반은 보존한다.
2. **touch 96건(24 groups).** 추가 획의 x=340은 tight bbox xmax=342 내부다. 선택된 tight bbox도 주 획 위치를 포함한다. AA/scale의 16건에서는 tight 밖에 최대 contrast 차이 1–5의 희미한 경계 신호가 있다. resampling halo 후보이지만 이를 주 획/문자 손실 또는 무의미한 noise로 단정하지 않는다. 나머지 80건은 추가 dark signal 자체가 tight 밖에 없다. preserve 기대값이 실제 손실 필요조건을 확인하지 않았다.
3. **bright12_separate 24건(6 groups).** 추가 획이 tight 밖에 실제로 남는다. extra-AA off 12건은 exact RGB 대비 contrast 12지만 luminance 연산의 cutoff 경계에서 누락된다. extra-AA on 12건은 rasterization 후 최대 contrast가 10으로 줄어 weak cutoff12 밖이다. 두 원인을 분리한다.
4. **speck_near 추가AA 4건(1 group).** 점의 희미한 pixel이 실제로 남지만 cutoff 아래다. 큰 의미가 있는 punctuation인지 noise인지 RGB만으로 보증하지 않는다. `punctuation_or_noise_unresolved`를 출력하지 않고 선택했다는 관측 한계다.

확인된 정밀 집계는 **136 = clean RGB와 동일 12 + 추가 dark pixel 전부 survivor 내부 80 + 일부 추가 dark pixel이 밖에 있음 44**다. 마지막 44건은 최대 contrast<12인 32건과 contrast≥12인 12건으로 나뉜다. 32건 중 16건은 위 touch의 희미한 경계 신호이고, 나머지 16건은 bright12 AA/near speck다. 밖에 있다는 pixel 관측만으로 실제 의미 손실을 확정하지 않는다. 예비 96/28 또는 108/28 semantic 분류는 사용하지 않으며, 원 FAIL 136도 사후 PASS로 바꾸지 않는다.

## 숫자 경계 결함

실제 crop 배열의 `pixels @ weights` 연산에서 white RGB255의 배경 Y가 `254.99999999999997`, gray243의 Y가 243.0으로 계산되어 subtraction은 `11.999999999999972`다. 따라서 strict `contrast >= 12`에 들어오지 않는다. **단일 1D dot에서는 12.0이 나올 수 있으므로 같은 crop 배열 연산으로 재현해야 한다.** 이는 contrast가 실제 10으로 줄어든 AA 사례와 다르며 **수치 비교 경계 결함**이다. 1px 위치 오차 자체와도 다르다. cutoff에 epsilon을 추가하거나 정수식으로 바꾸는 수정은 이번 frozen 실행 뒤 수행하지 않았다.

해결 방향을 검토하더라도 exact RGB contrast 정의, luminance rounding, 허용 경계의 계산 방식을 새 계약에서 고정해야 한다. 모든 밝은 pixel을 의미 있는 문자로 간주하거나 threshold를 무조건 낮추는 방식으로 일반화할 수 없다.

## 코드–명세 감사 한계

- `eligible=not veto`여서 v1의 별도 nonnegative-padding 조건은 직접 적용되지 않는다. v2의 pixel-cell 경계량 차이를 허용하는 문구와 기존 대표 선택 조건의 관계가 구현에 명시적으로 분리되지 않았다. 전체 audit에서 negative-padding candidate는 2,512개, eligible 40개, 실제 winner는 **0개**였다. 관측된 성공은 이 공백이 안전하다는 증거가 아니다. 명세 준수 완결로 주장하지 않는다.
- 명세의 shaft–glyph 접촉 기권에 대응하는 **명시적 인접 pixel veto가 없다**. weak component의 긴 성분 판정과 core/weak shaft-class 불일치 검사는 있지만, 이들이 모든 접촉을 대신 검증한다는 보장은 없다. 이 구현 누락은 G2의 현재 controls가 통과한 접촉 사례와 별개로 남는다. 제품 후보로 승격하지 않는다.
- 개별 glyph가 회전하더라도 중심의 가로 행이 확인되고 support를 잃지 않으면 v2 scope violation으로 세지 않는다. 이는 개별 glyph 자세를 검증했다는 뜻이 아니다. TLS 각도 δ는 여전히 미보장 heuristic이다.
- old positive의 전면 기권, fixture raster 이후 expectation 검증 부재, 밝기 경계 및 tiny 의미 불확실성은 독립 한계다. 유리한 일부만 모아 “v2가 통과했다”고 보고하지 않는다.

## 산출물과 재현

`benchmarks/r9_d_v2_controls.json`은 고정 gate 결과·실패 ID·모집단 분리·전체 artifact SHA와 post-result 감사 요약을 담는다. 전체 자료는 `artifacts/r9-d-v2-controls`의 `results.json`, `audits`, `masks`, `raster-delta-audit.json`, `negative-padding-audit.json`, `id-invariance.json`에 있다. root의 독립 RGB 감사와 이 작업의 감사는 별도로 수행했으며 상호 일치하는 원인과 pixel-level 한계를 구분해 기록했다.

```powershell
rtk proxy C:/vs/ImageToEditablePPT/.venv/Scripts/python.exe -c 'import sys,runpy;sys.path.insert(0,"src");sys.path.insert(0,"tools");sys.argv=["run_r9_d_v2_controls.py","--fixtures","artifacts/r9-d-v2-fixtures-final","--out","artifacts/r9-d-v2-controls-reproduction"];runpy.run_path("tools/run_r9_d_v2_controls.py",run_name="__main__")'
rtk proxy C:/vs/ImageToEditablePPT/.venv/Scripts/python.exe -m pytest tests/test_duplicate_owner_v2.py -q
```

runner의 exit1과 원 기대값은 유지한다. 원 데이터/코드를 덮어쓰지 않는다. 다음 구현 수정이나 실제 15개·C 결합은 이번 작업 범위에 포함하지 않는다.
