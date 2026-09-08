# R15 경계 대조 자료의 재사용 범위

## 확인 범위

기존 R14 v4의 노출된 43건에 대해 현재 RGB SHA와 source PPT·source COM 렌더의 receipt SHA를 모두 재확인했다. 43건 모두 일치한다. 절대 경로와 객체 XML 요약은 `artifacts/r15-boundary-inventory-v1/inventory.json`, 재실행 검사는 같은 폴더의 `inventory.py`에 있다.

43건의 XML preset 종류는 rect/line뿐이다. native/diagram-picture 반복 템플릿과 china/flower 및 생성 icon 계보를 공유한다. 기존 사진 기권·frame-only 보존 회귀에는 유용하지만 새로운 경계 복원 임계값의 독립 calibration/eval로 계산하지 않는다. XML rect에는 텍스트 상자도 포함되므로 preset 수를 구조 노드 GT로 해석하지 않는다.

## 기존 train의 소규모 재사용 후보

`C:/vs/ImageToEditablePPT/workbench-ml/ds-v13-soffice/dataset_manifest.json`에서 명시적으로 train인 첫 사례를 family마다 하나 선택했다. 실행 점수로 선택하지 않았다. 이 7건의 PPT/PNG/annotation 21개 파일 해시는 기존 `r10-pair-provenance-v2/results.json`과 모두 일치했다. manifest SHA는 `671c4fe856c5d6393ba19b4255020304642929797cfdadcb75d102f6ed224557`이다.

공통 경로는 `C:/vs/ImageToEditablePPT/workbench-ml/ds-v13-soffice/train/<id>.pptx`이다.

| ID | XML 도형 | annotation node/container | XML connector |
|---|---|---:|---:|
| table_matrix_1302_00000 | roundRect 6 | 6/0 | 0 |
| layered_stack_1302_00001 | roundRect 6 | 6/0 | 5 |
| block_flow_1302_00003 | roundRect 5 | 4/1 | 3 |
| orthogonal_flow_1302_00004 | roundRect 6 | 5/1 | 10 |
| cycle_1302_00005 | roundRect 5 | 5/0 | 5 |
| tree_1302_00012 | rect 6 | 6/0 | 5 |
| graph_1302_00020 | rect 6 | 6/0 | 6 |

이 7건은 picture와 명시 dash가 없다. 명시 선폭은 1.5/2.25pt이고 tree에는 default 선폭도 있다. family 이름만으로 가림·교차·경계 틈의 실제 coverage를 주장하지 않는다. 기존 PNG는 오래된 soffice 출력이므로 현재 COM receipt가 필요한 평가에서는 source PPT를 새로 렌더해야 한다. 현재 파일 해시 일치는 과거 렌더 과정의 소급 증명이 아니다.

## 임계값 설계에 남는 공백

선택 자료만으로 열린 윤곽, 작은 틈과 큰 틈, 가림, 굵은 테두리, ellipse/diamond/원통, 스케일 변화의 대조 coverage를 입증할 수 없다. 기존 PIL 96개 기하 fixture는 대조 조건의 설계에 참고할 수 있으나 source PPT→COM calibration 건수에 합산하지 않는다.

새 대조군이 필요하면 기대 역할과 생략 조건, 레이아웃/자산 계보별 calibration/eval 분리를 먼저 고정한 뒤 소수 source PPT를 생성·COM 렌더한다. 같은 장면의 crop/재렌더를 독립 split으로 나누지 않는다. 이번 inventory에는 추론, COM, 새 생성, 다운로드, 학습, val/test 또는 Phase16 holdout payload 접근이 없다.
