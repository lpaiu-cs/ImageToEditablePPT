# ImageToEditablePPT MVP

이 저장소는 논문용 구조적 다이어그램에서 **확실한 primitive만 보수적으로 추출**해 PowerPoint의 editable object로 내보내는 MVP 골격을 제공한다.

현재 CLI와 workbench 러너의 기본 경로는 **VLM proposal + local CV snapping + explicit routing** 기반의 semantic-first 하이브리드 파이프라인이다. `VLM_API_KEY`가 없을 때만 기존 bottom-up CV 파이프라인으로 fallback한다.

## 현재 지원 범위

- 단일 이미지 입력
- text-like / icon-like residual을 geometry fitting 전에 억제하고, `unknown` residual은 weak proposal로 보류하는 non-diagram filtering
- geometry용 detail mask와 별도로 raw text-mask source를 유지하고, text-like glyph를 morphological closing으로 word/block mask로 묶어 bridge evidence로 재사용
- axis-aligned rectangle / rounded rectangle 검출
- straight line 검출
- weak / large residual component에 대한 outer contour 기반 box fallback
- 채워진 solid region에서의 conservative filled-box fallback
- image-wide Hough stroke를 global segment graph로 조립하는 connector proposal
- 강한 근거가 있을 때만 수행하는 evidence-aware occlusion repair
- `cv2.HoughLinesP` + collinear merge 기반의 conservative segment proposal
- box edge 근처 segment endpoint를 box 외곽선으로 연장하는 conservative endpoint snapping
- simple multi-segment orthogonal connector 검출
- simple arrow 검출
- 닫힌 박스의 대표 단색 fill 추정
- non-uniform background에서 local contrast 기반 detail mask를 병행하는 보수적 전처리
- 높은 신뢰도 텍스트만 포함하는 선택적 OCR 게이트
- editable PPTX export
- synthetic 및 paper-like rasterized fixture 기반 테스트

## 의도적으로 비지원인 것

- pixel-perfect 재현
- icon / photo / logo / illustration raster fallback
- gradient / texture / shadow 재현
- 자유곡선 일반 복원
- chart / plot semantic reconstruction
- 근거 없는 occlusion 복원
- 낮은 신뢰도 OCR 강제 포함

## 설계 원칙

- 검출보다 생략을 우선한다.
- proposal 단계에서는 `definitely_non_diagram`만 제거하고, 애매한 residual은 후단 조립/선택으로 넘긴다.
- text-like candidate는 글자 단위가 아니라 phrase/block 단위 mask로 먼저 묶어 suppression과 gap bridge에 함께 사용한다.
- text block이 gap의 대부분을 차지하면 그 구간은 explicit bridge prior로 취급해 segment assembly와 repair를 밀어준다.
- weak component는 전체 픽셀 덩어리 대신 outer contour로 다시 본다.
- fill은 닫힌 박스에만 적용한다.
- 비-다이어그램으로 보이는 복합 요소는 생략한다.
- OCR이 꺼져 있어도 text-like region은 geometry 후보에서 제거한다.
- semantic prior가 있을 때는 픽셀보다 문맥을 먼저 믿는다.
- OCR은 기본 비활성화에 가까운 선택 기능이며, 없으면 텍스트를 생략한다.
- gap repair는 작은 거리만으로 허용하지 않고, 정렬/두께/명암/occluder/conflict 여부를 함께 본다.

## 사용 방법

```bash
python -m pip install -e .
image-to-editable-ppt input.png output.pptx
```

semantic-first 모드 사용 전:

```bash
cp .env.example .env
```

`.env`에 `VLM_API_KEY`를 채우면 CLI와 workbench runner가 semantic-first로 동작한다. 키 없이 실행하면 legacy CV fallback을 사용한다.

선택적 OCR:

```bash
python -m pip install -e .[ocr]
image-to-editable-ppt input.png output.pptx --ocr
```

JSON 디버그 출력:

```bash
image-to-editable-ppt input.png output.pptx --debug-elements elements.json
```

legacy 강제 실행:

```bash
image-to-editable-ppt input.png output.pptx --legacy
```

검증 workbench 생성:

```bash
python tools/alignment_loop.py input.png
```

위 스크립트는 `workbench2.0/input-alignment/iter_XX/` 아래에 다음 artifact를 남긴다.

- `output.pptx`
- `output.svg`
- `output.png`
- `overlay.png`
- `edge-diff.png`
- `comparison.json`

`output.svg`와 `output.png`는 생성된 `PPTX`를 다시 읽어 재구성한 검증용 출력이다. 즉, 외부 raster fallback 없이 실제 export 결과를 기준으로 비교한다.

## 파이프라인

1. semantic proposal: VLM이 node/edge topology와 coarse bbox를 JSON으로 추출
2. local geometry snapping: node별 crop 안에서만 contour/gradient를 다시 보고 `exact_bbox`를 보정
3. style extraction: 보정된 bbox 기준으로 stroke / fill representative color 추정
4. text hydration: VLM text를 우선 사용하고, 비어 있는 node만 선택적 OCR로 보충
5. explicit routing: edge topology를 기준으로 connector/arrow 경로를 프로그래밍 방식으로 생성
6. confidence gating: 낮은 신뢰도 primitive 생략
7. PPT export: primitive별 editable object 생성

legacy fallback은 기존 bottom-up CV 경로를 유지한다.

## Export Semantics

- `rect` / `rounded_rect`는 PowerPoint 기본 도형으로 내보낸다.
- `line`은 straight connector로 내보낸다.
- `orthogonal_connector`는 open freeform polyline으로 내보낸다.
- `arrow`는 straight connector가 가능하면 connector로, elbow route면 freeform polyline + OOXML arrow ending으로 내보낸다.
- DrawingML connector에서는 시작점이 `head`, 끝점이 `tail`이므로, 정규화된 arrow tip은 `tailEnd`에 매핑된다.
- `python-pptx`가 공개 API로 arrowhead를 직접 노출하지 않기 때문에, semantic arrow ending 삽입이 실패하면 freeform arrow shape로 fallback한다.
- 즉, arrow는 가능한 경우 더 semantic하게 내보내지만, 항상 spec-perfect하다고 주장하지 않는다.

## 테스트로 확인한 범위

- 깨끗한 synthetic diagram에서 core primitive 검출과 PPTX export
- paper-like occlusion이 있을 때 강한 근거 기반 box repair
- 약한 기하 근거와 conflict가 있는 경우 repair 생략
- noisy open contour에서 fill 금지
- mixed figure에서 non-diagram region omission
- dense text-heavy rasterized diagram에서 text fragment suppression과 large container survival
- semantic proposal이 있을 때 coarse bbox fallback으로 node 자체를 버리지 않음
- text-like glyph를 phrase/block mask로 묶어 bridge region으로 재사용
- explicit border가 약한 filled panel의 conservative box recovery
- global segment graph longest-path 기반 connector recovery
- near-box connector endpoint snapping
- OCR off 상태에서 text glyph가 geometry primitive로 새지 않음
- multi-segment orthogonal connector의 보수적 검출
- arrow export의 arrowhead markup 생성

## 현재 한계

- semantic-first 경로는 VLM proposal 품질에 크게 의존한다.
- 현재 API 호출은 OpenAI-compatible chat completions 형식을 기본 가정한다.
- 박스/커넥터는 axis-aligned 구조에 강하게 편향되어 있다.
- orthogonal connector는 단순한 chain만 지원하며, branch/T-junction/loop는 생략한다.
- arrow는 shaft + 한쪽 끝 widening 신호를 사용하는 단순 검출이다.
- OpenCV는 external contour fitting과 Hough segment proposal에만 사용한다. 이는 dense raster diagram에서 text/icon fragment를 그대로 primitive로 오인하지 않으면서 큰 구조를 다시 제안하기 위한 최소 추가 의존성이다.
- mean-shift fill region fallback은 넓고 균질한 채움 면을 panel box로 제안할 수 있지만, partial open contour나 decorative blob로 보이면 생략한다.
- OCR은 `pytesseract`가 설치되어 있을 때만 동작하며, text-like cluster crop이 구조적으로 그럴듯한 위치에 있을 때만 포함한다.
- 실제 논문 figure 전체에서 diagram subregion 분리는 아직 제한적이다.
- dense paper-like fixture는 커버하지만, polished infographic / UI mockup / general figure reconstruction을 지원한다고 주장하지 않는다.
- 큰 캔버스에서는 major panel recovery를 위해 추가적인 conservative box/line fallback이 켜지지만, 여전히 구조 근거가 약하면 생략한다.
