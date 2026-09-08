# v1 수직 화살표 방향 반전: 읽기 전용 진단

## 결론과 적용 범위

`block_flow_1302_00054`의 v1 native 출력에서 수직 화살표 두 개가 뒤집힌 최초 경계는
**`visual_connectors._arrow_direction`의 방향 관측**이다. solver/emit adapter와
PowerPoint XML은 이미 잘못 결정된 방향을 그대로 보존했다.

이 진단은 v1 `MLSlideIRProvider`의 visual geometry 경로에 한정한다.
루트의 R8-P는 `region.trace_scene`을 사용하므로 해당 경로의 원인으로 일반화하지 않는다.
제품 코드 수정·재학습·새 COM 실행은 하지 않았다.

## 근거와 읽기 경계

- 분석 시 HEAD: `8328219996f2ebf965853b30b021775540d1eee7`.
- 원본 RGB SHA: `3119868e3b4e9cf1ffa11d1288d37b485fefa42d6721c722273c9cd4729f6570`.
- 고정 예측: `artifacts/ml-image-only-v1/baseline_legacy_predictions.json`.
- 실제 출력: 같은 루트 `native-baseline/000.pptx`, `native-candidate/000.pptx`.
- 실제 PowerPoint 렌더는 기존 `native_contact.png`와 `native-render.json`을 읽었다.

provider 호출에서는 기존 예측과 복사된 RGB만 사용했다. 모델 checkpoint 추론은
다시 하지 않았고, 메모리에서 함수 입출력을 관찰했다. 그 후 별도 진단 단계에서만
원본 annotation/PPT 방향을 비교했다. GT 좌표·역할·제외 마스크를 복원 입력으로 넣지 않았다.

아래 fixture는 관찰한 component의 폭만 담는다. 테스트는 fixture JSON과 코드만 읽으며
원본 RGB·GT·checkpoint·PPT 없이 실행된다.

## 최초 오판정

`slide_ir_provider.py:176`은 visual geometry를 사용한 경우 morphological 옵션에서도
`visual_connectors`로 분기한다. 실제 candidate의 source도 `visual_connector`였다.
이 두 연결에는 `morphological_connectors._arrowhead_end`가 실행되지 않았다.

| 관찰 | gap A (Deploy→Audit) | gap B (Release→Input) |
|---|---|---|
| RGB owner의 y 경계 | 94→152 | 209→267 |
| cross x 경계 | 269..372 | 109..212 |
| 방향 crop의 y 범위 | 98:148 | 213:263 |
| 복원 bridge | (320, -1, 1.0) | (160, -1, 1.0) |
| 가장 큰 폭 증가 | 2 px | 1 px |
| 가장 큰 폭 감소 | 3 px | 2 px |

`visual_connectors.py:353`의 inset은 이 이미지에서 4 px다.
dominant background와의 색 거리≥24(`:432`)로 얻은 mask에는 그림자가 남는다.
가로 rule 제거 후 세로 `MORPH_CLOSE`, kernel 9×1(`:378`)를 적용한 mask를
방향 판정에 그대로 사용한다(`:405`). 경계 근처 잔류가 closing을 통해 퍼진다.

실제 `_arrow_direction` 입력의 폭을 run-length로 쓰면 다음과 같다.

```text
A: 11×3, 8×1, 7×39, 8×2, 9×2, 11×3
B:  9×4, 7×39, 8×2, 9×2, 10×1, 11×2
```

처음의 폭 감소가 아래쪽 실제 head의 폭 증가보다 크다. `:473-478`은
`negative_jump >= 2` 및 `negative_jump >= positive_jump * 1.25`이면 즉시 -1을 반환한다.
따라서 source 경계의 그림자/보정 mask 단차가 역방향 화살촉 증거로 취급된다.

방향 점수와 bridge coverage도 구분되지 않는다. 이 사례 coverage=1.0으로
candidate confidence가 1.0이 되지만 방향 관측은 틀렸다.

## 경로·플래그·XML 경계

`visual_connectors.py:104`는 direction<0일 때 owner와 path를 서로 바꾼다.
이는 잘못된 방향값을 받은 뒤의 일관된 처리다.

| 단계 | gap A | gap B |
|---|---|---|
| 원본 관찰 방향 | 아래 | 아래 |
| candidate path | (320,152)→(320,94) | (160,267)→(160,209) |
| candidate owner | Audit→Deploy | Input→Release |
| candidate 화살촉 | start=false/end=true | start=false/end=true |
| 최종 PPT XML | flipV=1, tailEnd=triangle | flipV=1, tailEnd=triangle |

`connectors/solve.py:58-62`, `emit/adapt.py:92-96`은 경로·플래그를 보존한다.
`pptx_writer.py:444-447`은 end를 `a:tailEnd`, start를 `a:headEnd`로 기록한다.
실제 baseline/candidate XML은 같은 두 upward connector이고 headEnd는 없다.
이 사례를 해결하기 위해 headEnd/tailEnd나 emitter 방향을 교환할 근거는 없다.

후속 GT 비교의 원본 경로는 y93.6→151.2 및 y208.8→266.4, end=true였다.
원본 PPT도 tailEnd=triangle이고 flipV가 없었다.
원본 PPT SHA는 `36a77d5104e162673aba8b9e4a5d0ae6766e97aee314710b4b81b47a8579c2f6`이다.

## 최소 재현과 원인 분리

GT-free fixture:
`tests/fixtures/visual_arrow_direction_known_failure_v1.json`.
폭 profile을 각 행 중앙에 놓은 boolean mask로 복원해 현행 함수를 호출한다.

```python
import numpy as np
from image_to_editable_ppt.ml.visual_connectors import _arrow_direction

widths = [11] * 3 + [8] + [7] * 39 + [8] * 2 + [9] * 2 + [11] * 3
mask = np.zeros((50, 15), dtype=bool)
for row, width in enumerate(widths):
    mask[row, 7 - width // 2 : 7 - width // 2 + width] = True
assert _arrow_direction(mask, axis="vertical") == -1  # 현행 실패 관측
```

같은 실제 RGB crop의 gray<140 mask만으로 방향 함수를 호출하면 두 경우 모두 +1이었다.
closing mask의 처음 4행만 제외하면 A는 +1, B는 0이었고, 양끝 4행 제외 시 둘 다 0이었다.
이는 shadow/boundary mask가 판정에 영향을 준다는 대조 실험이다. 고정 threshold140이나
모든 이미지의 4행 제거가 올바른 제품 수정이라는 검증은 하지 않았다.

폭-only fixture는 원본 색상·가로 위치·완전한 tip 형상을 보존하지 않는다. 따라서
미래 수정의 이 fixture 허용값은 +1 또는 보수적 0이다. 항상0을 반환하는 퇴행은
별도의 깨끗한 정방향/역방향 화살표 positive control이 잡는다.

## 테스트 해석 및 후속 수정 제안

`test_visual_arrow_direction_known_failure.py`는 현행 -1을 특성화하는 테스트와,
허용값0/+1을 요구하는 `xfail(strict=True, raises=AssertionError)` 테스트를 함께 둔다.
**xfail은 알려진 실패이며 방향 정확도 통과가 아니다.** 제품 수정 후에는 엄격 XPASS와
현재 동작 특성화 실패가 생기므로, 그때 근거를 검토하고 mark/특성화 기대값을 함께 갱신한다.
버그 자체를 영구 제품 요구사항으로 유지하려는 테스트가 아니다.

후속 수정 후보는 연결 존재 확인용 repair mask와 방향용 원픽셀 증거를 분리하고,
crop 경계의 그림자 단차가 head 증거가 되지 않도록 shaft/head/tip의 국소 위치와
형상 일관성을 요구하는 것이다. 충돌·tip clipping 시에는 방향을 보류하고,
coverage와 direction confidence를 별도로 기록하는 것이 적절하다.

제품 수정 시에는 실제 RGB 두 crop 외에도 반대 방향·밝은색·그림자 없는 stroke·
무화살표·양방향 사례를 별도로 검증해야 한다. 이번 fixture만으로 일반화를 승인하지 않는다.

재현 명령:

실행 결과는 **13 passed, 2 xfailed**다. 두 xfail은 본문의 두 현행 오방향 사례다.

```text
rtk proxy C:/vs/ImageToEditablePPT/.venv/Scripts/python.exe -m pytest -q -rx tests/test_visual_arrow_direction_known_failure.py tests/test_visual_connectors.py
```
