# R1 결과: 출력 병목 일부 해결, native reroute 스트레스 실패

2026-09-08. **진단 완료 / 제한된 출력 개선 / 제품 승인 아님**.

R0의 검출·OCR·관계를 고정하고 PPT 출력만 바꿨다. 여섯 사례의 신규 PPTX 12개를
PowerPoint 16.0에서 렌더하고 원본/A/B/C 비교 그림 여섯 장을 직접 열어 보았다.
글자 가독성과 Attention의 네 개 화살표 분리가 실제로 좋아졌다.
그러나 명시적 `RerouteConnections`는 관측된 연결점 위치를 보존하지 않았다.
H2 전체를 통과했다고 판정하지 않는다.

## 1. 무엇을 바꿨고 무엇을 고정했나

- 사전 protocol/입력 SHA 동결: `fc4fd85`.
- 생성 코드: `3a0e6e4`. 12개 출력 생성 당시 working tree clean.
- A는 R0 원본 PPTX/렌더 그대로다.
- B는 source 좌표를 폭 768px, 8인치 슬라이드로 정규화하고 기존 writer를 사용한다.
- C는 B와 같은 좌표·문자열·스타일에, 관측 endpoint에서 계산한 owner-relative
  연결점을 각 native shape 내부에 추가한다. 연결된 도형의 단순 외곽만 custom geometry로 바꾼다.
- 숨은 보조 도형, proxy group, raster 삽입, 미결속 선으로 외형만 맞추는 우회는 없다.
- 6개 입력의 총 26개 객체와 13개 connector는 그대로다. 두 조건 모두 모든 ID,
  라벨 문자열, endpoint owner 쌍, 방향 플래그를 유지했다. C의 26개 endpoint 모두 결속됐다.
- 객체 좌표의 정규화 오차는 최대 0.000103px 미만, raster 0개다.
- 검출·OCR 재실행, 새로운 정답 문자열 사용, 생산 writer/모델/Phase 15·16 변경은 없다.

특히 Attention과 PERCEIVE는 R0에서 사람이 제공한 박스/역할을 사용한 scene이다.
좋아진 Attention 그림은 자동 검출 성능 향상의 증거가 아니다.

## 2. 육안 확인

| 사례 | 직접 확인한 변화 | 여전히 남은 문제 |
|---|---|---|
| BLIP | B/C 라벨과 화살표가 A보다 읽기 쉬움 | text decoder OCR 오류, 외곽선 차이 |
| Attention | C에서 네 화살표가 서로 다른 위치에 수직으로 도착 | token 외곽/스타일 차이; 수동 박스 사용 |
| HEVC | B/C 글자가 확연히 커져 읽을 수 있음 | `all PU Obtain units` 등 잘못된 어순 |
| Reasoning | 네 박스와 세 연결이 더 명료함 | 선·화살표가 굵고, C 모서리 곡률이 달라짐 |
| PERCEIVE | 글자 크기는 개선 | OCR/채움 오류, 꺾인 연결 2개 누락은 그대로 |
| Negative chart | 변화 없음에 가까움 | 차트 유래 가짜 도형 3개 유지: reject 실패 |

![원본 / R0 / 정규화만 / 정규화와 연결점](../artifacts/region-first-r1/review-v3/mixed-attention-comparison.png)

![HEVC 가독성 비교](../artifacts/region-first-r1/review-v3/serial-hevc-comparison.png)

정규화만 한 B에서는 Attention 화살표가 여전히 중앙에서 겹친다.
C에서는 네 개를 분리해서 읽을 수 있으므로, 단순 확대가 아니라 연결점 개입의 효과가 보인다.
초기 endpoint 최대 좌표 오차는 B 71.345px, C 0.001px 미만이다.
초기 XML 좌표만 믿지 않고 아래의 실제 PowerPoint 편집·저장 동작도 별도로 확인했다.

가독성 개선은 원본 대비 같은 크기의 그림을 본 육안 판정이다. 모든 텍스트가 정확하거나
원본과 같은 폰트 크기라는 뜻이 아니다. 정규화 후에는 기존 connector의 그림자와 무거운
선 스타일도 눈에 띈다. 스타일 정리는 별도 변경으로 남겼다.

## 3. 실제 PowerPoint 편집 검사

Attention target을 x +12pt / y +18pt 이동하고, 폭 x1.25 / 높이 x1.20로 변경했다.
그 shape의 text frame을 임시 문구로 편집한 뒤 원래 OCR 문자열로 복원했다.
편집 사본을 저장하고 닫은 다음 다시 열어서 또 저장하고 렌더했다.
마지막에만 모든 connector에 명시적 reroute를 호출해 별도 사본을 남겼다.

기대 endpoint는 출력 좌표에서 역추정하지 않고, 동결 source endpoint의 상대좌표와
사전 지정한 target 변환으로 독립 계산했다. 통과 허용 오차는 1pt다.

| 조건 | 이동·확대 후 최대 오차 | 저장·재열기 후 | 명시적 reroute 후 |
|---|---:|---:|---:|
| B 정규화만 | 56.7313pt, 실패 | 56.7313pt, 실패 | 47.2637pt, 실패 |
| C 관측 연결점 | <0.0001pt, 통과 | <0.0001pt, 통과 | 64.4319pt, **실패** |

- C의 target custom connection site 8개는 저장·재열기·reroute 후에도 존재한다.
  그러나 reroute가 site **선택 인덱스**를 바꾼다. 연결점 데이터 유실과는 다르다.
- 두 조건 모두 10개 native shape(객체 6 + connector 4) 유지, 원래 label 복원 유지,
  네 source→target owner pair 유지. 결속만 검사했으면 reroute 실패를 놓쳤을 것이다.
- untouched source bbox 오차 <0.000058pt, 요청한 target 변환 오차 <0.000072pt.
- text-frame 편집 성공. 입력 PPTX 두 개의 SHA는 변경되지 않았다.
- 이 검사는 COM으로 특정 이동/확대를 적용한 개발 사례 하나다. 임의의 마우스 편집,
  회전, 복사·붙여넣기, 그룹화, 다른 Office 버전의 모든 동작을 검증한 것은 아니다.

![이동·확대 후 저장·재열기: 연결점 유지, 배치는 겹침](../artifacts/region-first-r1/edit-probe-v1/normalized_sites--reopened.png)

![명시적 reroute: 원래 연결점 위치 소실](../artifacts/region-first-r1/edit-probe-v1/normalized_sites--rerouted.png)

사전 지정한 이동·확대 자체가 target을 source token 행과 겹치게 한다.
따라서 첫 그림에서도 연결점 보존은 통과했지만 배치가 보기 좋지는 않다.
이를 피하려고 변환량을 바꾸거나 재실행하지 않았다. **자동 레이아웃 정리 성공은 아니다.**

## 4. 판정과 다음 선택

1. **H1 가독성: 개발 사례에서 지지.** source inference 해상도와 출력 물리 크기를
   분리하는 선택을 유지한다. 잘못된 OCR을 크게 보이게 하는 문제까지 해결하지는 않는다.
2. **H2 최초 attachment 및 통상 이동/확대/재열기: 사례에서 통과.** 명시적 연결점은
   보조 도형 없이 initial fan-in 붕괴를 해결할 수 있다.
3. **H2 reroute까지 포함한 전체 계약: 실패.** C를 production 기본값으로 승격하지 않는다.
   reroute를 호출하지 않았다는 사실을 숨기거나, owner 결속만으로 성공 처리하지 않는다.
4. **편집성 trade-off:** connected object는 하나의 native shape이며 텍스트·위치·크기 수정이
   가능하지만 preset의 roundness 조절 손잡이 같은 속성은 보존하지 않는다.
5. **제품 성능/사람시간:** 승인하지 않는다. 사용자의 도움이 된다는 정성 확인은 존중하되,
   이것을 측정된 시간 절약 수치로 바꾸지 않는다. 기존 Phase 16 동결 판정도 유지한다.

다음 연구 우선순위는 **객체 후보의 정밀한 선택**이다. 출력 문제를 이유로 detector를
계속 늘리는 것이 아니라, R0 Attention의 빈 face·token 중복과 negative chart 오탐을
분리해서 줄이는 작은 R2를 먼저 사전 등록한다. 검출된 후보가 곧 emit 객체가 되어서는 안 된다.

R2는 coarse ROI를 고정하고 기존 후보 전체/선택 후를 대조한다. 동일 물체의 fill·outline·
ellipse 관측을 묶고, 빈 face·차트 프레임을 분리하며, box label이나 target ID를 선택 규칙에
넣지 않는다. matched 객체 손실, 추가 객체, 남은 사용자 삭제량을 함께 보고한다.
관계·OCR는 고정해 후보 선택의 이득과 손실을 따로 볼 것. 아직 R2 실행이나 새 holdout
소비는 하지 않았다. 실제 꺾인 stroke 회복과 OCR reading order는 그 다음 별도 실험이다.

## 5. 재현·기록

```powershell
rtk proxy .venv/Scripts/python.exe tools/run_native_emit_experiment.py --output-dir artifacts/region-first-r1/reproduction-new
rtk proxy pwsh -NoProfile -File tools/render_pptx_via_powerpoint.ps1 -InputPath artifacts/region-first-r1/reproduction-new -OutputDirectory artifacts/region-first-r1/reproduction-new-renders
rtk proxy pwsh -NoProfile -File tools/probe_native_emit_powerpoint.ps1 -RunDirectory artifacts/region-first-r1/reproduction-new -OutputDirectory artifacts/region-first-r1/reproduction-new-probe
rtk proxy .venv/Scripts/python.exe -m pytest -q
```

PowerPoint 기존 프로세스가 없는지 먼저 확인한다. probe는 기존 프로세스가 있으면 거부한다.
생성·probe 폴더는 새 경로여야 하며 원본을 덮어쓰지 않는다.
현재 review 도구는 `run1`, `run1-renders`, `edit-probe-v1` 경로를 읽는 이번 실행용 감사 도구다.
재현 경로를 자동 탐색하는 범용 CLI로 보아서는 안 된다.

- 전체 테스트 **229 passed, 9 warnings**. 테스트와 육안 판정은 별개다.
- review-v1 생성 후 라벨 속성명 감사 코드 오류(`text` 대신 `label`)로 중단된 기록은
  보존했다. 실제 PPT 출력/COM probe는 다시 실행하지 않았다. review-v2에서 수정했고,
  review-v3은 ID/좌표/방향 불변량과 수동 육안 기록을 더한 최종 ledger다.
- [사전 protocol](region_first_r1_protocol.md), [입력 SHA](../benchmarks/region_first_r1_inputs_v1.json),
  [검토 기록](../benchmarks/region_first_r1_visual_review_v1.json),
  [최종 evidence ledger](../benchmarks/region_first_r1_evidence_v1.json).
- 신규 PPTX: `artifacts/region-first-r1/run1/`; 원본과 A는 R0 경로 그대로다.
- 실제 PowerPoint 렌더: `artifacts/region-first-r1/run1-renders/`.
- 편집·재열기·reroute 사본/렌더/COM snapshot: `artifacts/region-first-r1/edit-probe-v1/`.
- 비교 그림: `artifacts/region-first-r1/review-v3/`.
- 원본/생성물은 ignored local artifacts이며, tracked ledger의 SHA로 결속했다.
  다른 checkout에서는 해당 파일이 있어야 재현 가능하다. 원격 push는 하지 않았다.
