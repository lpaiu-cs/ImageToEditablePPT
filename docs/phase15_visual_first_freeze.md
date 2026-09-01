# Phase 15. Visual-first reconstruction freeze

동결일: 2026-09-02

결론: **후보 구현으로 동결한다. 제품 승인 상태는 NO-GO이며 canonical 모델로 승격하지 않는다.**

Phase 15는 원본 이미지, 검출 중간 결과, 실제 PowerPoint 재렌더를 반복해서 육안 비교하며 source-pixel 기반 geometry와 connector 경계를 조정한 개발 라운드다. 단순·중간 복잡도 도식에서는 편집 가능한 보수적 부분복원이 가능해졌지만, 복잡한 실제 도식에서는 핵심 구조·계층·관계·텍스트를 다시 그려야 한다. 따라서 이 결과를 실사용 가능 상태로 해석하지 않는다.

이 문서를 포함하는 Git 커밋을 Phase 15 코드 경계로 삼는다. 현재 표본과 이미 소비한 holdout을 이용한 추가 튜닝은 여기서 중단한다.

## 동결된 동작 경계

- ML detector bbox를 그대로 출력하지 않고, 원본 픽셀에서 실제 경계 또는 균일한 닫힌 영역이 확인된 geometry를 우선한다.
- rectangle, rounded rectangle, 큰 ellipse, header divider가 확인된 titled panel을 native PowerPoint 도형으로 출력한다.
- 전역 최소 면적은 이미지의 0.6%이며, 반복 구조가 있는 titled panel 내부의 작고 넓은 box는 0.25%까지 허용한다.
- connector는 원본에서 직접 확인되는 수평·수직 선분만 복원한다. 곡선, 점선, 자유 경로와 증거가 약한 연결은 생략한다.
- container connector는 다른 container뿐 아니라 내부 node를 가로지르는 경우도 차단한다.
- source에서 확인되지만 panel 중심에서 벗어난 endpoint는 위치를 보존하기 위해 도형에 결속하지 않는다.
- ellipse는 rectangle 근사가 아니라 native ellipse로 출력한다.
- 텍스트는 가장 작은 node에 우선 귀속하고, titled panel은 실제 header 영역의 텍스트만 소유한다.
- OCR은 같은 줄의 x 순서로 병합하고, 겹치는 중복·오염된 부분 문자열과 `Legend:`를 제거하며, 도형 내부 안전 영역에 맞춰 글꼴을 제한한다.
- OOD gate가 활성화된 경우 `connector / (node + container) >= 0.20`인 결과만 구조적으로 유용한 것으로 인정한다. `--no-gate`는 이 검사를 명시적으로 우회한다.

## 육안 판정

| 표본군 | 관측 결과 | 판정 |
|---|---|---|
| 공개 diagram 5종 | three-phase `3 node / 2 connector`, chat `7 / 1 container / 6`, DDSP `5 / 6 / 5`, HAR `18 / 4 / 12`, CTI `16 / 0 / 6`. 핵심 골격 일부가 editable object로 남는다. | 개발 표본에서 유용한 보수적 부분복원 |
| 저장소 `input.png` | `16 node / 3 container / 6 connector`가 출력되지만 RETRIEVE와 Memory 계층이 크게 누락되고, 잘못된 대형 영역·텍스트 손상·관계 단절이 남는다. | **NO-GO** |
| 개발 non-diagram 5종 | 모두 empty. 항공사진 오탐도 최종 gate에서 blank PPTX가 됐다. | 개발 표본 통과 |
| 과거 holdout non-diagram 9종 | 현재 모두 empty다. | 이미 본 자료이므로 승인 증거 아님 |
| 과거 holdout diagram 5종 | 육안으로 유용한 3종은 유지되고, 고립 객체만 남던 2종은 empty다. | 이미 본 자료이므로 승인 증거 아님 |

공개 5종의 결과는 범위가 좁은 개발 증거다. 성공 개수나 객체 개수만으로 제품 승인을 주장하지 않는다.

## 현재 문제점

### 1. 복잡한 혼합 도식의 구조 recall과 계층 복원이 부족하다

가장 큰 차단 요인이다. `input.png`에서는 PERCEIVE 일부와 THINK 일부만 조각처럼 남고, RETRIEVE와 Memory 영역의 핵심 box·중첩 계층·관계가 대량 누락된다. 반대로 좌측에는 실제 의미 단위와 맞지 않는 큰 영역이 생성된다. 사용자는 빠진 부분을 새로 그리고 잘못된 부분을 지워야 하므로 재작도량이 충분히 줄지 않는다.

현재 source-pixel confirmation은 깨끗한 닫힌 윤곽에는 강하지만, gradient 배경, 그림자, 아이콘, 텍스트와 교차하는 얇은 경계, 중첩 panel이 섞이면 의미 단위를 안정적으로 분리하지 못한다.

### 2. connector topology가 직접 축 선분에 한정된다

직선의 일부는 정확하고 편집 가능하게 남지만, elbow의 전체 경로, 여러 구간으로 분절된 선, 곡선, 점선, 가려진 connector는 대부분 생략된다. 그 결과 원본의 흐름과 방향성이 끊기며, 구조 box가 남아도 사용자가 관계를 다시 그려야 한다.

위치 보존을 위해 일부 off-center panel endpoint를 의도적으로 unbound로 내보내므로, 해당 connector는 PowerPoint에서 도형 이동을 자동 추종하지 않는 편집성 손실도 있다.

### 3. OCR 인식 자체가 불안정하다

현재 후처리는 중복, 순서, 소유권, 글꼴 넘침을 줄이지만 잘못 읽힌 문자를 복구하지는 못한다. 복잡 표본에서 단어 누락, 잘못된 문자열, 여러 줄의 잘못된 결합이 남는다. geometry가 맞더라도 label을 다시 입력해야 하므로 사용자 시간 절약이 제한된다.

### 4. 구조 유용성 gate가 개발 표본에 맞춘 휴리스틱이다

비도식 오탐을 막기 위해 추가한 `0.20` 비율은 현재 관측한 항공사진과 무용한 고립-object 결과에는 효과가 있었다. 그러나 연결이 적은 정당한 diagram도 거절할 수 있고, 연결 수만 맞춘 잘못된 diagram은 통과할 수 있다. 의미적 구조 정확도를 측정하는 gate는 아니다.

### 5. 독립 승인 증거가 없다

공개 표본, 저장소 입력, 기존 holdout은 모두 개발 과정에서 반복 관측됐다. 따라서 현재 `5/5`, `9/9`, `3/5` 같은 결과는 회귀·개발 증거일 뿐 confirmatory evidence가 아니다. 실제 사람의 PowerPoint 수정 시간 또는 독립적인 재작도량도 아직 측정하지 않았다.

### 6. clean checkout 재현과 배포가 완결되지 않았다

candidate bundle, checkpoint, 외부 benchmark 이미지, PowerPoint 재렌더 산출물은 로컬 ignored artifact다. 저장소만 checkout해서는 동일 실험을 재현할 수 없고, candidate는 `--allow-candidate-bundle`을 명시해야만 실행된다. canonical bundle은 없다.

## 동결 규칙과 다음 실험의 조건

1. 현재 공개 표본, `input.png`, 과거 holdout을 대상으로 threshold나 예외 규칙을 더 맞추지 않는다.
2. 후속 작업은 Phase 16처럼 별도 이름과 가설을 가진 새 실험으로 시작한다.
3. 먼저 새 독립 visual holdout과 판정 규칙을 동결한다.
4. 객체 개수보다 원본 대비 남은 수작업을 본다. 최소한 구조 추가, 잘못된 객체 삭제, connector 재작도, 텍스트 재입력 부담을 분리한다.
5. 복잡 계층/geometry, topology, OCR을 한 관문으로 섞지 않고 각각의 실패 원인과 개선 효과를 구분한다.
6. 새 holdout을 본 뒤에는 같은 라운드에서 rescue tuning하지 않는다.

## 재현 및 검증

후보 bundle을 로컬에 보유한 개발 환경의 대표 변환 명령:

```powershell
.venv\Scripts\python.exe tools\convert_to_pptx.py <inputs> -o <output-dir> --bundle workbench-ml\model_bundle.candidate.json --allow-candidate-bundle
```

코드 회귀 검증:

```powershell
.venv\Scripts\python.exe -m pytest -q
git diff --check
```

동결 직전 결과: `195 passed, 9 warnings in 13.42s`, `git diff --check` 통과. 경고는 Lightning의 pytree deprecation과 smoke-test dataloader worker 권고이며 실패는 아니다.

로컬 육안 증거의 대표 경로:

- `artifacts/visual-first/production-v12/public-ddsp-overview.png`
- `artifacts/visual-first/production-v12/public-ddsp-overview.pptx`
- `artifacts/visual-first/boundary-v3/input.png`
- `artifacts/visual-first/boundary-v3/input.pptx`

이 산출물은 재현 증거를 위한 로컬 파일이며 Git 동결 경계에는 포함하지 않는다.
