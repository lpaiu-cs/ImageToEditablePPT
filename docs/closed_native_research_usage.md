# 이미지 한 장에서 편집 가능한 부분 PPT 만들기

## 현재 범위

이 명령은 정답 annotation이나 기존 검출 캐시 없이 이미지에서 직접 부분 native PPT를 만든다. production 승인 명령은 아니다. 닫힌 박스·확실한 라벨·원본 근거가 있는 연결만 남으며 나머지는 생략될 수 있다. 사진/아이콘 일반 분류와 모든 복잡 관계의 복원은 아직 보장하지 않는다.

현재 고정 구성은 `closed-native-v2`다. 중첩 parent 내부 연결 마스크, union 자식의 OCR 제외, 원본1픽셀 경계 대응, 확실한 세로 라벨의 native 방향을 포함한다. `handoff.json`에 구성명을 기록한다. 이전 v1 산출물/실패를 덮어쓰지 않는다. 새 사진 캡션 대조군은 별도 검증 중이며 이 경로에 사진 일반분류기나 실패한 소형 CNN을 넣지 않았다.

## 실행

저장소 루트의 기존 `.venv`를 사용한다.

```powershell
rtk proxy .venv/Scripts/python.exe tools/convert_closed_native.py --image input.png --output artifacts/my-closed-native-run
```

RGB 또는 모든 alpha가255인 RGBA만 받는다. 후자는 RGB 픽셀을 바꾸지 않고 alpha만 제거하며 원본/파생 SHA를 보존한다. 투명 이미지를 임의의 배경으로 합성하지 않는다. 기존 출력 디렉터리는 덮어쓰지 않는다.

결과:

- `native/result.pptx`: 도형·글자·연결이 개별 편집 가능한 부분 초안
- `native/result.json`: 원본 관측, 소유 영역, OCR 비교, 연결과 최종 출력 기록
- `native/lock.json`: 입력·코드·OCR/폰트 SHA
- `handoff.json`: 원본/PPT SHA, 출력 개수, `production_approved: false`

`no_confident_structure`이면 구조를 찾았다고 보고하지 않는다. 비어 있는 PPT를 변환 성공으로 해석하지 않는다.

## 실제 PowerPoint로 확인

```powershell
rtk proxy pwsh -NoProfile -Command 'if (Get-Process POWERPNT -ErrorAction SilentlyContinue) { throw "사용 중인 PowerPoint를 먼저 확인하세요" }; & ./tools/render_pptx_via_powerpoint.ps1 -InputPath artifacts/my-closed-native-run/native/result.pptx -OutputDirectory artifacts/my-closed-native-run/renders -Width 1280'
```

사용 중인 PowerPoint 프로세스를 강제로 종료하지 않는다. 원본과 실제 렌더를 비교하고, 남은 객체의 위치·텍스트·관계가 유용한지 확인해야 한다. PNG/JSON의 개수만으로 production 승인하지 않는다.

확인된7개 개발 그림의 결과와 한계는 `r10_closed_native_v1_results.md`를 참조한다. 그림별로 유리한 설정을 고르는 인터페이스가 아니라, 검증한 통합 설정을 동일하게 적용한다.
