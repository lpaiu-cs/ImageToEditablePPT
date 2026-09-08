# R15.2-A 방향 고정 분기 독립 검증

## 판정

root `eee6895f5f037d2fa085926f43187216d0435a24`에서 R14 fixed flow 옵션에 `--directed-fanout`만 추가하여 기존 43건과 source PPT 통제 4건을 fresh 실행했다. `--boundary-gaps`는 사용하지 않았다. 47건 모두 exit 0이며 입력·소스 해시 검사가 통과했다.

기존 43건의 emitted scene과 styles는 R14 v4와 모두 완전히 같다. 기존 합계 68 shape, 64 label, 32 edge 및 picture 0을 보존했다. 그러나 새 직선 fanout 양성은 3개 관계를 하나도 복원하지 못했다. 이 통제에서 신규 효용은 확인되지 않았으며, 일반적인 직선 fanout 복원으로 해석할 수 없다.

## source 통제 결과와 의미

| 사례 | 후보/출력 node/label | source 관계 | 출력 edge | arm 기대와의 관계 |
|---|---:|---|---:|---|
| straight | 4/4/4 | Read→Build/Check/Write 3개 | 0 | 양성 회복 실패 |
| undirected | 4/4/4 | 무방향 연결 3개 | 0 | 제한된 arm의 기권 기대 일치 |
| partial-arrow | 4/4/4 | 연결 3개, Build 쪽만 방향 있음 | 0 | 제한된 arm의 기권 기대 일치 |
| bent | 4/4/4 | 방향 관계 3개, 위·아래 경로 굽음 | 0 | 제한된 arm의 기권 기대 일치 |

음성 3개의 source 관계를 정답 0개로 바꾸지 않는다. 출력 0은 지원 범위를 넘는 분기를 보수적으로 승인하지 않았다는 의미이며 source 관계 recall의 성공이 아니다. 모든 사례에서 Read/Build/Check/Write 라벨과 네 노드를 보존했고, tracing에는 네 owner가 접한 단일 component가 기록됐다. 따라서 노드 후보나 OCR 실패 때문에 분기 시험 자체가 무효가 된 경우는 아니다.

같은 동결 root에서 directed-fanout 옵션을 끈 통제 4건도 별도 실행했다. 모두 4 node/4 label/0 edge이고 옵션을 켠 결과와 emitted scene이 완전히 같다. 이 4건에서는 새 옵션의 증분 효과가 0이다.

## 직선 양성의 실패 원인

저장된 예측 geometry와 동일 RGB로 trace를 다시 구성한 진단에서 saved `original_trace`와 정확히 동일한 결과를 얻었다. root 소스는 수정하지 않았으며 OCR을 다시 실행하거나 fixture를 바꾸지 않았다.

| hub Read에서 leaf로 탐색 | shaft 최대 잔차(px) | 기존 허용치(px) | arrow sign |
|---|---:|---:|---:|
| Build | 4.796520 | 2.0 | +1 |
| Check | 0 | 2.0 | +1 |
| Write | 4.845676 | 2.0 | +1 |

화살표 끝 증거는 모두 방향 +1이며 shaft width 5px, end width 16/16/15px다. 상하 직선 ray에서도 hub-first BFS 경로의 직선 잔차가 허용치를 초과해 unique hub가 탈락한다. 방향 캐시 고정은 이 source 조건의 경로 직선성 문제를 해결하지 않는다. cutoff 완화나 사후 source 교체로 양성을 구제하지 않았다.

## 증거와 범위

- fresh artifact: `artifacts/r15-fanout-fresh-v1`
- fresh lock SHA: `5160933dffeb65206b13c2e8c78e596f798ec87c31807f195cc6a334a0c91a58`
- `verification.json`/`verify.py`: 기존43 scene/style 동일성, 통제 후보·라벨·방향 관계와 XML 검사.
- `straight-diagnostic.json`/`diagnose_straight.py`: 저장 geometry 기반 실패 경로 진단.
- baseline 통제: `artifacts/r15-fanout-controls-baseline-v1`.
- 출력 COM: 통제 4개만 800×450 렌더하고 모두 직접 확인했다. 출력에는 네 노드와 라벨만 있고 연결은 없다. 기존43 전체를 새로 COM 렌더했다는 의미는 아니다.
- 출력 COM manifest SHA: `6cbdab308b2113ce7741aff1194fcb207a1b2b463f1978245deb8f38829f7d2b`.
- `receipt-binding.json`/`verify_receipts.py`: source PPT·RGB→fresh PPT→COM 렌더 해시 연결 및 baseline 동일성 검사.
- source 생성·사전 기대·테마 그림자 조건: `docs/r15_directed_fanout_controls.md`.

COM은 반환했고 POWERPNT 프로세스가 남지 않았다. root의 reasoning/복잡7 개선 보고는 이 독립 통제의 검증 결과와 구분한다. 이번 source 4건은 동일 템플릿 계보의 노출된 회귀 대조로 독립 일반화 표본이 아니다. 신규 사진·다운로드·학습·holdout 접근은 없다.
