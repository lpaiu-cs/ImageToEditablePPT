# R10 폐윤곽 기반 이미지 단독 native PPT: 통합 실행 결과

## 결론

실패 기록에서 작업을 끝내지 않고 앞단을 바꾸어 수정·대조·실제 PowerPoint 렌더를 반복했다. 레거시 모델이 복잡 그림에 만든 큰 가짜 owner를 그대로 후처리하는 대신, **원본에서 각각 검증된 실제 폐윤곽을 제안하고 소유 영역별 OCR를 복원**하는 고정 경로를 만들었다.

최신7개 실행은 native 도형99개/비어 있지 않은 라벨93개/native 연결31개/삽입 이미지0개다. **이는 출력 개수이지 정답 개수나 성공률이 아니다.** 육안으로 확인한 부분 복원은 개선됐지만, 모든 복잡 도식의 전체 복원이나 무조건적인 프로덕션 승인은 아니다. 원본 일부와 fusion/contrastive는 관계 누락이 많다.

## 고정 실행과 자료

- 핵심 실행 코드 Git: `7828c30` (`R10-P: Integrate independently observed boundaries and owned text`)
- 입력: 기존 real development6개와 이미 노출된 원본1개. 새로운 holdout은 열지 않았다.
- 출력: `artifacts/region-image-only-r10/closed-native-v1/{id}/result.pptx`
- 비교 이미지와 감사: `artifacts/region-image-only-r10/closed-native-v1-review`
- 실행 입력은 RGB뿐이다. annotation/정답 PPT/검출 캐시/이전 scene은 입력하지 않았다. 사전학습 RapidOCR ONNX는 사용하며 그 파일 SHA는 lock에 있다.
- 원본 `input.png`는 RGBA지만 alpha 전 픽셀이255임을 검증한 뒤 alpha만 제거했다. RGB 값은 동일하다. 원본 SHA `f664aecdd35261c549fd3dc9fba7b2098e5ad50d9c515fc2db30169edbe381cf`, RGB PNG SHA `ca69631098693305962aa48fbbeab3c3353079d45fa56332451b8aa09b1e77b5`. provenance는 `complex-inputs/original-rgb.provenance.json`에 있다.
- Python/네이티브 라이브러리 IO를 OS sandbox로 격리한 실행은 아니다. 입력·코드·OCR/폰트 hash 및 실행 중 불변성 검사로 범위를 기록했다.

## 구현한 수정

1. Canny 두 threshold와 어두운 픽셀 두 threshold에서 각각 검증한 실재 폐윤곽의 합집합을 사용한다. 중복은 제거하되 새로운 bbox나 경계를 평균·창작하지 않는다. 세로 박스에도 대칭 크기 조건을 적용한다.
2. 출력 후보에서 제외된 내부 폐윤곽도 부모의 색과 글자에 포함되지 않도록 소유 영역을 분리한다. 작은 색 배지도 별도 소유이다.
3. 위치 기반 OCR와 실제 잉크 행 OCR를 모두 실행한다. 겹친 OCR 창을 이어 붙여 숫자를 중복하지 않고, 서로 충돌한 문자열은 공백으로 둔다. 단일 글자는 양쪽 관측의 동의를 요구한다.
4. 글자는 원본 위치에 대응하는 native 도형 text-frame inset에 둔다. 겹치는 OCR bbox 높이를 단순 합산하지 않고 실제 줄 간격을 쓰며 Arial 폭으로 맞춘다. 도형을 옮길 때 글자도 함께 움직인다.
5. 실제 닫힌 흰색 내부는 투명하지 않은 흰색 채움이다. 부모 색이 자식 내부로 비치지 않게 했다.
6. 사진 내용은 자식 영역으로 가린 뒤 검사하지 않고 원본 전체 내부에서 텍스처 거부 여부를 검사한다. 이 검사가 일반 semantic 분류기라는 주장은 하지 않는다.
7. 마지막 native 연결과 owner 연결 ID를 다시 확인하고, 신뢰 라벨도 native 연결 근거도 없는 고립 경계는 제거한다.

## 실제 렌더를 직접 본 판정

| 그림 | 도형 | 라벨 있음 | native 연결 | 육안 관측과 제한 |
|---|---:|---:|---:|---|
| reasoning-full | 24 | 22 | 18 | 원본의24개 박스 위치와 세 줄 흐름이 복원됐다. 가짜 대형 owner 없음. 분기·점선 연결 누락, 세로 글자 방향/크기와 일부 라벨 공백·부분 prefix는 남는다. |
| blue-flow | 7 | 6 | 5 | 실제7개 박스, 주요 직교 흐름이 복원됐다. `Section 3 3.4` 중복은 없어지고3.4가 직접 읽혔다. 위쪽 distillation과 아래쪽 합류 일부, 우측 상단 라벨은 누락이다. |
| nested-panels | 26 | 26 | 0 | 부모 제목이 자식 글자와 겹치지 않고 원래 제목 위치에 있다. 부모/자식 색이 분리됐고 PDF 아이콘 내부 글자와 바깥 라벨의 중복은 없어졌다. 일부 내부 모델/입력 박스와 전체 외곽은 빠졌다. `LLMAPIs`의 띄어쓰기 손실은 남는다. 원본 자체가 화살표 없는 구획 도식이므로 연결0을 오류로 세지 않는다. |
| contrastive | 22 | 22 | 1 | 실제 encoder/decoder 일부와 BOS/EOS 토큰이 편집 가능하다. 수식 악센트를 빼고 평문T로 승인하던 일부 위험은 기권하도록 고쳤다. 대부분의 흐름 관계가 빠져 전체 도식용으로는 부족하다. |
| dark-transformer | 7 | 5 | 2 | 실제 스택/임베딩 박스를 복원했다. 검정 배경은 복제하지 않았다. Add & Norm 글자, skip 관계와 화살촉 일부가 누락이다. 방향이 없는 선을 방향 정답으로 부르지 않는다. |
| fusion | 4 | 4 | 1 | 질문을 한 개 editable 라벨로 유지하고 POS/NER/RoBERTa 박스를 복원했다. 중심 fusion과 외곽 그룹·대부분 관계는 빠져 최소 초안만 유효하다. |
| original | 9 | 8 | 4 | 이전 거대 가짜 박스와 합쳐진 라벨이 사라졌다. Sensory/Identity/Boundary와 ACT 일부의 관계가 복원됐고 QueryPlanner 글자가 경계 밖으로 나가지 않는다. 대부분 루프·외부 입력·memory 구조는 누락이다. 일부 설명문은 신뢰 prefix만 남아 불완전한 괄호가 보인다. |

모든 비교 이미지를 원본과 실제 COM 렌더로 직접 확인했다. 이 표는 GT 자동 평가가 아니라 제한을 명시한 육안 관측이다. 사진/아이콘을 다시 그리지 않았으며, native PPT를 원본 이미지 위에 겹쳐 넣어 시각 점수를 높이지 않았다.

## 검증

- 활성 회귀: **1281 passed / 2 known xfailed / 9 warnings**. JUnit: `artifacts/region-image-only-r10/closed-native-v1-regression.xml`.
- C-v1 역사적6실패가 있는 `tests/test_source_centerline.py`는 기존 동결 경계대로 별도 보존한다. 위1281개에 포함시켜 성공으로 바꾸지 않았다.
- 신규 폐윤곽/OCR/소유/내용/텍스처 관련77개 단위검사 통과.
- `audit_closed_native_batch.py`가7개 PPT를 검사했다: 도형 ID·bbox·라벨 일치, 실제 connector의 양쪽 owner ID, 그림/embedded media0, 원본·결과·PPT·COM 렌더 SHA 연결 모두 통과했다.
- 이는 저장된 native 편집성 검사이다. **실제 사람이 수정하는 시간 감소는 아직 측정하지 않았다.**
- 별도 복사본을 실제 PowerPoint에서 열고 `Pruned Space` 도형을 오른쪽12pt/아래8pt 이동하고 텍스트를 바꾸었다. 연결3개의 owner 부착이 유지되며 선 위치도 갱신되는 것을 COM으로 확인했다. 원본 PPT SHA는 변하지 않았다. 증거는 `closed-native-edit-probe-v2/edit-probe.json`과 `edited.pptx`다. 첫 probe는 untitled로 열어 Save가 실패했고, 파일 복사본을 named document로 여는 수정 후 재검사했다. 이는 자동 편집 가능성 검사이지 사람의 수정시간 실험이 아니다.
- 단일 입력 CLI `tools/convert_closed_native.py`를 추가했다. 실제 blue-flow 실행의 COM PNG가 고정 batch의 PNG와 byte-identical이었으며, 불투명 alpha 보존·투명 입력 거부·기존 출력 보존3개 경계 테스트도 통과했다. CLI는 `production_approved: false`를 명시한다.
- 각 파일 전체 SHA는 `closed-native-v1-review/audit.json`에 있다. 대표 PPT SHA: reasoning `24d9f946f8735f170f9fd139bbd43f7741d226bafe4145fe28a94a0290c40244`, nested `a8dbe8705b90f10b44a7e163220647ba78a4915bb7e414265e3245166fda6f95`, original `3420e42169c9ce712b26710bd5e89b4c5bdc495a6ced5805ac2df5019323637a`.

## 실패에서 배운 것과 아직 해결하지 못한 것

- 단색 내용 gate는 원본10개를1개로 줄였고 사진 캡션 반례도 남아서 채택하지 않았다.
- 최초 텍스처 gate도 큰 글자와 색 변화에 과잉 기권했다. 후속 버전에서 실제 텍스트 창과 거의1차원인 색 변화의 처리를 분리했다. 회색조 사진은 여전히 사각지대이다.
- source-row OCR의.98을 낮추는 안은 독립72개에서 실제 문자 오답이 생겨 채택하지 않았다.3배율 일치가 독립된3모델의 증명은 아니다. 같은 모델의 동시 오인·띄어쓰기 손실·잘린 글자 위험이 있다.
- 닫힌 실제 사각형이라는 사실은 semantic diagram-node라는 증명이 아니다. 그레이스케일 사진 캡션 등의 판별에는 별도 의미 증거가 필요하다.
- 이번 경로는 전체 figure가 아니라 **확실한 최소 구조의 편집 가능한 부분 초안**이다. 무조건적인 production 승인, 새 holdout 통과, 실제 편집시간 절약을 주장하지 않는다.

다음 작업은 근거 없이 threshold를 완화하는 것이 아니라, 기존 PPT→스크린샷 정답쌍의 실제 provenance를 확인하고 의미 판별 학습에 사용할 수 있는지를 별도 학습 트랙에서 검증하는 것이다. 현재의 실제 개선과 남은 실패는 서로 상쇄하거나 덮어쓰지 않는다.
