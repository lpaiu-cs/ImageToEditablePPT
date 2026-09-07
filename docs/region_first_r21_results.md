# R2.1 결과: 정상 객체를 보존하면서 오탐 감소

2026-09-08. **개발 표본에서 후보 선택 개선 / 전체 출력 품질 승인 아님**.

결합 조건은 정상 객체 **23/23개**, 기존 올바른 관계 **9/15개**를 유지하며
추가 객체를 **8→3개**로 줄였다. R2에서 두 정상 그림을 지웠던 실패는 이번 결합
조건에서 재발하지 않았다. 실제 PowerPoint 렌더에서도 BLIP 보존, 차트 오탐 삭제,
Attention 가짜 외곽·빈 박스 일부 삭제를 직접 확인했다.

그러나 Attention은 아직 올바른 연결 **0/4**, PERCEIVE는 **0/2**다.
객체 선택 개선을 완성된 다이어그램이나 사람시간 절약으로 과장하지 않는다.

## 1. 실험 경계

- 사전 protocol `54ca336`; 실행 코드 `86fbefa21af10f4f165840efad15c462cabb942a`, 당시 clean.
- R2와 동일한 6개 consumed development ROI 입력과 정답 SHA. oracle 박스로 바꾸지 않았다.
- baseline은 R2 B의 중복 제거 그대로다. 여섯 baseline scene SHA가 R2 B와 동일한지 검증했다.
- 새 구현은 별도 `research/local_select.py`다. R2 selector·실패 결과·임계값은 수정하지 않았다.
- face, envelope, local scatter, guarded scatter, combined를 독립 조건으로 실행했다.
- 모든 조건에서 부모 rejection의 자식 전파를 없앴다. 자식도 자신의 픽셀 근거로만 판단한다.
- 같은 중복 제거 후보 집합에서 각 규칙을 계산하므로 결합 조건에도 연쇄 재판정이 없다.
- 검출/OCR/연결 재실행 및 sample별 규칙 없음. 남긴 객체·라벨·연결 primitive는 원래 scene의
  정확한 부분집합이다. 삭제 객체의 incident 선은 삭제만 하고 다른 객체로 바꾸지 않았다.
- 출력은 동일한 768px normalize_only writer다. R1 custom-site와 reroute 개선 실험은 아니다.

## 2. 독립 조건 결과

추가 객체는 국소 정답에 대응하지 않는 객체 수이며, 실제 사람이 수행한 삭제 횟수나 초가 아니다.

| 조건 | 대상 객체 | 추가 객체 | 올바른 관계 | raw connector |
|---|---:|---:|---:|---:|
| baseline: R2 B | 23/23 | 8 | 9/15 | 15 |
| face_only | 23/23 | 7 | 9/15 | 13 |
| envelope_only | 23/23 | 7 | 9/15 | 15 |
| local_scatter | **18/23** | 4 | **6/15** | 12 |
| guarded_scatter | 23/23 | 5 | 9/15 | 15 |
| **combined** | **23/23** | **3** | **9/15** | **13** |

local_scatter는 부모 전파만 제거한 조건이다. Attention의 자식은 보존하지만 BLIP의
다섯 박스는 각각 오판되므로 여전히 실패한다. 즉, **전파 제거만으로 충분하지 않다.**

결합 조건에서 제거한 추가 객체 5개는 다음과 같다.

- Attention의 가장 넓은 빈 face 1개: face 규칙.
- Attention의 가짜 전체 외곽 1개: envelope 규칙.
- Negative chart의 프레임 2개와 빨간 조각 1개: 각자의 guarded scatter 근거.

남은 추가 객체 3개는 Attention의 작은 빈 face 2개와 PERCEIVE의 fill 조각 1개다.
원래 R2 A의 추가 객체 14개와 비교하면 중복 제거 6개 + 이번 추가 제거 5개지만,
이번 실험의 직접 대조군은 **R2 B의 8개**다.

## 3. 실제 그림에서 확인한 것

![Attention 독립 기하 조건](../artifacts/region-first-r21/review-v2/mixed-attention-geometry.png)

![Attention 결합 결과](../artifacts/region-first-r21/review-v2/mixed-attention-combined.png)

가짜 외곽이 사라지고 오른쪽 빈 face가 제거돼 불필요한 구조가 줄었다.
하지만 남은 빈 face 두 개에 연결이 잘못 붙어 있어 아직 좋은 결과가 아니다.
오른쪽 보라색 토큰의 잘못된 연결이 사라졌다고 올바른 연결이 복구된 것도 아니다.
삭제된 raw connector 두 개는 원래 오답이었고, 맞는 관계의 개수는 변하지 않았다.

![BLIP 기존 규칙과 보호 조건](../artifacts/region-first-r21/review-v2/mixed-blip-texture.png)

BLIP의 다섯 박스와 세 연결은 guarded/combined에서 유지된다. local_scatter는 다시
빈 결과를 내므로, R2 실패를 숨기지 않고 원인 개입의 효과를 대조할 수 있다.

![Negative chart 결합 결과](../artifacts/region-first-r21/review-v2/negative-plots-combined.png)

차트의 오탐 세 개는 사라졌다. 이것은 **유색 산점도 개발 사례 하나**의 결과이며,
흑백 plot, 조밀한 scatter, 사진, 로고 전반을 판별했다고 해석하지 않는다.

HEVC·Reasoning·PERCEIVE의 모든 조건도 비교했다. 앞의 두 사례는 기존 구조가
그대로이며, PERCEIVE의 꺾인 선 누락·OCR·채움 문제와 추가 조각은 해결되지 않았다.

## 4. 왜 이번에는 글자를 보존했나

작은 유색 component 수만 세는 기존 규칙 뒤에 크기·종횡비·채움 비율과 2차원 분포를
검사했다. 최소 dot 20개, 작은 component 중 dot 비율 65%, 충분한 가로·세로 분포,
두 개의 수평 bin에 70% 이상 몰리지 않는 조건을 **실행 전에** 고정했다.

- BLIP 첫 라벨: 작은 유색 component 113개 중 dot 형태는 17개(15.0%).
  나머지 라벨도 dot 비율 11.8~26.3%로 산점도 판정을 통과하지 않는다.
- Attention 제목을 포함한 외곽: dot 형태 19개, 세로 분포 0.024,
  상위 두 행 bin 비율 1.0. 제목의 한 줄 배치를 산점도와 구분했다.
- 실제 negative plot 세 후보: dot 비율 82.9~93.8%, 세로 분포 0.515~0.900,
  상위 두 행 bin 비율 0.377~0.621로 조건을 통과했다.

이 설명은 기록된 feature에 근거한다. 이 표본에 맞춰 결과 후 임계값을 바꾸거나
OCR 문자열을 읽어 예외 처리하지 않았다. 다만 같은 개발 그림을 반복 사용한 만큼
일반화는 별도 검증이 필요하다. dot 모양 글자, 여러 행의 유색 문자, 가려진 정상 테두리,
작은 nested diagram 등에서는 여전히 오판할 수 있다.

## 5. 판정 및 다음 병목

결합 조건은 사전 정의한 개발 gate(추가 객체 감소, 모든 양성 target 보존,
기존 correct edge 손실 없음)를 통과한다. **후속 연구의 후보 선택 기준으로 동결하되,
production 기본값으로 승격하지 않는다.** R0/R1/R2/Phase 15·16의 판정은 그대로다.

지금 남은 큰 병목은 **관측된 선의 경로와 endpoint owner 복구**다.
R3에서는 선택 객체를 고정한 조건과 별도 수동-box 진단 조건을 분리하고, 원본 stroke
근거로 직선/꺾인 경로를 추적해야 한다. 가짜 face가 경로를 가로채는 문제와 실제 꺾인
선의 누락을 독립적으로 측정할 것. R1 emitter 효과까지 섞어서 검출 성능으로 세지 않는다.
작은 face 두 개를 없애려고 이번 uniform threshold를 사후 완화하는 것은 하지 않는다.

R3는 아직 실행하지 않았다. 사람 편집시간은 측정하지 않았고 기존 calibration 경계도 유지한다.

## 6. 검증과 재현

- 실제 PowerPoint 16.0으로 **36개 PPTX** 렌더.
- geometry/texture/combined 비교 **18장** 전부 직접 열어 확인. 선택 중간 overlay도 확인.
- 모든 source/scene/PPTX/PNG SHA 검증. 남은 native ID·라벨·owner binding 보존, raster 0개,
  정규화 bbox 최대 오차 0.001px 미만.
- 추가 합성 검사: 유색 제목, 안티앨리어싱된 글자와 유색 채움, 진짜 scatter 안의 독립 child,
  빈 node 및 라벨/ID 변경 불변성. 기존 R2의 shared-face 등 테스트도 재실행했다.
- **241 passed, 9 warnings**. 합성 텍스트 렌더 테스트는 이번 Windows Arial 환경에서 검증했다.
- [protocol](region_first_r21_protocol.md), [공유 입력 manifest](../benchmarks/region_first_r2_inputs_v1.json),
  [육안 기록](../benchmarks/region_first_r21_visual_review_v1.json),
  [최종 evidence](../benchmarks/region_first_r21_evidence_v1.json).
- 원본/생성물은 ignored local artifacts이고 tracked ledger가 SHA를 결속한다. 원격 push 없음.

```powershell
rtk proxy .venv/Scripts/python.exe tools/run_local_selection.py --output-dir artifacts/region-first-r21/reproduction-new
rtk proxy pwsh -NoProfile -Command 'if (Get-Process POWERPNT -ErrorAction SilentlyContinue) { throw "Existing PowerPoint process" }; & ./tools/render_pptx_via_powerpoint.ps1 -InputPath artifacts/region-first-r21/reproduction-new -OutputDirectory artifacts/region-first-r21/reproduction-new-renders'
rtk proxy .venv/Scripts/python.exe tools/review_local_selection.py --run-dir artifacts/region-first-r21/reproduction-new --render-dir artifacts/region-first-r21/reproduction-new-renders --output-dir artifacts/region-first-r21/reproduction-new-review
rtk proxy .venv/Scripts/python.exe -m pytest -q
```

출력은 새 폴더여야 한다. 재현 그림에는 새 육안 검토가 필요하므로 기존 visual review를 자동
이식하지 않는다. PowerPoint의 기존 사용자 프로세스가 있으면 렌더 실행을 중단한다.
