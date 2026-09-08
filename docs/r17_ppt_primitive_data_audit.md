# R17 새 calibration/eval 데이터 감사

확정 데이터는 `artifacts/r17-ppt-primitive-data-v1/dataset_manifest.json`이며 SHA는 `36e2c3a5c9a43774bb8d64657f6a4147236699edc34129b7e28cd9c920f25d96`이다. 새 32 input/mask 쌍, 총64개 1-slide PPT를 source800×500에서 실제 COM320×200으로 렌더했다. 모델 학습·추론은 실행하지 않았다.

| split/stage | 개수 | seed | source 배치 |
|---|---:|---:|---|
| calibration/scene | 12 | 17022 | 3열×2행 |
| calibration/negative | 4 | 17032 | 열린 선과 텍스트 |
| eval/scene | 12 | 17023 | 2열×3행 |
| eval/negative | 4 | 17033 | 열린 선과 텍스트 |

scene마다 6종 preset이 하나씩 있고 종류 순서, 색, 선폭, 선택적 텍스트를 독립 추출한다. 폭120..205 source px, calibration 높이95..170, eval 높이95..130이다. eval은 layout뿐 아니라 높이/종횡비 분포도 달라져 두 효과를 분리할 수 없다. negative의 레이아웃 family는 공유한다. 모두 무회전·무중첩·채움 있는 default adjustments 조건이며 사진·outline-only·연결 관계 학습 자료가 아니다.

## 정답과 재현 경계

R16 v2의 white occupancy 계약을 그대로 사용했다. input과 동일 geometry/adjustments의 white/no-outline/black-background PPT를 COM 렌더하고, 겹치지 않는 source bbox 내부의 순백 픽셀을 palette class로 배정한다. 순검정은0, 다른 색은 derived RGB 회색128/target ignore255다. bbox 밖 순백과 bbox 겹침은 assertion 실패다. cylinder의 topface는 포함하고 얇은 preset rim AA seam은 ignore로 남는다.

`image`, `mask`(derived palette), `mask_raw`(white COM), `target`, `objects`, `bbox` 필드는 R16과 같다. bbox는320×200 좌표이며 source bbox와 adjustments도 보존한다. GT bbox는 정답 생성/감사에만 쓰고 predictor 입력이 아니다. source/mask PPT, COM raw render, derived palette, target SHA를 각각 기록했다.

동결된 R16 파일을 수정하지 않기 위해 새 `tools/r17_ppt_primitive_data.py`에 생성 레시피를 보존하고 population/seed/layout/count만 바꿨다. 기존 deck label·해시 helper는 재사용한다. 새 source ID는 모두 `r17-`로 시작하며 기존 R16 calibration/eval payload는 읽지 않았다.

## 검사

- 64개 source PPT/COM receipt SHA 및 RGB 변환 픽셀 동일성 검사 통과.
- input/mask의 object xfrm/preset geometry와 adjustments 일치, picture 없음.
- 32개 RGB SHA 상호 고유. 기존 R16 v2 manifest의72개 입력 SHA와도 중복 없음. 기존 데이터는 manifest 해시 정보만 비교했다.
- 모든 scene은 6종 각1개이며 class별 내부16px 이상, 전체 bbox 범위/무중첩/순백 ownership 검사 통과. negative는 target 전체0.
- calibration16개 input/raw occupancy/palette 보드를 직접 확인했다. 경로는 `artifacts/r17-ppt-primitive-data-v1/calibration-qa-board.png`이며 읽기 편한 두 분할은 `calibration-qa-board-0.png`, `calibration-qa-board-1.png`다.
- eval은 생성 구조/정답/receipt 감사만 수행했다. eval 이미지 육안 확인·모델 성능 측정·root에 eval 시각 정보 전달은 하지 않았다.
- `artifacts/r17-ppt-primitive-data-v1/qa.py`와 `qa.json`에 추가 QA가 남아 있다. COM은 반환했고 POWERPNT 프로세스가 없다.

## 재현

```powershell
C:/vs/ImageToEditablePPT/.venv/Scripts/python.exe tools/r17_ppt_primitive_data.py build --out <새폴더>
# COM 슬롯과 기존 POWERPNT 부재를 먼저 확인한다.
& C:/vs/ImageToEditablePPT/tools/render_pptx_via_powerpoint.ps1 -InputPath <새폴더>/pptx -OutputDirectory <새폴더>/renders -Width 320
C:/vs/ImageToEditablePPT/.venv/Scripts/python.exe tools/r17_ppt_primitive_data.py finalize --out <새폴더>
```

preregister SHA: `be9ca5d6f919fa1a07737b1fe4a13b5d136d901eb071f604ba4aeb9171a2c126`.
COM manifest SHA: `37886ddd2094191d1a4b973ec26432e96ea041525441ec74505556ae0b97fe0f`.

학습은 기존 R16 train만 사용하고 이 데이터에는 train split이 없다. 새 데이터는 예측이나 결과를 보고 수정하지 않았다. root의 `docs/r17_object_primitive_spec.md`와 대조해 요청한 데이터 계약이 일치함을 확인했다.
