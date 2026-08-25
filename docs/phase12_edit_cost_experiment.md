# Phase 12. 편집 비용 기준선 실험

실험일: 2026-08-25

## 질문

프로젝트의 성공 기준을 픽셀 유사도가 아니라 **사용자가 PowerPoint에서 고쳐야 하는 최소 작업량**으로 다시 놓았을 때, 현재 파이프라인의 어느 경계가 실제 병목인가?

다음 세 조건을 우선 검증했다.

1. 출력이 native PowerPoint 도형·텍스트·커넥터로 구성되는가.
2. 커넥터가 도형에 결속되어 도형 이동을 따라가는가.
3. 정답 구조를 입력했을 때의 결과와 현재 휴리스틱 추론 결과 사이에서 편집 비용이 어디서 생기는가.

## 환경과 한계

- Python 3.12 가상환경에 `ml`, `ocr`, `test` extra를 설치했다.
- LibreOffice와 Microsoft PowerPoint로 각각 렌더·동작 검증을 했다.
- 저장소나 로컬 `workbench-ml`에 canonical checkpoint가 없었다. 따라서 이 실험은 **현재 정식 ML 모델의 실전 품질을 검증하지 못했다**.
- 비교 가능한 실험은 휴리스틱 경로와 GT annotation을 주입한 oracle-composed 경로로 한정했다.

## 평가기

`tools/evaluate_pptx_editability.py`를 추가했다. PPTX의 native object 수, 커넥터 결속, GT 대비 node/container/topology F1, label 정확도와 `edit_operations_lower_bound`를 계산한다.

편집 작업 하한은 현재 다음 오류의 합이다.

- node/container의 FP와 FN
- connector topology의 FP와 FN
- topology가 맞지만 화살표 방향·유무가 틀린 connector의 수정
- 누락·오인식 label
- 결속되지 않은 connector endpoint
- 도형 text와 중복되는 standalone textbox

이는 실제 사람의 편집 시간을 직접 재는 지표는 아니며, 비교 가능한 보수적 하한이다.

## 실험 A: 복잡한 실제형 입력

루트 `input.png`를 `--no-ml`로 변환했다.

- 추론: node 29, container 3, connector 6, text 77/100
- PPTX: 총 82개 object, autoshape 32, line 6, textbox 44
- 수정 전 connector XML 결속: start 0, end 0
- 수정 후 connector XML 결속: start 6, end 6

결속 및 단일 connector 수정 후 PowerPoint에서 도형을 36pt 옮기자 연결된 선의 시작점도 36pt 이동했고 반대쪽 끝점은 고정됐다. 여러 독립 선분으로 끊어 쓰지 않고 직선 또는 PowerPoint elbow connector 하나로 내보내므로 실제 편집 동작을 보존한다.

그러나 PowerPoint 렌더의 구조 품질은 실사용 기준에 미달했다. 다수의 잘못된 박스·텍스트 중첩과 부정확한 연결이 남았다. 즉, **PPTX가 편집 가능하다는 사실만으로 수작업 감소가 보장되지는 않는다**.

## 실험 B: 고정 GT가 있는 직교 흐름도

seed 42, 640×360, LibreOffice renderer로 합성한 held-out 표본 하나를 사용했다. GT는 node 8, container 1, connector 7, label 8이다.

| 경로 | Node F1 | Topology F1 | 방향 포함 F1 | 정확 label | 결속 connector | 편집 작업 하한 |
|---|---:|---:|---:|---:|---:|---:|
| 기존 휴리스틱 | 0.9412 | 0.3810 | 0.0952 | 7/8 | 14/14 | 18 |
| port-pair 중복 제거 | 0.9412 | 0.5714 | 0.1429 | 7/8 | 7/7 | 11 |
| GT oracle + 실제 compose/writer | 1.0000 | 1.0000 | 1.0000 | 8/8 | 7/7 | 0 |

동일한 두 connection port에 붙은 connector 후보를 하나로 줄이되 화살촉 증거가 있는 후보를 우선하도록 resolve를 수정했다. 같은 owner라도 포트가 다르면 별도 연결로 보존한다. connector 수는 14개에서 7개로 줄었고, topology F1은 0.3810에서 0.5714로, 편집 작업 하한은 18에서 11로 개선됐다. 다만 방향 포함 F1은 0.1429에 불과해 화살촉 판정도 여전히 핵심 병목이다.

oracle-composed 경로는 annotation을 adapter, text merge, connector resolve, emit writer의 실제 구현에 통과시킨 결과다. 모든 구조·label·결속 지표가 정확했고 편집 작업 하한은 0이었다. 이는 현재 병목이 writer나 composition contract가 아니라 **입력 이미지에서 정확한 객체와 관계를 찾는 단계**임을 분리해 보여준다.

## 이번 실험에서 수정한 신뢰성 결함

- PPTX connector의 start/end를 실제 도형 connection site에 결속하고, 다중 선분 route를 하나의 reroutable straight/elbow connector로 내보낸다.
- batch 입력의 동일 stem 출력 충돌을 변환 전에 거절한다.
- gate checkpoint가 없으면 명시적 `--no-gate` 없이는 실패하도록 했다.
- primitive가 0개인 결과를 family 기본값 때문에 `[OK]`로 보고하지 않도록 했다.
- 화살촉 판정에서 owner box의 어두운 잉크를 제외했다.
- 동일 owner pair의 중복 connector를 제거했다.
- CI가 ML/OCR 경로를 포함한 전체 test extra를 설치하도록 했다.

## 결론과 다음 관문

현재 코드는 **정확한 구조가 들어오면 편집 가능한 PPTX를 올바르게 구성할 수 있다**. 반면 복잡한 입력에서 휴리스틱만 사용한 결과는 아직 제품 기준에 미달한다. 따라서 family 수나 style 기능을 넓히는 것보다 다음 순서가 타당하다.

1. canonical detector/family/connector/gate checkpoint를 버전과 checksum이 있는 bundle로 고정한다.
2. diagram과 non-diagram을 함께 포함한 고정 real-figure benchmark를 만든다.
3. 각 출력에 대해 이 평가기와 실제 수정 시간을 함께 기록한다.
4. 가장 큰 편집 비용 항목부터 개선한다. 현 표본에서는 connector topology와 방향 판정이 우선이다.
5. 위 관문을 통과하기 전에는 generic routing, 새 family, style 고도화를 보류한다.

## 후속 육안 hardening (Phase 13)

Phase 12 수치만으로 판단하지 않고 controlled 출력과 복잡 실제 입력을 Microsoft PowerPoint로 다시 렌더해 육안 검토했다. controlled 출력에는 컨테이너 테두리의 거짓 connector, 네 노드를 덮는 거짓 box, 짧은 화살표 누락, 방향 반전이 실제로 보였다. 복잡 입력은 텍스트 영역을 box로 승격해 29개의 거짓 node와 다수의 떠 있는 OCR 텍스트를 만들었다.

컨테이너 변 제외, 중첩 윤곽 제거, 짧은 선분 회수, owner 잉크를 제외한 화살촉 판정, 중심점 기반 text ownership, text-only box 금지, title 외 standalone OCR 생략을 적용했다. 전역 OCR이 놓치는 어두운 node의 흰 라벨은 이미 검출된 node 내부에서만 재시도한다.

| 경로 | Node F1 | Container F1 | Topology F1 | 방향 포함 F1 | 정확 label | 결속 connector | 편집 작업 하한 |
|---|---:|---:|---:|---:|---:|---:|---:|
| visual hardening 후 휴리스틱 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 8/8 | 7/7 | 0 |

PowerPoint 렌더에서도 8개 node, 7개 화살표와 모든 방향·라벨이 자연스럽게 보였다. 이는 한 held-out 합성 표본의 결과이므로 일반화 증거로 과장하지 않는다.

복잡 입력은 29 node/3 container/6 connector의 혼잡한 결과에서 근거가 강한 중앙 node 1개와 title만 남기는 결과로 바뀌었다. 중앙 node의 두 줄 라벨은 흰 editable text로 복구했다. 거짓 양성은 크게 줄었지만 대부분의 구조가 공백이므로 제품 품질이나 전체 복원 성공으로 보지 않는다. OCR 합성어의 띄어쓰기 손실도 잔여 문제다.

## 검증

- 전체 테스트: `152 passed` (`9 warnings`)
- 경고는 Lightning의 pytree deprecation과 dataloader worker 권고이며 test failure는 아니다.
