# R9-D v1 G0–G2 결과: 반례 gate 실패, 실제 15개 미진입

## 판정

**R9-D v1 suppression 후보는 실패로 동결한다.** 입력 경계 unit test 12개는 통과했지만 고정 fixture 3,656건 중 376건에서 보존해야 할 owner를 제거했다. 최초 명세의 숫자, 관측 규칙, fixture 기대값을 결과 후 수정하지 않았다. 실제 15개 D-O/D-S, 새 학습, 제품 runtime/enum/postprocess 변경, COM은 수행하지 않았다.

관측 모듈은 `src/image_to_editable_ppt/research/duplicate_owner_observations.py`, builder는 `tools/r9_duplicate_owner_fixtures.py`, 실행기는 `tools/run_r9_duplicate_owner_controls.py`다. 최종 관측 코드 SHA256은 `90eb83235e988cecc371794f701fd591dc8fe189193d23e2f70ad1ce50a34846`이다.

## 실행 전 잠금과 실행 환경 실패의 분리

1. 최초 코드/fixture 잠금은 `79b78e3`에 커밋했다. 모든 관측 실행 전에 manifest/expectation/font/observer/spec SHA를 저장하고 원 작업에 3,656개 목록의 개수를 전달했다.
2. 최초 실행은 관측 모듈의 닫는 괄호 누락으로 collection 단계에서 실패했다. 별도로 직접 script 실행이 외부 venv의 원 checkout package를 참조해 import에 실패했다. 이때 fixture 판정 결과는 없었다. 괄호 한 개만 수정한 `3d0e4dc`와 명시적인 worktree `sys.path`로 실행 경계를 고쳤다. **수치·계산식·기대값 수정은 없다.** 원 code/lock은 보존했다.
3. build2 fixture는 같은 builder로 재생성했다. 3,656개 각각의 RGB SHA와 owner JSON SHA, 전체 expectation bytes가 최초 잠금과 동일함을 검증했다. 경로와 관측 build SHA만 다르다. `benchmarks/r9_d_v1_fixture_lock.json` 및 `r9_d_v1_fixture_build2_lock.json`을 모두 보존한다.
4. build2 첫 전체 실행은 엄격한 no-file-open guard가 NumPy의 지연 `numpy.ma` import를 막았다. 2,792건 PermissionError와 864건 조기 no-op 결과를 `artifacts/r9-d-v1-controls-build2/results.json`에 보존했다. 이것을 2,792개의 geometry 반례 실패나 all-abstain 성적으로 해석하지 않는다.
5. `1cf442c`는 runner에서 **NumPy 런타임만 guard 전에 preload**한다. 관측 코드·fixture·기대값은 변경하지 않았다. 새 실행은 `artifacts/r9-d-v1-controls-runtime-ready`에 저장했다. 이 실행의 observer 구간 파일 open 시도는 0이다. Python audit-hook 증거이며 native library의 모든 OS 접근을 보장하는 sandbox라고 주장하지 않는다.

초기 builder 자체도 중복 keyword 오류로 생성 도중 중단된 디렉터리를 남겼다(`artifacts/r9-d-v1-fixtures`). 이는 최종 fixture 잠금 이전이며 observer 실행은 없었다. 부분 생성물을 평가 모집단에 섞지 않았다.

## 고정 모집단

- synthetic base 36개 × scale 3 × shaft shift 2 × color 2 × 추가 AA 2 × order 2 × score 2 = 3,456건.
- overlap chain은 전체 6순열이므로 추가 192건.
- 원래 PP det9/11만 사용하는 실제 RGB full/crop control 각각 order/score 4건 = 8건.
- 합계 **3,656 records / PNG 경로 866개 / 서로 다른 PNG SHA 498개**. 3,656개 독립 이미지라는 뜻이 아니다. 일부 shift는 해당 base에 선이 없어 같은 RGB를 만든다. vertical과 rotation90도 같은 bitmap 기반 중복 control이다.
- seed 901은 texture 생성에 사용했다. optional 1% random noise는 사용하지 않았다.
- Arial 14, font SHA `b3658eadae55e682b5f69eb64c439c1ecc8f196c0bb8d4756d145d13bc86476a`, Pillow 12.3.0, Python 3.12.9.
- 최종 fixture lock SHA `1787ef8177772f9f8893e3838d40080d5682e3827cc8726a702575f0e7348d25`.
- expectation SHA `71444d563110c0967d7947ec7794c9036710d8391d4062662a80769978564a69`.

builder의 AA flag는 추가 bicubic 확대→Lanczos 축소 유무다. PIL TrueType 글자의 기본 antialias까지 끈 것은 아니다. bitmap base의 AA-off는 hard pixel이고 font base의 AA-off는 추가 roundtrip만 없다는 뜻이다. 따라서 모든 글꼴의 완전 무-AA/AA 비교를 수행했다고 주장하지 않는다. texture도 실제 사진이 아닌 고정 난수 RGB control이다.

## 실제 G2 성적

| 구분 | records | 실패 |
|---|---:|---:|
| 회전 −15° | 96 | 72 |
| 회전 +15° | 96 | 64 |
| 회전 90° | 96 | 72 |
| vertical | 96 | 72 |
| 부분 문자 Il | 96 | 16 |
| punctuation | 96 | 80 |
| 나머지 | 3,080 | 0 |
| 전체 | **3,656** | **376** |

실패 376건은 order/score 변형을 접으면 94개 geometry group이다. 모두 `false_suppression`이며 input mutation, D-O/D-S proposed decision 불일치, survivor 필드 변경, order/score 의존 실패, 관측 중 파일 open 시도는 이번 실행에서 0건이다.

clean positive 기본 fixture는 4건 성공했다. 이는 동일한 원본 bitmap 기본 사례의 order/score 4변형이며 독립 clean 장면 네 개가 아니다. 따라서 all-abstain 실패는 아니지만 안전성 gate는 통과하지 못했다. unit test 12 passed가 이 G2 실패를 대체하지 않는다.

## 실패 원인 — 수정하지 않은 관측 근거

### 회전/세로: 지원 밖을 판정할 관측 조건이 없다

회전90 기본 사례에서도 두 bbox가 같은 단일 atom을 100% 포함한다. 더 작은 bbox가 padding loss에서 우세하므로 a를 남긴다. 명세는 회전/세로쓰기를 unsupported로 선언했지만, single atom의 text orientation을 검증하는 gate는 수식에 없다. 세 threshold에서 같은 결론이 나온다는 안정성만으로 가로쓰기 여부가 증명되지 않는다. 방향 판정 heuristic을 사후 추가하지 않았다.

### 부분 Il: 낮은 해상도의 희미한 stroke가 세 mask에서 모두 사라진다

`partial_il-s0.75-g0-c0-aa0-o0-swap0`은 세 mask 모두 한 개의 1×8 atom만 관측한다. whole bbox a와 partial bbox b의 signature가 같고 coverage가 모두 1이어서, padding이 작은 **partial bbox b**를 고른다. whole-minus-partial 영역 RGB의 최소 Y는 223으로, 110/140/170 어느 threshold에도 들어오지 않는다. RGB에 남은 희미한 ink를 못 본 세 mask의 합의가 전체 글자 보존으로 오인됐다. 양자화/글꼴 AA와 관측 threshold 범위의 한계이며 기대값을 삭제하거나 threshold를 높여 v1을 구제하지 않았다.

### punctuation: tiny ink를 기록하지만 대표 선택에서 실질적으로 무시한다

`punctuation-s0.75-g0-c0-aa1-o0-swap0`에서 점 1px은 M/G mask와 atom audit에 남는다. coverage는 a=0, b=1이다. 그러나 면적이 owned atom 최소 면적보다 작아 signature에 포함되지 않고 tiny 누적 면적도 기권 기준을 초과하지 않는다. 따라서 두 signature가 같다고 보고 점을 포함하지 않는 작은 bbox a를 고른다. 이는 실제로 점을 기록하는 것과 점을 잃는 선택을 막는 것이 다름을 보여준다. v1의 “punctuation을 버리며 병합하지 않는다”는 의도를 현 수치 계약이 만족시키지 못했다.

## PP와 보호 control의 해석

PP full 4건은 모두 `threshold_instability`, crop 4건은 모두 `crop_too_large`로 두 bbox를 유지했다. det11을 보호했지만 **det11을 고르는 데 성공하지 않았다**. crop은 이미지 높이 H가 달라 s=H/360과 최대 crop 크기가 바뀌므로, 원본과 동일한 픽셀을 담아도 관측 범위가 달라진다. crop/full 결과를 좌표·scale 불변성 성공으로 보고하지 않는다.

근접 독립 glyph, 반복 문자열, 부분 ROOT, 두 baseline, 선 접촉, chain, blank/배경, tie/tradeoff controls는 owner 보존 검사를 통과했다. 일부는 candidate overlap이 없어 조기 no-op이며, 모두 복잡한 identity 문제를 적극 해결한 성공이라는 뜻이 아니다. 가까운 base에는 문자열을 읽지 않는 bitmap glyph를 사용했고, 실제 반복 문자열은 별도 font base로 검사했다.

정상 fanout owner 96건은 전부 보존됐다. 추가로 고정 product tracer를 원 owner와 보존 owner에서 재실행해 **96/96 출력 동일**을 확인했다. 다만 baseline 자체가 정상 두 관계를 내는 것은 82/96이고 나머지 14건은 전후 모두 0개였다. 이는 D-S에 의한 퇴행은 아니지만 96건 모두 정상 fanout positive라는 fixture 전제는 성립하지 않는다. 실패 fixture를 삭제하거나 tracer를 수정하지 않았다. 해당 추가 결과는 `fanout-checks.json`에 별도로 보존하며 3,656 owner 판정 성적의 분모에 섞지 않는다.

## 산출물과 재현

`benchmarks/r9_d_v1_controls.json`은 gate 성적, 실패 ID 376개, 대표 audit 경로/SHA, 전체 결과 경로/SHA, 앞선 runtime 실패 provenance를 담는다. 원본과 expectation 파일은 고정 상태다. 각 record별 전체 관측은 `artifacts/r9-d-v1-controls-runtime-ready/audits`, M/S/U/G mask는 content-addressed `masks`에 있다.

worktree 코드를 확실히 선택하는 실행 예:

```powershell
rtk proxy C:/vs/ImageToEditablePPT/.venv/Scripts/python.exe -c 'import sys,runpy; sys.path.insert(0,"src"); sys.path.insert(0,"tools"); sys.argv=["run_r9_duplicate_owner_controls.py","--fixtures","artifacts/r9-d-v1-fixtures-build2","--out","artifacts/r9-d-v1-controls-reproduction"]; runpy.run_path("tools/run_r9_duplicate_owner_controls.py",run_name="__main__")'
rtk proxy C:/vs/ImageToEditablePPT/.venv/Scripts/python.exe -m pytest tests/test_duplicate_owner_observations.py -q
```

gate runner는 실패 결과 저장 후 exit 1을 반환한다. 기존 디렉터리를 덮어쓰지 않는다. 재현 시 새 출력 경로를 사용하고 fixture manifest/expectation/observer/spec SHA를 검증한다.

## 후속 범위

현재 허용되는 결론은 **명세를 구현해 반례에서 실패를 발견했다**는 것이다. 실제 복원 성적이 나빠졌다는 측정도, 실제 15개에 적용해 개선됐다는 측정도 없다. R9-C와 결합하지 않는다.

별도 v2를 검토한다면 unsupported 방향을 관측 가능하게 표현할 수 있는지, 관측 밖 밝은 ink와 작은 punctuation의 손실을 어떻게 거부할지, crop scale과 font rasterization contract를 어떻게 고정할지를 먼저 명세해야 한다. 이 보고서는 해당 수정이나 v2 실행을 수행하지 않는다.
