# conversion-spec.md

> Status: Draft v0.1
> 
> 이 문서는 **ImageToEditablePPT**의 변환 규격을 정의한다. 상위 규범은 `principle.md`이며, 에이전트 행동 규칙은 `AGENTS.md`를 따른다. 충돌 시 우선순위는 다음과 같다.
>
> `principle.md` > `AGENTS.md` > `conversion-spec.md`

---

## 1. 목적

이 문서는 입력 이미지로부터 어떤 요소를 추출하고, 어떤 기준으로 생략하며, 어떤 방식으로 PowerPoint의 editable object로 내보내는지를 **구현 가능한 수준으로 명세**하기 위해 존재한다.

핵심 목표는 다음과 같다.

1. 논문용 **구조적 다이어그램**의 수작업 재현 비용을 줄인다.
2. 결과물을 PowerPoint에서 **즉시 수정 가능한 primitive** 중심으로 만든다.
3. 불확실한 복원을 줄이고, 확실한 구조만 안정적으로 변환한다.

이 문서는 **완벽 복제 규격**이 아니다. 이 문서는 **보수적이고 수정 친화적인 구조 복원 규격**이다.

---

## 2. 규범적 표현

이 문서에서 다음 용어는 아래 의미를 가진다.

- **MUST / 반드시**: 구현이 반드시 지켜야 하는 요구사항
- **SHOULD / 권장**: 강하게 권장되나, 합리적 이유가 있으면 예외 가능
- **MAY / 선택**: 구현체가 선택적으로 채택할 수 있음

---

## 3. 범위

### 3.1 1차 대상

다음과 같은 **구조적 다이어그램 요소**를 변환 대상으로 본다.

- rectangle
- rounded rectangle
- closed box / closed contour
- line segment
- orthogonal connector
- arrow
- section divider
- 구조적 라벨 텍스트

### 3.2 비대상

다음은 변환 대상이 아니다.

- 아이콘
- 로고
- 사진
- 일러스트
- 장식용 그래픽
- 배경 텍스처
- 그래프 플롯 자체의 곡선과 마커
- heatmap, microscopy image, screenshot, UI capture
- 의미가 불명확한 복합 그림 요소

비대상은 **변환하지 않고 공백으로 둔다.**

### 3.3 비목표

이 프로젝트는 아래를 목표로 하지 않는다.

- pixel-perfect 복제
- 모든 paper figure 일반 복원
- 비-다이어그램 요소의 벡터화
- gradient, shadow, texture 재현
- 근거 없는 의미적 상상 복원

---

## 4. 핵심 정의

### 4.1 구조적 다이어그램 요소
도식의 구조, 흐름, 관계, 경계, 구획을 구성하는 시각 요소.

### 4.2 닫힌 박스
시각적으로 폐곡선을 이루며 내부 영역이 정의 가능한 box/contour.

### 4.3 열린 박스
경계가 끊겨 있어 내부를 확정할 수 없는 box-like contour.

### 4.4 비-다이어그램 요소
구조 설명의 핵심이 아니며, 장식/삽화/이미지 성격이 강한 요소.

### 4.5 가림(occlusion)
텍스트, 아이콘, 기타 오브젝트 때문에 원래 하나의 선/박스가 부분적으로 보이지 않는 상태.

### 4.6 강한 근거(strong evidence)
아래 중 복수의 신호가 일관되게 성립하여, 분절된 조각을 하나의 객체로 보는 것이 더 자연스러운 상태.

- collinearity
- 동일 또는 거의 동일한 두께
- 동일 또는 거의 동일한 stroke color
- 동일한 dash/solid style
- box geometry 상 자연스러운 연장
- 텍스트/아이콘이 gap의 직접 원인으로 보임
- 반복 패턴 또는 대칭
- 정렬 관계가 명확함

### 4.7 대표 단색(representative solid color)
노이즈, 그라데이션, anti-aliasing, 그림자 영향을 제거한 뒤 내부 영역을 대표하는 하나의 단색.

---

## 5. 입력 계약(Input Contract)

### 5.1 입력 단위
구현체는 최소한 아래 입력을 지원해야 한다.

- 단일 이미지 파일 1개

지원 형식은 구현 선택이지만, 기본적으로 다음을 권장한다.

- PNG
- JPEG/JPG
- WEBP
- SVG(있으면 rasterize 또는 vector path 활용 가능)

### 5.2 입력 가정

입력은 논문 figure 전체일 수도 있고, 일부 crop일 수도 있다.
구현은 **전체 figure에서 구조적 diagram 부분만 골라서 변환**할 수 있어야 한다.

### 5.3 입력 해상도

- 너무 저해상도여서 구조 판별이 불가능하면 생략이 늘어날 수 있다.
- 저해상도 입력에서도 억지 복원을 시도해서는 안 된다.

---

## 6. 출력 계약(Output Contract)

### 6.1 기본 출력
기본 출력은 다음을 만족해야 한다.

1. 결과는 **PowerPoint에서 개별 선택·이동·수정 가능한 객체 집합**이어야 한다.
2. 비-다이어그램 요소는 래스터 fallback 없이 **생략**되어야 한다.
3. 불확실한 요소는 **추가하지 않는다.**
4. 닫힌 박스만 fill을 가진다.
5. gradient fill은 사용하지 않는다.

### 6.2 좌표 보존

- 출력 객체는 입력 이미지의 상대적 배치를 유지해야 한다.
- 전체 배율은 달라도 되지만, **객체 간 기하 관계**는 유지되어야 한다.
- 권장 방식은 입력 이미지 좌표계를 슬라이드 좌표계에 선형 매핑하는 것이다.

### 6.3 객체 단위
다음은 separate editable object로 생성하는 것을 원칙으로 한다.

- 박스 하나 = 객체 하나
- 선분/커넥터 하나 = 객체 하나
- 화살표 하나 = 객체 하나
- 텍스트 블록 하나 = 텍스트 박스 하나

필요 이상으로 여러 조각으로 쪼개는 것은 금지한다.

---

## 7. 내부 중간 표현(IR) 권장안

구현은 내부적으로 어떤 표현을 써도 되지만, 최소한 다음 정보를 표현할 수 있어야 한다.

```text
Element {
  id: string
  kind: rect | rounded_rect | line | orthogonal_connector | arrow | text
  geometry: bbox | points | polyline
  stroke: {
    color,
    width,
    dash_style
  }
  fill: {
    enabled,
    color
  }
  text: {
    content,
    alignment,
    confidence
  } | null
  confidence: float [0,1]
  source_region: bbox
  inferred: boolean
}
```

### 7.1 IR 원칙

- geometry는 가능한 한 **단순한 primitive**여야 한다.
- fill은 닫힌 박스에만 enabled=true 가능하다.
- `inferred=true`는 가려진 부분 복원 같은 보수적 추론이 개입되었음을 뜻한다.

---

## 8. 변환 파이프라인 규격

권장 파이프라인은 아래와 같다.

1. 전처리
2. 구조 후보 탐지
3. 비-다이어그램 필터링
4. primitive fitting
5. occlusion repair
6. style extraction
7. text extraction
8. confidence gating
9. PPT object assembly

구현체는 다른 내부 순서를 사용할 수 있으나, 최종 행동은 본 문서의 규칙을 만족해야 한다.

---

## 9. 전처리 규칙

### 9.1 노이즈 처리
다음은 노이즈로 본다.

- gradient
- 얼룩
- anti-aliasing
- JPEG artifact
- 미세한 음영 변화
- 그림자성 외곽

이들은 구조 정보로 해석해서는 안 된다.

### 9.2 권장 전처리

- 약한 blur 또는 denoise
- edge enhancement
- binarization 또는 adaptive thresholding
- 색상 클러스터링/양자화

단, 전처리 결과 때문에 새로운 구조를 만들어내면 안 된다.

---

## 10. 구조 후보 탐지 규칙

### 10.1 박스
아래 조건을 만족하면 box 후보로 본다.

- 4변 경향이 뚜렷함
- 직교 또는 거의 직교 구조
- 폐곡선 또는 폐곡선에 가까운 contour
- 내부가 하나의 구획으로 해석 가능

#### 10.1.1 rectangle vs rounded rectangle
- corner radius가 일관되게 존재하면 rounded rectangle
- 아니면 rectangle
- 애매하면 rectangle로 단순화하는 것이 권장된다.

### 10.2 선/커넥터
아래를 선/커넥터 후보로 본다.

- 명확한 직선 또는 polyline
- box 간 연결 관계를 형성함
- divider/section line 역할을 함

#### 10.2.1 orthogonal connector
90도 방향 전환이 명확하면 orthogonal connector로 본다.

### 10.3 화살표
다음이 결합되면 arrow 후보로 본다.

- shaft(선분 또는 connector)
- arrow head로 해석 가능한 삼각/chevron 끝단

화살표 머리가 불명확하지만 연결선은 명확한 경우, 기본 line/connector로 내리는 것이 허용된다.

### 10.4 텍스트
텍스트는 구조적 의미가 분명하고 신뢰도가 높을 때만 변환한다.

예:
- box label
- section title
- arrow label

장식적 문구, 워터마크, 캡션 일부, OCR 신뢰도가 낮은 텍스트는 생략 가능하다.

---

## 11. 비-다이어그램 필터링 규칙

### 11.1 반드시 생략할 것
다음은 반드시 변환하지 않는다.

- pictogram
- app icon
- dataset example image
- 사람/동물/사물 사진
- 장식용 pattern
- 배경 텍스처

### 11.2 애매한 경우
애매하면 생략한다.

즉, 아래 분기 규칙을 따른다.

- 구조적 다이어그램 요소라고 **확신 가능** → 변환 후보 유지
- 확신 불가 → 생략

### 11.3 래스터 fallback 금지
비-다이어그램 요소를 “일단 이미지로 넣는 방식”은 기본 출력에서 금지한다.

---

## 12. Primitive fitting 규칙

### 12.1 단순화 우선
원본이 조금 더 복잡해 보여도, 다음 순서로 단순한 primitive를 우선한다.

1. rectangle / rounded rectangle
2. line
3. orthogonal connector
4. arrow
5. text box

### 12.2 복잡 곡선 처리
- 자유곡선이 구조 핵심이 아니면 생략 가능
- 구조 핵심이더라도 단순 line/polyline으로 안정적으로 근사 가능할 때만 포함
- Bezier 재현은 MVP 필수 아님

### 12.3 선 굵기
- anti-aliasing 때문에 경계가 퍼져 보이면 평균 두께로 정규화한다.
- 미세한 두께 변화는 무시한다.

### 12.4 대시 스타일
- dashed 여부가 명확하면 유지
- 불명확하면 solid로 단순화

---

## 13. Occlusion repair 규칙

이 섹션은 본 프로젝트의 핵심 규칙 중 하나다.

### 13.1 기본 원칙
가려진 선/박스는 **강한 근거가 있을 때만** 이어 붙인다.

### 13.2 허용되는 복원
다음은 허용된다.

- 텍스트 때문에 끊겨 보이는 직선의 재연결
- 아이콘 때문에 가려진 박스 테두리의 연장
- 3변이 명확한 박스의 누락된 1변 복원
- 반복 패턴에서 동일 구조가 명확할 때 일부 gap 보정

### 13.3 금지되는 복원
다음은 금지한다.

- 의미 추측만으로 새로운 box 생성
- 보이지 않는 branch 추가
- 모호한 endpoint 사이를 임의 연결
- box인지 table인지 graph인지 불명확한 것을 단정적으로 box 처리

### 13.4 권장 evidence scoring
구현체는 아래와 유사한 보수적 기준을 둘 것을 권장한다.

- +2: 높은 collinearity
- +2: stroke width / color / style 일치
- +1: gap 원인이 텍스트/아이콘 가림으로 명확함
- +1: box geometry 완성도 증가
- +1: 반복 패턴/대칭 근거
- -2: 주변 구조와 충돌
- -2: 연결 시 새로운 의미 구조가 생성됨

권장 정책:
- 총점 >= 3 이고 강한 모순이 없을 때만 복원 고려
- 아니면 생략

이 점수식은 예시이며, 구현은 다른 형태여도 된다. 중요한 것은 **증거 기반의 보수적 복원**이다.

---

## 14. 색상 및 채움 규칙

### 14.1 색상 일반 원칙
색은 구조가 아니라 스타일이다. 스타일은 구조를 해치지 않는 범위에서만 보존한다.

### 14.2 fill 적용 조건
fill은 아래를 모두 만족할 때만 허용된다.

- 폐곡선이 확실함
- box 내부가 정의 가능함
- 내부 샘플링이 가능함

### 14.3 열린 구조
열린 박스, 끊긴 윤곽, 내부가 불명확한 contour에는 fill을 적용해서는 안 된다.

### 14.4 대표 단색 추정
대표 단색은 다음 원칙으로 추정한다.

1. 샘플링 영역은 **항상 박스 내부**에 한정
2. border 근처 stroke 영향은 제외 권장
3. 텍스트/아이콘 픽셀은 제외 권장
4. median 또는 robust mean 사용 권장
5. gradient는 평균화하여 단색으로 환원

### 14.5 금지 사항
금지되는 출력:

- gradient fill
- texture fill
- shadow 재현
- 열린 구조의 임의 fill

---

## 15. Stroke 규칙

### 15.1 stroke color
- 경계에서 대표 stroke color를 추정한다.
- 미세한 색 흔들림은 무시한다.

### 15.2 stroke width
- 대표 width 하나로 정규화한다.
- 아주 얇은 anti-aliased halo는 무시한다.

### 15.3 line endings
- 화살표가 확실하면 arrow ending 사용
- 아니면 plain line ending 사용

---

## 16. 텍스트 처리 규칙

### 16.1 텍스트 포함 조건
다음 조건을 만족하면 editable text로 포함 가능하다.

- OCR 신뢰도가 충분함
- 구조적 역할이 분명함
- 위치가 안정적으로 산출 가능함

### 16.2 텍스트 생략 조건
다음은 생략 가능하다.

- OCR confidence가 낮음
- 장식/배경 텍스트
- 글자 겹침이 심해 판독 불가
- 구조와 무관한 캡션 조각

### 16.3 텍스트 환각 금지
보이지 않는 텍스트를 의미적으로 추정해 채워 넣어서는 안 된다.

### 16.4 폰트 보존
MVP에서는 정확한 font family 재현은 필수 아님.
중요한 것은 **텍스트 내용, 위치, 편집 가능성**이다.

---

## 17. Confidence gating 규칙

각 element는 confidence를 가져야 한다.

권장 정책:

- **0.80 이상**: 기본적으로 포함
- **0.60 이상 0.80 미만**: 단순 primitive만 포함, 텍스트는 더 엄격히 판단
- **0.60 미만**: 기본적으로 생략

confidence 산정 방식은 구현 자유지만, 다음 신호를 반영하는 것이 권장된다.

- geometry 안정성
- contour 완성도
- style 일관성
- OCR 신뢰도
- 주변 구조와의 합치성
- occlusion repair의 증거 강도

---

## 18. PPT 매핑 규칙

### 18.1 기본 primitive 매핑

- rect → PowerPoint rectangle
- rounded_rect → PowerPoint rounded rectangle
- line → PowerPoint line
- orthogonal_connector → PowerPoint connector 또는 polyline equivalent
- arrow → line/connector with arrow head
- text → PowerPoint text box

### 18.2 z-order 권장
아래 순서를 권장한다.

1. filled boxes
2. unfilled boxes / lines / connectors / arrows
3. text

### 18.3 그룹화
- 기본적으로 과한 grouping은 하지 않는다.
- 사용자가 바로 수정해야 하므로 primitive 접근성이 우선이다.

### 18.4 배경 이미지
기본 출력에서는 입력 원본 이미지를 배경으로 깔지 않는다.
디버깅 모드가 아닌 이상 pure editable output을 유지한다.

---

## 19. 생략 규칙

생략은 실패가 아니다. 아래는 정상적인 결과다.

- 아이콘 자리 공백
- OCR 실패 텍스트 공백
- box인지 확신 못 하는 contour 생략
- 가려졌지만 증거 부족한 선분 생략
- gradient 영역을 단색으로 축약하거나, 필요시 fill 자체 생략

구현은 “최대한 많이 그리기”보다 “틀리지 않게 그리기”를 우선해야 한다.

---

## 20. MVP 범위

MVP에서 우선 지원해야 할 항목은 다음과 같다.

1. rectangle
2. rounded rectangle
3. straight line
4. orthogonal connector
5. simple arrow
6. basic text box
7. conservative occlusion repair
8. representative solid fill for closed boxes
9. non-diagram omission
10. PPTX export

### 20.1 MVP에서 미뤄도 되는 것

- 복잡한 자유곡선
- 특수 도형 라이브러리 전반
- 정교한 폰트 매칭
- table structure 일반 복원
- chart/plot semantic reconstruction
- multi-slide decomposition
- 완전한 vector semantics preservation

---

## 21. 검증 기준(Definition of Correct Conversion)

다음 조건을 만족하면 올바른 변환으로 본다.

1. 결과 객체가 PowerPoint에서 개별 편집 가능하다.
2. 주요 box/line/arrow 구조가 보수적으로 재구성된다.
3. 비-다이어그램 요소는 벡터화되지 않는다.
4. 닫힌 박스만 단색 fill을 가진다.
5. gradient/shadow/texture는 구조로 오인되지 않는다.
6. 가려진 부분은 증거가 충분할 때만 이어진다.
7. 불확실한 요소는 생략된다.
8. 전체적으로 사용자의 수작업 시간이 줄어든다.

---

## 22. 테스트 케이스 권장 목록

구현체는 최소한 아래 케이스를 테스트하는 것이 권장된다.

### Case A. 단순 박스 다이어그램
- 사각형 3개
- 직선 커넥터 2개
- 라벨 3개
- 기대: 거의 전부 변환

### Case B. 텍스트에 의해 박스 테두리가 부분 가림
- 기대: box 테두리 보수적 복원

### Case C. 아이콘이 박스 안/옆에 존재
- 기대: 아이콘 생략, box/line만 유지

### Case D. gradient fill box
- 기대: 평균 단색 fill

### Case E. 열린 윤곽
- 기대: fill 없음

### Case F. non-diagram image only
- 기대: 거의 빈 출력

### Case G. ambiguity high
- 기대: 환각 구조 없이 생략 위주

---

## 23. 최종 규칙

이 문서 전체를 한 문장으로 요약하면 다음과 같다.

> **구조적 근거가 충분한 primitive만 editable PPT object로 만들고, 나머지는 과감히 비운다.**
