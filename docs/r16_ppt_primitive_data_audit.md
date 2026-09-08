# R16-PG source PPT 데이터 감사

## 사용 가능한 데이터

학습용 확정본은 `artifacts/r16-ppt-primitive-data-v2/dataset_manifest.json`이다. SHA는 `bbbaa437653631cc8d3ef96874dd0387ced57fbb57ade8f5b051723b515328bb`이다. 모델·예측을 사용하지 않고 source PPT에서 만든 72쌍을 실제 PowerPoint COM 320×200으로 렌더했다. source 크기는 800×500이고 input/mask companion 총 144개 PPT는 각각 1 slide다.

| stage | train | calibration | eval |
|---|---:|---:|---:|
| primitive | 24 | 0 | 0 |
| scene | 24 | 8 | 8 |
| negative | 4 | 2 | 2 |

종류는 1 rectangle, 2 rounded rectangle, 3 ellipse, 4 diamond, 5 parallelogram, 6 cylinder다. primitive는 종류별 4장, scene은 장마다 종류별 하나다. 입력 색·선폭·선택적 글자는 class와 독립적으로 추출했다. preset adjustments는 기본값을 사용하고 actual source 값과 input/mask의 동일성을 기록했다. 회전·가림·중첩이 없고 positive에는 connector가 없다. negative의 열린 선은 연결 관계 없는 native line 객체다.

## 마스크와 v1 중단 이유

v1의 cyan cylinder는 native preset의 topface lighten 때문에 `(102,255,255)`가 됐다. primitive-train-020에서 그 내부 459px가 AA로 오인되어 ignore 처리된 것을 **학습 전에** 육안으로 발견했다. v1은 사용 중지하고 원본·builder·manifest·렌더를 보존했다.

승인된 수정 계약에 따라 v2는 동일 geometry/adjustments의 white fill/no outline/black background companion PPT를 COM 렌더한다. 순백 픽셀만 겹치지 않는 source bbox로 소유자를 정해 class palette에 배정하고 순검정은 0, 나머지 AA 색은 palette의 어느 class와도 일치하지 않는 회색128로 남긴다. grayscale target에서는 이 회색을 ignore255로 처리한다. cylinder 윗면 전체는 이제 포함되며 preset 내부 rim의 얇은 raster AA seam은 ignore로 남는다.

이는 같은 COM renderer의 도형 점유 영역이며 잉크·텍스트 픽셀 정답이 아니다. 입력 글자가 덮는 부분도 도형 소유 영역으로 포함한다. bbox는 target 생성/evaluator만 사용하며 runtime crop 입력이 아니다.

## 검사 결과

- source XML의 object별 xfrm/preset geometry가 input/mask에서 정확히 일치한다. picture는 없다. source 객체의 효과 목록을 명시적으로 비워 테마 그림자를 배제했다.
- 144개 source PPT 및 COM receipt SHA를 검증했다. RGB 변환 전후 픽셀이 동일하고 해상도는 모두 320×200이다.
- 입력 RGB 72개의 SHA가 모두 고유하다. v1/v2의 72개 입력 RGB SHA 및 objects geometry/adjustments는 모두 동일하다. 7개 stage/split seed도 유지했다.
- 모든 bbox가 화면 내부이고 서로 겹치지 않는다. bbox 밖 purewhite 및 bbox 중첩은 assertion 실패로 처리한다.
- 모든 positive의 기대 class 내부가 최소16px 존재하며 뜻하지 않은 class는 없다. negative 8개는 전 픽셀0이다.
- primitive train의 6종과 scene train의 6종, negative를 input/raw white occupancy/derived palette 보드로 직접 확인했다. 보드는 `artifacts/r16-ppt-primitive-data-v2/training-qa-board.png`이며 `qa.py`가 재검사와 보드를 만든다.
- COM은 반환했고 POWERPNT 프로세스가 남지 않았다. 모델 학습·추론·새 다운로드·기존 Phase16 holdout payload 접근은 없었다.

split마다 seed와 scene ID는 다르지만 scene의 grid3x2 layout family는 공유한다. 따라서 독립 seed 장면 평가이지 새로운 layout family 일반화가 아니다. mask background와 negative mask의 중복은 의도적이며 입력 RGB 중복과 구분한다. 사진 음성·instance 분리·overlap·renderer 간 일반화는 검증하지 않는다.

## 파일 계약과 재현

각 record의 `image`는 전체 RGB, `mask`는 derived palette RGB, `mask_raw`는 white COM RGB다. `target`은 0..6/255 단일채널이다. `objects`에는 ID, kind, source bbox, 320×200 bbox, adjustments와 입력 스타일이 있다. source/mask PPT SHA, raw render SHA, derived palette SHA, target SHA를 별도로 묶었다.

```powershell
C:/vs/ImageToEditablePPT/.venv/Scripts/python.exe tools/r16_ppt_primitive_data.py build --out <새폴더>
# POWERPNT가 없는 상태에서만 COM 슬롯을 확보한다.
& C:/vs/ImageToEditablePPT/tools/render_pptx_via_powerpoint.ps1 -InputPath <새폴더>/pptx -OutputDirectory <새폴더>/renders -Width 320
C:/vs/ImageToEditablePPT/.venv/Scripts/python.exe tools/r16_ppt_primitive_data.py finalize --out <새폴더>
```

- v2 preregister SHA: `e56cad7302add22aba1581d7eb46b98afcc6f3259531a9c749a0911517e23a8f`
- v2 COM manifest SHA: `af3771304257699c37d71c7514868d7b9ff6596035d15aad7df62f456233ec7a`
- generator SHA: `9673336efe15ede4cf7dda87c0574287b34decf31bdeaa41a9156e17c52e436c`

source 생성·mask 구성 오류를 학습 전 수정한 것이며 예측 결과에 맞춘 정답 수정은 없다.
