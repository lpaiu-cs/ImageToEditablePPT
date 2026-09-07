# Region-first R0 결과: 영역 지정은 도움이 되지만 충분하지 않다

2026-09-08. 상태: **진단 라운드 완료 / 제품 승인 아님**.

새 연구선 `codex/region-first-diagnostics`에서 사전 고정한 6개 개발 표본의
23개 국소 객체와 15개 방향 관계를 대상으로 3개 조건, 총 18개 PPTX를 생성했다.
PowerPoint 16.0에서 모두 렌더했고, 원본 ROI와 세 조건을 나란히 놓은 비교 그림
6개를 직접 열어 육안으로 확인했다. 동결 Phase 15/16의 정답·모델·기본 실행 경로는 바꾸지 않았다.

## 1. 브랜치와 실험 경계

- 이전 로컬 브랜치 `claude/charming-euler-d8be44`는 `archive/phase16-baseline`으로 이름을 바꿨다.
- 동일 tip `bf86a84b7d76eda839c03a12d748fb396a2f2d2b`를 annotated tag `archive/phase16-baseline-bf86a84`에도 보존했다.
- `main`은 `9fe246b`에서 원격 `fe2fc99`로 fast-forward했다. unique commit 손실 없음.
- 기존 원격 브랜치는 PR #6이 OPEN이고 로컬 동결 커밋 4개가 아직 원격에 없어서 삭제하지 않았다.
- 기존 detached baseline worktree도 재현 근거이므로 보존했다. 원격 push, PR 변경, 원격 브랜치 삭제 없음.
- protocol/대상 고정: `8a6ce5a`; 실제 실행 코드: `07e83b172f0ab444a8437783de5bcadcb73c4297`, 실행 당시 clean.
- 기존 Phase 16 사람시간 calibration/NO-GO는 유지한다. 사용자 승인에 따른 별도 진단이지 기존 승인 조건의 사후 완화가 아니다.

## 2. 대조 조건 — 자동 성능과 수동 입력을 혼동하지 않는다

| 조건 | 제공 정보 | 자동으로 수행한 것 |
|---|---|---|
| A `full_cv` | 원본 RGB | native 해상도 CV 객체/역할, 연결, 박스 내부 OCR, PPTX |
| B `roi_cv` | 원본 + 수동 coarse ROI | ROI 안의 동일 CV 객체/역할, 연결, OCR, PPTX |
| C `oracle_boxes` | 원본 + ROI + 수동 박스 경계/역할 | 연결, OCR, PPTX |

C의 23/23 객체는 제공한 입력이므로 자동 검출 성능이 아니다. C에는 정답 라벨,
연결 쌍, 경로를 제공하지 않았다. 수동 박스는 원본 육안에 기반한 근사 경계이며
픽셀 단위 정답이 아니므로 OCR의 단조로운 상한을 보장하지 않는다.

A는 기존 ML baseline과 다르다. frozen CV helper를 native 해상도에서 사용하고
ML detector와 global gate는 사용하지 않는다. B-A는 영역 개입, C-B는 박스/역할 개입의
진단이다. 이 결과로 기존 end-to-end ML 모델보다 성능이 향상됐다고 주장하지 않는다.

전체 그림의 일부만 annotation했다. ROI 밖 출력은 지정된 제외 영역을 침범한 경우를
제외하면 미평가다. p063/p040의 잘못된 whole-scene non_diagram 판정은 새 국소 정답에서
바로잡았지만 기존 frozen annotation은 보존했다. 다른 62개 annotation의 재감사는 하지 않았다.

## 3. 결과

표의 값은 `대상 객체 일치 / 방향 있는 endpoint-pair 일치`다.

| 지정 영역 | A 전체 CV | B 수동 ROI + CV | C 수동 박스/역할 |
|---|---:|---:|---:|
| p063 BLIP 하단 두 도식 | 5/5 · 3/3 | 5/5 · 3/3 | 5/5 · 3/3 |
| p040 Attention + query tokens | 2/6 · 0/4 | 6/6 · 0/4 | 6/6 · 4/4 |
| p008 HEVC 첫 네 박스 | 4/4 · 3/3 | 4/4 · 3/3 | 4/4 · 3/3 |
| p034 Logical Reasoning 첫 행 | 3/4 · 1/3 | 4/4 · 3/3 | 4/4 · 3/3 |
| input.png PERCEIVE | 4/4 · 0/2 | 4/4 · 0/2 | 4/4 · 0/2 |
| 합계, 위 5개 국소 양성 | 18/23 · 7/15 | 23/23 · 9/15 | 제공 23/23 · 13/15 |

이 합계만 보면 B가 좋아 보이지만, 실제로는 중요한 실패가 남는다.

- p063: A의 병리사진 타일 오탐 4개가 B에서 사라졌다. 지정 도식의 5개 박스와
  3개 연결은 유지됐다. 국소 부분 추출의 유효한 개발 사례다.
- p040: B에는 정답 객체 외에 **10개 객체가 더 생겼다**. 세로 화살표와 두 박스
  테두리가 둘러싼 빈 사각 영역 3개가 node가 됐고, token의 fill/ellipse/outline이
  중복되며 전체를 감싼 가짜 container도 생겼다. 이것은 글자 인식만의 문제가 아니다.
  닫힌 영상 영역과 의미 있는 도형을 동일시한 문제가 직접 드러난다.
- p034: B는 첫 행의 4개 박스·3개 연결을 복구하고 국소 추가 객체를 제거했다.
- PERCEIVE: B는 추가 객체 1개를 남기고, C도 두 꺾인 경로를 모두 놓쳤다.
  현재 direct-gap 연결기는 이 경로를 지원하지 않는다. 박스 검출 개선만으로 해결되지 않는다.
- negative p002: A/B는 차트 프레임과 빨간 영역을 **3개 도형으로 오인**했다.
  C의 빈 결과는 빈 정답 박스를 제공했기 때문이므로 자동 reject 성공으로 세지 않는다.

## 4. 수치가 통과해도 육안으로 통과하지 못한 부분

### 연결 관계와 PPT 연결점은 서로 다른 검증 대상이다

p040의 C는 원본 픽셀에서 4개 endpoint-pair를 맞히고 OOXML에도 8개 endpoint가
결속돼 있다. 그러나 네 화살표가 도착 박스의 서로 다른 위치 대신 같은 side-center로
이동하면서 elbow들이 겹친다. 원래 위를 향하던 화살표 끝도 가로로 겹쳐 보여 읽기 어렵다.
**4/4 관계, 8/8 native binding만으로 편집 가능한 좋은 결과라고 판정할 수 없다.**

![Attention 비교](../artifacts/region-first-r0/review-v1/mixed-attention-comparison.png)

### OCR 내용과 글자 크기도 분리해야 한다

- whitespace-normalized label exact count: A 13/17, B 14/17, C 12/17.
- `Obtain all PU units`가 `all PU Obtain units`, `Sensory System`이 `System Sensory`로
  뒤집힌 사례가 있다. 수동 박스 C에서는 `Video S Stream`, `Boundary R Redaction`도 나타났다.
- R0는 원본 해상도로 도형을 만들고 기존 writer의 고정 point-size 제한을 그대로 쓴다.
  따라서 큰 물리적 슬라이드에서 글자와 선이 상대적으로 지나치게 작고 가늘다.
  이 출력은 육안상 부족하다. 이는 R0의 native-to-slide mapping 문제도 포함하므로,
  기존 768px production 출력의 회귀라고 해석하지 않는다.
- container 제목은 R0에서 평가/복구하지 않았다. PERCEIVE 제목 누락은 명시적 실험 범위의 한계다.

![PERCEIVE 비교](../artifacts/region-first-r0/review-v1/cogbot-perceive-comparison.png)

## 5. 실제 PowerPoint 편집 동작

BLIP B의 native shape를 COM으로 12pt 옮겨 확인했다.

- source shape 이동: 12pt.
- 결속 connector의 left 좌표 이동: 12pt. 별도 RerouteConnections 호출 없음.
- 반대쪽 shape 위치는 그대로이며 양 끝의 binding ID 유지.
- 같은 shape의 text frame을 임시 문구로 수정할 수 있었음.
- 원본 PPTX는 저장하지 않았고 SHA가 변하지 않았음.

이것은 단순 연결 1개의 자동 동작 검사이며, 사람 편집시간이나 복잡한 fan-in의
편집성에 대한 증거는 아니다. 18개 PPTX 모두 삽입 raster image는 0개였다.

## 6. 이번 결과에 따른 방향 결정

R0의 A/B/C를 다시 튜닝해서 결과를 개선하지 않는다. 조건 D의 mixed-role 변경도
이번에는 실행하지 않는다. 실제로 드러난 핵심 실패는 역할 분리 하나로 해결되지 않는다.

다음 연구 순서는 다음처럼 좁힌다.

1. **native emit 계약부터 작은 독립 검증**: 입력 해상도와 PPT 물리 크기를 분리하고,
   한 박스의 서로 다른 attachment 좌표를 유지하면서 실제 이동/크기 변경에도 결속되는지
   확인한다. 검출 없이 source-observed scene을 고정한 대조군에서 시험한다.
   미결속으로 바꿔 외형만 맞추는 결과는 같은 성공으로 세지 않는다.
2. **객체 후보 선택**: 단순 closed contour가 아니라 node/container/raster/빈 face를
   구별한다. fill·outline·ellipse는 서로 다른 객체가 아닌 동일 객체의 관측일 수 있다.
   ROI는 후보의 문맥이지 그 안의 모든 윤곽을 emit하라는 허가가 아니다.
3. **실제 stroke 경로**: PERCEIVE의 관측된 꺾인 선처럼 endpoint 사이의 경로를
   추적하되, 선이 없으면 추가하지 않는다. 박스 실패와 관계 실패를 독립적으로 보존한다.
4. **OCR reading order와 box geometry**를 분리한다. 정답 문자열을 복사하거나 의미적
   철자 보정으로 오류를 가리지 않는다. 판독 불확실성은 별도로 남긴다.

ROI 검출 모델을 더 학습하거나 큰 MEG 구현을 통째로 시작할 근거는 아직 부족하다.
특히 지금 상태에서 객체 recall만 끌어올리는 것은 가짜 객체와 잘못 읽히는 연결을
함께 늘릴 수 있다. 새 독립 holdout과 실제 사람 시간 비교는 제품 후보가 나온 뒤에 수행한다.

## 7. 재현 및 근거

```powershell
rtk proxy .venv/Scripts/python.exe -m pytest -q
rtk proxy .venv/Scripts/python.exe tools/run_region_first_diagnostics.py --output-dir artifacts/region-first-r0/reproduction-new
rtk proxy pwsh -NoProfile -File tools/render_pptx_via_powerpoint.ps1 -InputPath artifacts/region-first-r0/reproduction-new -OutputDirectory artifacts/region-first-r0/reproduction-new-renders
```

- 모든 출력 폴더는 새 경로여야 한다. 덮어쓰기를 허용하지 않는다.
- 외부 이미지와 모델은 기존과 같이 ignored local artifacts다. source SHA 불일치/부재 시
  runner는 전체 preflight에서 멈춘다. 필요한 파일은 새 sample manifest와 기존 Phase 16 dev manifest에 provenance가 있다.
- Windows PowerShell 5.1 호출에서는 Get-FileHash module을 찾지 못해 첫 렌더 후 종료했다.
  부분 파일은 first-renders에 보존하고, bundled pwsh로 18개 전부 별도 폴더에 정상 렌더했다.
- 현재 PowerPoint가 사용자 작업을 열고 있다면 렌더/COM probe를 동시에 실행하지 않는다.
  native movement probe는 기존 PowerPoint process가 있으면 거부한다.
- 전체 테스트: **221 passed, 9 warnings**. 테스트 통과는 시각적 승인과 별개다.
- [사전 protocol](region_first_r0_protocol.md), [새 국소 정답](../benchmarks/region_first_r0_v1.json),
  [검토 완료 evidence ledger](../benchmarks/region_first_r0_evidence_v1.json).
- 상세 scene/metric/PPTX: `artifacts/region-first-r0/run1/`.
- 실제 PowerPoint PNG와 render SHA: `artifacts/region-first-r0/run1-renders/`.
- 전체 18개 출력의 국소 A/B/C 육안 비교: `artifacts/region-first-r0/review-v1/`.

최종 판정: **영역 지정의 국소 이득은 확인했으나, 자동 변환 성능이나 사용자 시간 절약은 승인하지 않는다.**
