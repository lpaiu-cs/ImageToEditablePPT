# ImageToEditablePPT MVP

이 저장소는 논문용 구조적 다이어그램에서 **확실한 primitive만 보수적으로 추출**해 PowerPoint의 editable object로 내보내는 MVP 골격을 제공한다.

## 현재 지원 범위

- 단일 이미지 입력
- axis-aligned rectangle / rounded rectangle 검출
- straight line 검출
- one-bend orthogonal connector 검출
- simple arrow 검출
- 닫힌 박스의 대표 단색 fill 추정
- 높은 신뢰도 텍스트만 포함하는 선택적 OCR 게이트
- editable PPTX export
- synthetic fixture 기반 테스트

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
4. occlusion repair: 강한 기하 근거가 있는 collinear gap merge
5. style extraction: stroke / fill representative color 추정
6. text extraction: 선택적 OCR + 구조적 역할 게이트
7. confidence gating: 낮은 신뢰도 primitive 생략
8. PPT export: primitive별 editable object 생성

## 현재 한계

- 박스/커넥터는 axis-aligned 구조에 강하게 편향되어 있다.
- orthogonal connector는 MVP에서 one-bend L-shape 중심이다.
- arrow는 shaft + 한쪽 끝 widening 신호를 사용하는 단순 검출이다.
- OCR은 `pytesseract`가 설치되어 있을 때만 동작하며, box 내부 등 구조적 위치에서만 포함한다.
- 실제 논문 figure 전체에서 diagram subregion 분리는 아직 제한적이다.
