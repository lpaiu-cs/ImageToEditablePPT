# Phase 16 PowerPoint operation-time calibration

이 측정은 자동화 benchmark가 아니라 **사람이 실제 PowerPoint에서 고치는 데 걸리는 시간**을 edit-cost weight로 바꾸기 위한 것이다. 자동화 실행시간이나 추정값으로 대체하지 않는다.

## 준비물

- deck: `artifacts/phase16-operation-calibration/operation_time_calibration.pptx`
- 기록표: `artifacts/phase16-operation-calibration/operation_time_measurements.csv`
- PowerPoint desktop `16.0`
- 초 단위 stopwatch

deck의 9개 slide가 각각 하나의 편집 작업이다. 모든 slide는 실제 PowerPoint 렌더로 육안 확인됐다.

## 측정 방법

각 작업을 10회씩 수행한다.

1. 원본 task slide를 복제해 새 trial을 만든다. 원본 task slide는 수정하지 않는다.
2. 지시문은 timing 전에 읽는다.
3. 첫 편집 동작 직전에 stopwatch를 시작한다.
4. 요구된 상태가 화면상 완성되는 순간 stopwatch를 멈춘다. 파일 열기, 지시문 읽기, 저장 시간은 포함하지 않는다.
5. CSV의 해당 `operation_id`와 `repetition` 행에 초를 `seconds`로 적는다.
6. 방해를 받거나 잘못 시작한 trial은 `valid=false`로 남기고, 같은 값을 덮어쓰지 않는다. 새 고유 repetition 번호를 추가해 다시 측정한다.

느린 정상 trial은 삭제하거나 다시 재지 않는다. 도구는 각 작업의 모든 valid trial에서 median을 계산한다.

## 측정 완료 후 검증

```powershell
.venv\Scripts\python.exe tools\calibrate_edit_operation_time.py `
  --measurements artifacts\phase16-operation-calibration\operation_time_measurements.csv `
  --participant-id local-human-1 `
  --powerpoint-version 16.0
```

정상 완료되면 `artifacts/phase16-operation-calibration/operation_time_calibration.json`이 생긴다. 이후 Phase 16 experiment lock을 다시 만들고, 다른 blocker가 없을 때만 MEG proposal ceiling을 시작한다.
