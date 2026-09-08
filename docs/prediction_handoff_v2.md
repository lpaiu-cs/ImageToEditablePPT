# 이미지 단독 prediction handoff v2

## 목적과 판정 경계

기존 `7bb2bedd`의 corrected v13 baseline 예측을 다시 추론하거나 학습하지 않고,
구조 트랙의 **predicted owners → traced graph → emitted graph → PowerPoint** 진단에
전달한다. 제품 loader·enum·v1 산출물은 변경하지 않는다. 새로운 평가 이미지는 열지 않는다.

이 버전은 **명시적 legacy 연구용 경로만 구현**한다. 기본 export/validate는 거부하고
`--allow-legacy-research`를 양쪽 실행에 명시해야 통과한다. 통과하더라도
`research_only=true`이며 성능·제품·과거 실행 provenance 승인으로 해석하지 않는다.
향후 `run_attested` 지원을 가장하여 현재 provenance를 승격시키지 않는다.

## 실제 과거 실행에 대해 모르는 것

v1 checkpoint는 class 이름과 실행 code SHA를 저장하지 않았다. class 대응은
`a00d61c` enum과 `3ae7caf` ellipse 삽입 diff에서 복구한 **legacy 추정**이다.
예측 후에 native/contact/freeze 코드가 추가되었으므로 v1 요약의 코드 SHA는 실행 당시
전체 파일 SHA가 아니다. v2는 다음을 반드시 유지한다.

- `inference_code.attestation = post_run_reference_snapshot`
- `inference_code.run_git_commit = null`
- `inference_code.reference_git_commit = 7bb2beddcd50ffd65146082a6f82947f3a2613e1`
- `inference_code.scope = listed_project_files_only_not_execution_attested`
- entrypoint와 Lightning/dataset/enum의 **참조 스냅샷 파일별 SHA**, 그 metadata 전체 SHA

이 목록은 프로젝트 코드 참조 범위이며 framework/OS/실제 과거 실행을 증명하지 않는다.
누락된 metadata를 자동으로 채우지 않는다. 먼저 `prepare-legacy`가 불확실성을 명시한
별도 선언을 만들고, exporter는 그 선언을 엄격히 검증한다.

## 파일과 스키마

새 산출물 루트는 `artifacts/ml-image-only-v2`다.

- `declaration.json`: 원예측/RGB목록/checkpoint/code/class/postprocess의 명시적 선언.
- `provenance/`: Git에서 읽어 저장한 코드·enum·변경 diff 스냅샷.
- **`baseline.handoff.final.json`**: 최종 통합 입력.
- `baseline.handoff.final.json.reads.json`: export 파일 접근 기록.
- `baseline.handoff.final.json.validation.reads.json`: 독립 validator 접근 기록.
- `strict-rejected.json.reads.json`: 옵션 없는 실제 거부 증거. 해당 bundle은 생성되지 않았다.

초기 `baseline.handoff.json`은 동일 데이터로 만든 구현 중간 검증본이다. 그 뒤 다른
checkout에서도 같은 코드 SHA로 validator를 실행할 수 있게 경로 검증을 보완했다.
중간본은 보존하지만 통합에는 `final` 파일만 사용한다.

envelope는 `payload`와 `payload_sha256` 두 필드다. SHA는 UTF-8 JSON의
`sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False` 표현으로
계산한다. pretty-print된 전체 파일 SHA와 canonical payload SHA는 서로 다르다.
`class_schema.sha256`, `inference_code.sha256`는 각 절에서 `sha256` 필드를 제외한
나머지 metadata의 같은 canonical SHA다. 파일 참조의 SHA는 실제 파일 바이트 SHA다.

payload의 필수 필드:

| 필드 | 의미 |
|---|---|
| schema_version | `image_only_prediction_handoff_v2` |
| research_only / limitations | true 및 legacy·실행 미입증·validation 노출 한계 |
| declaration | 아래 provenance·source·postprocess 선언 전체 |
| exporter_code | 연구 helper의 경로 및 실제 content SHA |
| samples | 원본별 의미 객체·제외 기록 |
| verified_source_files | 읽어 SHA를 확인한 원자료 파일과 목적 |

declaration에는 `source_prediction`, `rgb_inputs`, `checkpoint`의 절대 경로/파일 SHA,
위 `inference_code`, `class_schema`, `postprocess`가 모두 필요하다. checkpoint는
identity 확인용 바이트 hash만 읽고 deserialization·모델 추론은 하지 않는다.

## 클래스 계약

`source_num_classes=7`, `current_num_classes=8`,
`raw_label_space=r7b_current_labels_already_remapped`를 고정한다. 입력 JSON은 이미
legacy adapter를 거친 current 번호다. exporter에서 두 번 remap하지 않는다.

| checkpoint source_label | 예측 JSON raw_label | semantic_kind | role |
|---:|---:|---|---|
| 0 | 0 | background | background |
| 1 | 1 | box | node |
| 2 | 2 | rounded_box | node |
| 3 | 4 | section | node |
| 4 | 5 | label_anchor | node |
| 5 | 6 | flow_cluster | container |
| 6 | 7 | panel | container |

current label3 `ellipse`는 `unsupported_current_classes`에만 기록한다.
background·ellipse·unknown label이 detection에 등장하면 전체 export를 거부한다.
정수 수가 같더라도 의미 이름/role/순서가 다르거나 bool/float로 번호를 대체하면 거부한다.
class 수나 entries를 임의로 늘리고 metadata SHA만 다시 계산해도 거부한다.

## 객체와 좌표

각 sample의 `sample_id`는 `rgb-` + 원본 이미지 SHA 전체다.
v1 문자열 ID는 `source_record_id`에 추적용으로만 남기며 모델에 다시 넣지 않는다.
`source_rgb`는 실제 RGB PNG 경로/SHA, `image_size`는 `[width,height]`,
`coordinate_system`은 `original_image_pixels`다. RGB 변환·resize·ROI는 이 export에 없다.

각 object에는 다음을 기록한다.

- `id = sample_id + ':det:' + source_detection_index`
- source/raw class 번호, semantic_kind, role, confidence
- `bbox_xyxy`, `raw_bbox_xyxy`, `geometry_change=none`
- `evidence=rgb_detector_prediction`

라벨 문자열·연결은 새로 만들지 않는다. `text_prediction_status`와
`connection_prediction_status`는 모두 `not_predicted`다. label_anchor 검출은 OCR이 아니다.
이 상태를 연결 없음이 정답이라는 뜻으로 해석하지 않는다.

좌표/score는 finite여야 하고 confidence는 [0,1], bbox는 원본 안의 양의 면적이어야 한다.
잘못된 좌표를 clip·확장·제외하여 조용히 보정하지 않고 전체를 거부한다.
정상 detection 중 score/NMS에서 제외된 것은 `omitted`에 원객체와 사유를 남긴다.
사유는 `below_score_threshold` 또는 `cross_class_nms_or_node_containment`다.
후자는 두 억제 단계의 결합 사유이며 더 세밀한 원인을 측정했다고 주장하지 않는다.

## 후처리와 무결성

고정값은 `score_threshold=.5`, `cross_class_nms_iou=.7`,
`node_containment_threshold=.85`다. 평가 IoU=.5는 evaluator 계약이며 bundle에 넣지 않는다.
기존 `select_detection_indices`를 CPU float32로 사용하고 구현 파일과 dataset/enum
의존 파일 SHA를 선언과 대조한다. active semantic label 표도 검사한다.

validator는 envelope hash만 보지 않는다. 원예측·RGB·checkpoint·코드 파일 SHA를
재확인하고 객체와 제외를 재도출하여 bundle 전체와 비교한다. 중복 sample/object ID,
의미·좌표·confidence 변조, metadata 삭제, source SHA/크기 불일치는 거부된다.
exporter는 새 파일만 쓰며 기존 파일을 덮어쓰지 않는다.

소비자는 같은 helper 코드를 다른 checkout에서 실행할 수 있다. 기록된 exporter 파일
SHA와 실행 중 helper content SHA가 같아야 하며, 원래 경로를 단지 현재 cwd로 바꾸지
않는다. 선언의 source 경로들은 이 로컬 연구 환경에서 실제 접근 가능해야 한다.
다른 코드 버전·원자료가 없는 환경으로의 이동은 자동 완화하지 않는다.

## GT 접근 경계

exporter/validator의 입력은 existing predictions, RGB manifest/PNG, 명시적 provenance
파일, checkpoint identity다. GT dataset 경로·annotation/holdout 경로·PPT 입력은
연구 helper가 거부한다. CLI는 metadata 확인과 라이브러리 초기화 이후 모든 Python
파일 open을 선언에 포함된 파일과 RGB 및 필요한 코드/출력 파일 allowlist로 제한한다.
이 로그는 `*.reads.json`에 남는다. guard 설정용 RGB manifest 초기화도 별도 verified
reader로 선언의 SHA를 확인한다. 최초 declaration 자체는 사용자가 제공하는 루트 입력이며
그 필수 필드와 내부 digest를 이후 검증한다.
이는 Python 파일 접근 검증이며 OS sandbox 또는 native I/O 전체의 보장은 아니다.

## 재현

이 worktree에서 아래 명령마다
`rtk proxy C:/vs/ImageToEditablePPT/.venv/Scripts/python.exe`를 앞에 붙인다.
출력은 새 경로여야 한다.

```text
tools/export_prediction_handoff.py prepare-legacy --v1-root artifacts/ml-image-only-v1 --checkpoint C:/vs/ImageToEditablePPT/workbench-ml/run-v13-detector/checkpoints/last.ckpt --output-dir <새 v2 폴더>
tools/export_prediction_handoff.py export --declaration <v2>/declaration.json --output <v2>/baseline.handoff.final.json --allow-legacy-research
tools/export_prediction_handoff.py validate --bundle <v2>/baseline.handoff.final.json --allow-legacy-research
-m pytest -q tests/test_prediction_handoff.py tests/test_ml_image_only_pilot.py tests/test_detection_postprocess.py
```

실제 baseline은 원예측154개에서 노드94/container11을 선택하고 49개를 제외했다.
선택 객체의 bbox/score는 v1 원예측과 그대로 일치한다. 기존 평가의 prediction_count와도
일치하며 재학습·재추론·GT 평가를 새로 수행한 결과가 아니다.

회귀 검증은 **51 passed**다. 실제 final bundle의 export와 별도 validate가 통과했고,
현재 helper의 strict export는 거부되어 출력 파일이 생성되지 않았다. v1 요약에 기록된
전체 artifact SHA도 다시 확인하여 모두 그대로임을 확인했다.

이 bundle을 받아 owner→trace→emit 손실을 기록하는 것은 후속 구조 트랙의 일이다.
현재 export 성공만으로 그 후속 통합이 완료됐다고 주장하지 않는다.
