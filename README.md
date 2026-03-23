# ImageToEditablePPT MVP

이 저장소는 논문용 구조적 다이어그램에서 **확실한 primitive만 보수적으로 추출**해 PowerPoint의 editable object로 내보내는 MVP 골격을 제공한다.

## 현재 지원 범위

- 단일 이미지 입력
- axis-aligned rectangle / rounded rectangle 검출
- straight line 검출
- 강한 근거가 있을 때만 수행하는 evidence-aware occlusion repair
- simple multi-segment orthogonal connector 검출
- simple arrow 검출
- 닫힌 박스의 대표 단색 fill 추정
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
- fill은 닫힌 박스에만 적용한다.
- 비-다이어그램으로 보이는 복합 요소는 생략한다.
- MVP는 결정적 heuristic 파이프라인으로 시작한다.
- OCR은 기본 비활성화에 가까운 선택 기능이며, 없으면 텍스트를 생략한다.
- gap repair는 작은 거리만으로 허용하지 않고, 정렬/두께/명암/occluder/conflict 여부를 함께 본다.

## 사용 방법

```bash
python -m pip install -e .
image-to-editable-ppt input.png output.pptx
```

선택적 OCR:

```bash
python -m pip install -e .[ocr]
image-to-editable-ppt input.png output.pptx --ocr
```

JSON 디버그 출력:

```bash
image-to-editable-ppt input.png output.pptx --debug-elements elements.json
```

## 파이프라인

1. 전처리: 배경 추정, foreground / boundary mask 구성, speck 제거
2. 구조 후보 탐지: 수평/수직 stroke 추출, 박스 후보 탐지
3. primitive fitting: box / line / arrow / connector fitting
4. occlusion repair: 정렬, 폭, 명암, occluder, conflict를 함께 보는 evidence-aware merge
5. style extraction: stroke / fill representative color 추정
6. text extraction: 선택적 OCR + 구조적 역할 게이트
7. confidence gating: 낮은 신뢰도 primitive 생략
8. PPT export: primitive별 editable object 생성

## Export Semantics

- `rect` / `rounded_rect`는 PowerPoint 기본 도형으로 내보낸다.
- `line`은 straight connector로 내보낸다.
- `orthogonal_connector`는 open freeform polyline으로 내보낸다.
- `arrow`는 먼저 straight connector + OOXML arrow ending을 시도한다.
- DrawingML connector에서는 시작점이 `head`, 끝점이 `tail`이므로, 정규화된 arrow tip은 `tailEnd`에 매핑된다.
- `python-pptx`가 공개 API로 arrowhead를 직접 노출하지 않기 때문에, semantic arrow ending 삽입이 실패하면 freeform arrow shape로 fallback한다.
- 즉, arrow는 가능한 경우 더 semantic하게 내보내지만, 항상 spec-perfect하다고 주장하지 않는다.

## 테스트로 확인한 범위

- 깨끗한 synthetic diagram에서 core primitive 검출과 PPTX export
- paper-like occlusion이 있을 때 강한 근거 기반 box repair
- 약한 기하 근거와 conflict가 있는 경우 repair 생략
- noisy open contour에서 fill 금지
- mixed figure에서 non-diagram region omission
- multi-segment orthogonal connector의 보수적 검출
- arrow export의 arrowhead markup 생성

## 현재 한계

- 박스/커넥터는 axis-aligned 구조에 강하게 편향되어 있다.
- orthogonal connector는 단순한 chain만 지원하며, branch/T-junction/loop는 생략한다.
- arrow는 shaft + 한쪽 끝 widening 신호를 사용하는 단순 검출이다.
- OCR은 `pytesseract`가 설치되어 있을 때만 동작하며, box 내부 등 구조적 위치에서만 포함한다.
- 실제 논문 figure 전체에서 diagram subregion 분리는 아직 제한적이다.
- paper-like fixture는 커버하지만, 실제 모든 논문 raster artifact를 일반적으로 다루는 수준은 아니다.
