# R12 raw-branches v1 독립 감사: 기존32건 유지, 회색 교차 반례 실패

**고정 CLI는 R11로 유지해야 한다.** 기존32 RGB 통합 회귀는 유지됐지만, component-local 입력에서 보이는 회색 교차선이 사라져 잘못 승인되는 별도 기하학 반례를 확인했다. 기존 회귀 통과가 이 안전성 실패를 상쇄하지 않는다. 구현·기준은 수정하지 않았다.

## 고정 실행

- 실행 root commit: `8d14c24d918eb08f32bbeee34fca71365bf2681b`
- worker cherry-pick: `3516927`. 감사 전용 branch에 없던3개 파일의 modify/delete 충돌은 요청 commit의 incoming 파일 그대로 채택했다. 실제 실행은 root 고정 source를 사용했다.
- artifact: `artifacts/r12-raw-branches-v1`
- lock SHA256: `98b1f3d83327834a78c24c668c606581d29060c85366a8beef4525672726868a`
- 입력32 records는 `artifacts/r11-spatial-fresh-v3/lock.json` 그대로다. runtime에는 RGB만 전달했고 OCR/추론을 새로 실행했다.
- 이전 모든 R11 probe flags에 `--raw-branches`만 추가했다. 매 건 source/RGB 해시와 최종 runtime raw_branches flag를 검증했다.

```text
C:/vs/ImageToEditablePPT/.venv/Scripts/python.exe tools/r10_closed_native_integration_audit.py run --out artifacts/r12-raw-branches-v1 --nested-owners --pixel-agreement --spatial-texture --raw-branches
```

완료 폴더는 덮어쓰지 않는다. 재실행은 별도 lock/output 폴더가 필요하다. source snapshot, commands/stdout/stderr, 각 native lock/result/PPT를 보존했다.

## 통합 결과

32건 모두 exit0이다. 모든 `emitted_scene`이 이전 R11 결과와 전체 JSON 동일하며 raw 추가 연결은0이다. 양성12건은44box/44label/24edge, 음성사진20건은 shape/edge/picture0을 유지한다. 양성12개 실제 PPT XML의 `cNvPr` ID와 `stCxn/endCxn`을 대응해 Read–Build, Build–Check 두 연결을 확인했다. 음성20개 XML에는 도형·연결선·그림이 없다.

검증은 `verification.json`에 있다. 이번 작업은 요청대로 **COM을 실행하지 않았다**. R11 COM 결과를 이번 실행의 새 렌더 증거로 재사용하지 않는다. 입력 사진은 원본2개의 파생20개이며 도식12개를 포함한32건이다. 이 세트에는 새 raw 분기 성공 사례가 없으므로 분기 복원 효과를 주장할 수 없다.

## [P1] 회색 교차 곁선이 원본 성분에서 제거되어 승인됨

위치: `src/image_to_editable_ppt/research/raw_branch_completion.py:33`의 trace component를 그대로 `_fit`에 전달하는 경계. `region/strokes.py:15`는 dark ink를 gray<110으로 선택하지만 기존 B-v1 원본 mask는 integer luminance<130이다. 따라서 B-v1이 검사하던 실제 잉크를 component-local 경로에서 잃을 수 있다.

재현 RGB는360×600 흰 배경이다. 박스는 `(20,120,100,240)`, `(490,120,580,240)`이며 검정 두께2다. 먼저 회색120 두께2 수직선 `(290,130)→(290,230)`을 그린 뒤 검정 두께2 수평선 `(100,180)→(490,180)`을 그린다. 실제 영상에는 연결된 교차 곁선이 있다.

- R12는 LINE1개를 추가한다. `_fit`: seed_max1, whole_component_max1, coverage1, supported_box_raw_centerline.
- 같은 RGB의 기존 B-v1 원본 mask를 `_fit`에 전달하면 seed_max8, nonlinear_or_competing_seed로 기권한다.
- H는 전체 RGB에서 branch_or_contact를 보고하지만, 방향 미승인을 LINE으로 바꾸는 경로가 연결 자체를 막지 않는다. 방향 fallback만 바꾸기보다 입력 성분에서 곁선이 제거되는 원인을 다뤄야 한다.

이는 spec의 “연결된 곁가지는 그대로 반례로 남는다”를 충족하지 못한다. `_fit` 함수와 수치 기준이 같아도 입력 픽셀 집합이 다르므로 기존 B-v1 안전성을 그대로 계승한다고 볼 수 없다. raw_components=False 기본 경로는 이번 변경에서 유지되며 R11 CLI 결함으로 보고하지 않는다.

보존 파일:

- `artifacts/r12-raw-branches-v1/gray-crossing-repro.py`
- `artifacts/r12-raw-branches-v1/gray-crossing.png`
- `artifacts/r12-raw-branches-v1/gray-crossing.json`
- RGB SHA256: `07815a30b1b6c092b164f5fdbe79f02c849ffedfe4c09c7450fff14bce114cb2`

반례는 두 owner를 직접 주는 기하학 단위 검사이며 전체 OCR pipeline 반례라고 확대하지 않는다. 원본 RGB를 육안 확인했고 재현 assertion이 R12 승인/기존 B-v1 기권을 확인했다. 새 holdout·학습·다운로드를 사용하지 않았다. 후속 수정은 별도 arm으로 검증해야 하며 v1 실패는 보존한다.
