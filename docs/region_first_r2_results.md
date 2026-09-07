# R2 결과: 중복 제거는 유효, source-evidence 필터는 실패

2026-09-08. **R2 진단 완료 / B의 제한적 이득 / C 실패 / 제품 승인 아님**.

기존 R0의 수동 ROI 안에서 자동 검출한 후보를 고정하고 선택 단계만 바꿨다.
18개 PPTX를 실제 PowerPoint 16.0에서 렌더하고, 원본/A/B/C 비교 그림 여섯 장과
삭제 후보 overlay 및 실패 원인 mask 그림을 직접 열어 보았다.

결론은 분리해야 한다. **중복 제거 B는 실제 객체를 잃지 않고 불필요한 도형 6개를
줄였다.** 그러나 점 무늬를 걸러내는 C는 정상 객체 11개도 삭제했다. 오탐이 적다는
집계만으로 C를 승인하면 원래 목표인 유용한 부분 복원을 오히려 훼손한다.

## 1. 동결 경계

- protocol 및 입력 SHA: `7f55032`.
- 실행 코드: `1b9a70b01b696458fd397103c6e7b944130a6068`, 생성 당시 clean.
- 6개 모두 R0 `roi_cv` scene이다. R1에서 사용했던 수동 oracle 박스로 바꾸지 않았다.
- A: 전체 후보. B: 중복 관측 제거. C: B + 빈 shared-border face / 불연속 외곽 /
  scatter-like region 검사. 파라미터와 우선순위는 결과 실행 전에 고정했다.
- 모든 조건은 같은 R1 `normalize_only` 출력이다. R1 custom 연결점은 이번 개입에서 제외했다.
- 새 검출·OCR·연결 복구 없음. 남긴 객체의 경계·역할·라벨과 남긴 connector의
  owner pair·경로·방향은 원래 scene 그대로다. 사라진 owner의 선은 삭제만 하고 재결속하지 않았다.
- sample명/target ID/정답 라벨/정답 연결 쌍을 선택 규칙에 쓰지 않는다.
  scene이 운반하는 OCR 문자열은 그대로 보존하며 선택 판단에는 사용하지 않는다.
- R0/R1/Phase 15·16 동결 결과, production writer/검출기/기본값 변경 없음. holdout 미사용.

## 2. 정량 결과

각 셀은 **대상 객체 일치 / 추가 객체 / 올바른 방향 관계 일치**다.
추가 객체는 국소 annotation에서 unmatched인 도형 수이며 사람이 실제 삭제한 횟수나 시간은 아니다.

| 국소 사례 | A 전체 후보 | B 중복 제거 | C source-evidence |
|---|---:|---:|---:|
| BLIP | 5/5 · 0 · 3/3 | 5/5 · 0 · 3/3 | **0/5** · 0 · **0/3** |
| Attention | 6/6 · 10 · 0/4 | 6/6 · **4** · 0/4 | **0/6** · 0 · 0/4 |
| HEVC | 4/4 · 0 · 3/3 | 4/4 · 0 · 3/3 | 4/4 · 0 · 3/3 |
| Reasoning | 4/4 · 0 · 3/3 | 4/4 · 0 · 3/3 | 4/4 · 0 · 3/3 |
| PERCEIVE | 4/4 · 1 · 0/2 | 4/4 · 1 · 0/2 | 4/4 · 1 · 0/2 |
| Negative chart | 0/0 · 3 · 0/0 | 0/0 · 3 · 0/0 | 0/0 · **0** · 0/0 |
| 전체 | **23/23 · 14 · 9/15** | **23/23 · 8 · 9/15** | **12/23 · 1 · 6/15** |

- B는 모든 양성 사례에서 target 손실 0, 기존 맞은 관계 손실 0이다. 원래 raw connector
  15개도 모두 남았다. 이 중 Attention의 6개는 잘못되거나 정답 관계에 대응하지 않는 선이다.
- B에서 제거된 6개는 Attention의 작은 ellipse 1개, fill 4개, node와 겹친 container 1개다.
  적어도 이 사례에서는 fill/outline/ellipse가 별개의 객체가 아니라 같은 토큰의 관측이었다.
- C는 BLIP의 정상 관계 3개와 Attention의 잘못된 raw 선 6개를 삭제했다. 올바른 관계
  손실과 잘못된 관계 감소를 같은 개선으로 합산하지 않는다.
- whitespace-normalized correct label은 A/B 14/17, C 9/17이다. 어려운 텍스트를 포함한
  박스가 삭제됐다고 OCR가 좋아진 것으로 세지 않았다. 역할 오류는 세 조건 모두 0이다.

## 3. 육안 판정

![R2 Attention 원본/A/B/C](../artifacts/region-first-r2/review-v2/mixed-attention-comparison.png)

B에서는 특히 노란 토큰의 네모난 중첩 외형이 하나의 원형으로 정리됐다.
그러나 화살표 사이 가짜 박스 3개와 전체를 감싼 가짜 container 1개가 남고,
잘못 연결된 선도 남는다. **도형 수가 줄었다는 것은 확인했지만 좋은 다이어그램으로
완성됐다고 보기는 어렵다.** C는 정상 영역 전체가 빈칸이어서 명백한 실패다.

![R2 BLIP 원본/A/B/C](../artifacts/region-first-r2/review-v2/mixed-blip-comparison.png)

BLIP은 A/B의 쓸 수 있던 부분 복원이 C에서 완전히 사라졌다.
이는 불확실한 장식을 보수적으로 생략한 사례가 아니라, 확실한 구조를 오판한 사례다.

HEVC와 Reasoning은 A/B/C가 시각적으로 동등하다. PERCEIVE의 OCR·채움 오류,
추가 fill 조각 및 꺾인 선 2개 누락도 그대로다. Negative chart만 보면 C의 빈칸은
맞지만, 두 양성 그림을 파괴한 대가를 무시할 수 없다.

## 4. 실패 원인을 그림으로 재확인

실행 후 수치를 보고 임계값을 조정하지 않았다. 대신 기존 결과의 색상 마스크를
그대로 시각화하고, component 개수/면적이 run1에 기록된 값과 일치하는지 assert했다.
이는 실패 설명용 진단이지 새 실험 조건이나 보정 실행이 아니다.

### 4.1 글자와 산점도 점을 같은 근거로 셌다

![BLIP의 글자 가장자리가 점 무늬로 집계됨](../artifacts/region-first-r2/rejection-inspection-v1/mixed-blip-mask.png)

BLIP 첫 라벨의 작은 유색 component는 **113개, 내부 면적 8.306%**다.
직접 보니 plot 점이 아니라 글자 윤곽과 색 번짐을 따라간다. 이 사례의 정상 박스
다섯 개는 각각 scatter로 오인돼 삭제됐다. 무채색 글자라고 가정한 간단한 합성 양성
테스트만으로는 실제 래스터 글자 가장자리의 색상 분절을 방어하지 못했다.

### 4.2 부모의 약한 판정을 자식 전체에 전파했다

![Attention의 빨간 제목이 점 무늬로 집계됨](../artifacts/region-first-r2/rejection-inspection-v1/mixed-attention-mask.png)

Attention의 가짜 바깥 container에서 **22개, 4.154%**를 셌는데 실제로는 빨간 제목이다.
이 부모 판정이 containment 규칙을 통해 안쪽 모든 후보에 전파됐다. 토큰들은 각자
작은 유색 component가 **0개**인데도 모두 삭제됐다. 구조적 containment 자체도 오탐일
수 있으므로, 부모 후보의 약한 의미 판정으로 독립적인 자식 기하 증거를 지워서는 안 된다.

Negative 오른쪽 plot의 **151개, 6.413%**는 실제 산점도 점이다. 개수와 면적만으로는
유색 글자·글자 가장자리와 구별되지 않는다는 반례가 확보됐다. 숫자 컷오프를 이 여섯
그림에 맞춰 옮기는 방식으로 해결됐다고 주장하지 않는다.

### 4.3 다른 규칙의 효과까지 한꺼번에 승인할 수 없다

C는 scatter rejection이 먼저 적용되므로 Attention의 blank-face/envelope 검사 기여를
분리해 측정하지 못했다. 기록된 feature상 가짜 face 2개는 내부 uniform 0.9785/0.9798로
사전 임계값 0.985 미만이고, 나머지 1개는 1.0이었다. 따라서 scatter만 끄면 가짜 박스가
모두 해결될 것이라고도 말할 수 없다. 별도 ablation을 사후 성공 조건으로 끼워 넣지 않았다.

## 5. 다음 방향

**B를 후속 연구의 제한된 비교 기준으로 유지하고 C는 승격하지 않는다.** B도 한 사례에서
이득을 보인 개발 결과이므로 production의 일반 성능이나 사람시간 절약으로 해석하지 않는다.

다음 R2.1을 진행한다면 먼저 다음 경계를 독립적으로 사전 등록해야 한다.

1. blank face, discontinuous envelope, texture rejection을 서로 다른 arm으로 분해한다.
2. 부모 rejection을 자식 전체에 전파하는 규칙을 제거하고, 각 자식의 독립 경계 증거를 보존한다.
3. 색상 component 수가 아니라 글자 행/획과 분산 점의 공간적 차이를 검증한다.
   유색 글자와 안티앨리어싱된 글자, 실제 scatter, 중첩 다이어그램을 동등한 반례로 넣는다.
4. B에서도 남은 잘못된 연결을 개선하려면 선택 후 관측 stroke 기반의 연결 복구가 별도로
   필요하다. 이번처럼 관계를 고정한 R2에서 연결 recall 상승을 기대해서는 안 된다.

R2.1이나 관계 재추출은 아직 실행하지 않았다. R2의 실패 출력/임계값을 덮어쓰지 않는다.

## 6. 검증·재현

- 18개 native PPTX 및 PowerPoint 렌더 SHA 검증. 남은 scene primitive/connector가
  원본의 정확한 부분집합인지 확인했다. PPTX ID/라벨/owner binding 유지, raster 0개.
- 새 합성 반례 테스트 8개 통과. 전체 **237 passed, 9 warnings**.
  이것은 코드 동작 검사이며 C의 실제 이미지 실패를 상쇄하지 않는다.
- [protocol](region_first_r2_protocol.md), [입력 SHA](../benchmarks/region_first_r2_inputs_v1.json),
  [육안 기록](../benchmarks/region_first_r2_visual_review_v1.json),
  [최종 ledger](../benchmarks/region_first_r2_evidence_v1.json).
- 원본/scene/PPTX/PNG는 ignored local artifacts이며 tracked ledger에 경로와 SHA를 기록했다.
  다른 checkout에서 재현하려면 해당 입력 파일이 필요하다. 원격 push는 하지 않았다.

```powershell
rtk proxy .venv/Scripts/python.exe tools/run_candidate_selection.py --output-dir artifacts/region-first-r2/reproduction-new
rtk proxy pwsh -NoProfile -Command 'if (Get-Process POWERPNT -ErrorAction SilentlyContinue) { throw "Existing PowerPoint process" }; & ./tools/render_pptx_via_powerpoint.ps1 -InputPath artifacts/region-first-r2/reproduction-new -OutputDirectory artifacts/region-first-r2/reproduction-new-renders'
rtk proxy .venv/Scripts/python.exe tools/review_candidate_selection.py --run-dir artifacts/region-first-r2/reproduction-new --render-dir artifacts/region-first-r2/reproduction-new-renders --output-dir artifacts/region-first-r2/reproduction-new-review
rtk proxy .venv/Scripts/python.exe -m pytest -q
```

출력 폴더는 항상 새 경로다. 재현 결과의 육안 검토를 새로 해야 하므로 위 명령은 이번
육안 기록을 자동 이식하지 않는다. 실제 PowerPoint 기존 사용자 세션이 있으면 먼저 멈춘다.
