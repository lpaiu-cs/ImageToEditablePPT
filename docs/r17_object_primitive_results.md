# R17 결과: 단순 도형 복원은 개선, 복잡 도식 일반화는 실패

2026-09-09. 사용자 후속 진행 승인에 따라 학습·독립 평가·실제 PowerPoint 렌더·복잡 원본 진단까지 실행했다. 실행 코드 기준 `36e8554`, 최초 명세/모델 커밋 `712a389`.

## 최종 판정

1. **객체 단위 분류 파이프라인은 제한된 PPT 도형 분포에서 작동한다.** 단독 도형 학습24/24, 새 배치의 평가에서는 가장 좋은 대조군이72개 중71개를 정확한 종류와 위치로 복원했다. 실제 COM 결과에서도 여섯 종류가 대부분 남는다.
2. **선학습의 추가 이득은 이번에도 확인되지 않았다.** primitive 선학습군은69TP/1FP/3FN이고, 동일 계산량의 scene 추가학습 대조군은71TP/0FP/1FN이다.
3. **실제 프로덕션 승인은 불가하다.** 기존 복잡 CogBot 원본에 같은 RGB-only 파이프라인을 적용하자 글자·아이콘·배경 조각을24개의 잘못된 마름모로 출력했다. 이 실패를 단순 합성 평가의 높은 점수로 상쇄하지 않는다.

제품 기본 CLI와 R15 출력은 변경하지 않았다. R16 실패 데이터·모델·판정을 덮어쓰지 않았다. 기존 Phase16 formal holdout/val/test payload도 열지 않았다.

## 구현 및 데이터 경계

R16의 `scene80_scene80.pt`를 공통의 고정 점유 검출기로 사용했다. 세 arm 모두 같은 후보와 crop을 받는다. 종류별 high-confidence 내부 조각 대신 배경이 아닌 전체 후보의 bbox를 사용했다. 예측 bbox에 여백을 주고 grayscale 관측과 예측 occupancy를64×64로 만들어 기존 family CNN의 공간 pooling/head만 바꾼 객체 분류기에 넣었다. 불필요한 신규 프레임워크 대신 기존 검출기·분류기·native preset 출력·COM 감사 도구를 재사용했다.

source GT bbox와 종류는 train 후보에 label을 붙이거나 평가할 때만 사용했다. 모델 추론에는 RGB와 가중치만 주었다. 별도 `predict` 호출의6개 객체가 evaluator의 동일 입력 예측과 정확히 일치했고, 파일·가중치·코드 SHA를 실행 전후 검증했다. 객체 의미 역할이나 source annotation을 불러 렌더한 결과가 아니다.

학습 데이터는 기존 R16 train24 primitive/24 scene/4 negative만 사용했다. 독립 작업은 새 calibration16장과 eval16장을 source PPT/white occupancy companion 총64PPT로 만들어 실제 COM320×200으로 렌더했다.32개 RGB는 상호 고유하고 R16 전체72개 RGB의 SHA와도 중복이 없다. source/mask geometry·adjustments·receipt 검사가 통과했다.

eval 배치는 calibration/train의3열×2행과 다른2열×3행이다. eval 높이는95..130 source px라서 기존95..170과 종횡비 분포도 함께 달라진다. 여전히 채움 있는6종, 무중첩·무회전·기본 adjustment의 작은 합성 분포다. 사진·outline-only·가림·계층·연결 일반화를 뜻하지 않는다.

## 중간 양성 대조 및 학습 결과

primitive300steps 이후 **24/24 정답**, 종류별4/4였다. 후보도 이미지마다 정확히 하나씩 정답에 매칭됐다. [24개 crop 보드](C:/vs/ImageToEditablePPT/artifacts/region-image-only-r17/positive-v1/positive-crops.png)를 직접 확인했다. 왼쪽 채널은 grayscale 원본 관측, 오른쪽은 GT가 아닌 예측 occupancy다. 전체 윤곽이 남고 일부 mask가 거칠어도 종류를 구분했다.

이 통과 뒤에만 후속 학습과 새 평가를 진행했다. seed1701, stage300steps, batch12(종류별2개), AdamW lr.001, 같은 초기값과 마지막 scene RNG1703을 사용했다. 단계마다 optimizer를 새로 만들고 primitive 및 scene-first checkpoint를 보존했다. 독립 읽기 전용 감사에서도 초기값·계산량 대조·GT 경계·calibration 선행·SHA 계약의 무효화 문제는 발견되지 않았다.

| arm | scene train top1 | primitive train top1, scene 학습 후 |
|---|---:|---:|
| scratch_scene300 | 144/144 | 22/24 |
| pretrain300_scene300 | 144/144 | 23/24 |
| scene300_scene300 | 144/144 | 23/24 |

학습 정확도는 암기/학습가능성 검사이며 독립 성능이 아니다. primitive24/24에서 scene 이후23/24로 떨어진 것도 보존한다.

## 새 calibration/eval 결과

모든 arm의 threshold를 calibration에서 먼저 결정한 뒤 eval 이미지 추론을 시작했다. 이후 threshold·학습량·가중치·정답을 바꾸지 않았다.

| arm | classifier steps | threshold | eval TP / FP / FN | precision | recall | 사전 연구 gate |
|---|---:|---:|---|---:|---:|---|
| scratch_scene300 | 300 | .85 | 69 / 1 / 3 | 98.57% | 95.83% | 실패: FP1 |
| pretrain300_scene300 | 600 | .85 | 69 / 1 / 3 | 98.57% | 95.83% | 실패: FP1 |
| scene300_scene300 | 600 | .95 | 71 / 0 / 1 | 100% | 98.61% | 합성 범위 통과 |

연구 gate는 eval precision1, recall≥.8, 각종류 recall≥.5, 음성FP0이다. 세 arm의 공통 후보는 eval72개를 모두 포함했고 추가 후보는0이었다. 음성4장도 모두 후보/출력0이다. 이는 해당 단순 음성 분포에 한정된다.

| 종류 | scratch TP / GT | pretrain TP / GT | 동일 계산량 TP / GT |
|---|---:|---:|---:|
| rectangle | 10/12 | 10/12 | 11/12 |
| rounded rectangle | 11/12 | 11/12 | 12/12 |
| ellipse | 12/12 | 12/12 | 12/12 |
| diamond | 12/12 | 12/12 | 12/12 |
| parallelogram | 12/12 | 12/12 | 12/12 |
| cylinder | 12/12 | 12/12 | 12/12 |

scratch와pretrain의 FP는 새 위치에 존재하지 않는 도형을 만든 것이 아니라, `r17-scene-eval-011`의 **직사각형을 둥근 직사각형으로 잘못 분류**한1개다. 이 preset 계약상 FP1/FN1이며 1px 위치 오차를 실패 처리한 것이 아니다. 동일 계산량 모델도 이 후보를 rounded로 예측했지만confidence.805로 .95기준 아래여서 생략했다. 따라서 남은FN1은 후보 누락이 아니라 종류 불확실성이다. 이미 본 eval에 맞춰 예외처리를 추가하지 않았다.

R16 대비 학습량·crop·채널·분류기·평가 모집단이 함께 바뀌었다. 따라서 이 결과만으로 특정 한 변경의 인과 효과를 고립하거나 R16의16.7%와 이번98.6%를 동일 모집단의 개선율로 계산하지 않는다. 선학습 유무의 직접 대조는 **R17 내부 세 arm**이다. 단일 seed와12개 scene이므로 통계적 우월성·보편적 일반화를 주장하지 않는다.

## 실제 PowerPoint 육안 확인

48개 결과 PPT를 실제 COM으로 렌더하고, source와 세 arm을 나란히 놓은16개 보드를 모두 직접 확인했다. XML native 객체 수211개가 예측 수와 일치하고 PPT/render/보드 SHA가 일치한다. 래스터 삽입은 없다.

- [대표 장면000](C:/vs/ImageToEditablePPT/artifacts/region-image-only-r17/com-v1/r17-scene-eval-000.png): 여섯 종류와 상대 위치가 모두 남는다. R16처럼 마름모 하나만 남는 출력과는 시각적으로 다르다.
- [장면004](C:/vs/ImageToEditablePPT/artifacts/region-image-only-r17/com-v1/r17-scene-eval-004.png): scratch/pretrain은 우하단 직사각형을 생략하지만 계산량 대조는 복원한다.
- [잔여 오류 장면011](C:/vs/ImageToEditablePPT/artifacts/region-image-only-r17/com-v1/r17-scene-eval-011.png): scratch/pretrain은 좌측 중간 직사각형의 모서리를 둥글게 만들고, 계산량 대조는 그 도형을 비운다.
- 크기·위치의 작은 차이와 기본preset 곡률 차이는 남는다. OCR·연결·원본fill·adjustment회귀는 범위 밖이므로 본래 라벨/채움이 없는 결과다. 편집 가능한 도형 초안이지 완성 슬라이드가 아니다. 실제 사람의 수정 시간을 재지 않았으므로 시간 절약률은 주장하지 않는다.

## 복잡 원본 진단: 합성 통과를 제품 승인으로 오인하지 않기

formal 결과를 동결한 다음, 기존 공개된 개발용 CogBot 원본에 계산량 대조 모델과 calibration의.95를 그대로 적용했다. 새 모델 선택용 평가가 아니라 **후속 적용 한계 진단**이다. source/GT를 고쳐 넣지 않았다.

[실제 원본/COM 비교](C:/vs/ImageToEditablePPT/artifacts/region-image-only-r17/audit-v1/original-comparison.png)와 [후보별 RGB/occupancy crop](C:/vs/ImageToEditablePPT/artifacts/region-image-only-r17/audit-v1/original-candidate-crops.png)을 직접 확인했다.

- 예측 후보34개 중24개를 모두 마름모로 출력했다. 원본의 해당 구조와 맞지 않는 잘못된 결과다. 높은softmax confidence(.96이상인 잘못된 예 다수)가 올바른 구조의 증거가 되지 않았다.
- 후보 crop에는 `CogBot`, `PERCEIVE`, `Chunks`, `RETRIEVE`, 문단·아이콘 조각과 큰 병합 영역이 들어 있다. 온전한 닫힌 카드 대신 글자 잉크를 객체로 보고 있다는 것을 시각적으로 확인했다.
- RGB-only 후보 계산이 끝난 뒤 기존 수동 개발 ledger의17개 주요 노드 bbox에 **종류 무시 IoU≥.5**로 매칭했다. 후보 coverage는2TP/32FP/15FN이다. 이 ledger는 독립 정답이 아니고 모든 구조의 완전한 목록도 아니므로 일반 성능으로 보고하지 않는다. 다만 대부분 주요 노드가 후보 단계에서 이미 빠졌다는 진단 근거다.
- 최종24개 마름모는 주요 노드 종류도 복원하지 못한다. 합성에서의 후보72/72는 복잡 원본으로 이어지지 않는다. 기존 제품 출력을 이 모델로 대체하지 않았다.

**현재 확인된 병목:** 복잡 원본에서는 분류기 이전의 후보 검출이 무너진다. 그리고6종만 학습한 분류기에 구조가 아닌 crop을 넣어도 어떤 종류로든 자신 있게 분류한다. 단순한 classifier 학습량 증가나 confidence threshold 조절만으로 고칠 문제라고 보지 않는다.

**아직 가설인 원인:** 흰 카드/색 배경과 학습의 색 도형/흰 배경 차이, 원본2760×1504를240×152로 줄이는 과정, 내부 문단·아이콘·계층 구조의 부재가 각각 얼마나 기여했는지는 분리 실험하지 않았다. 이들 모두를 확정 원인으로 단정하지 않는다.

## 다음 우선순위

다음은 별도 버전으로 고정할 연구 방향이며 현재 eval의 점수를 구제하기 위해 실행한 수정이 아니다.

1. **구조 후보를 거부할 학습과 평가를 먼저 만든다.** 단독 닫힌 도형뿐 아니라 실제 PPT 문단·열린 선·장식/아이콘 역할·배경 조각 등 hard negative를 넣고, 후보가 유효 구조인지와6종 중 무엇인지를 분리한다. 단지7번째 class를 추가하면 해결된다고 가정하지 않는다. source 객체 종류와 구조 역할 정답을 구분한다.
2. **후보 recall과 분류 정확도를 분리해서 개선한다.** 온전한 후보가 없는15/17 주요 노드 문제는 classifier로 고칠 수 없다. 흰/무채움 카드, 색 배경, 내부 텍스트, 여러 객체 크기와 nested/container를 가진 source PPT 정답쌍을 만든다. union occupancy connected component만으로 서로 닿거나 포함된 객체를 분리할 수 없다는 한계도 평가한다.
3. **해상도·분포·인스턴스 문제를 한꺼번에 바꾸지 않는다.** 기존 분류기를 고정한 후보 진단, 기존 후보를 고정한 유효성 거부 진단을 별개로 비교한다. 다중 해상도/타일 또는 instance/boundary 감독은 candidate coverage 증가와 false candidate 변화로 선택한다. GT crop 성공을 실제 후보 성공으로 대체하지 않는다.
4. **새 구조·스타일 분리 평가를 만든 뒤에만 다시 승인한다.** 이번 R17 eval과 CogBot 원본은 이후 개발 진단으로만 사용한다. 새 eval은 slide/생성 레시피 단위로 분리하고 실제 COM 결과를 확인한다. 이 경계가 통과하기 전에는 관계 GNN이나 production 통합을 늘리지 않는다.

우선순위는 더 많은 primitive 선학습이 아니라 **실제 구조 후보 검출·비구조 거부·독립 복잡도 검증**이다. 작은 합성 성공은 보존하되 연구 전체가 성공했다고 부르지 않는다.

## 검증과 동결 증거

제외 없는 전체 회귀는 **1405 passed / 6 failed / 2 xfailed**, 기존 경고9개다. 실패6개는 R16에서 확인한 동일한 `test_source_centerline.py` 사례이고 이번에 구현/허용오차를 변경하지 않았다. 새 객체 crop/종류 분류 테스트와 R16 테스트 합계6개는 통과했다. 전체 녹색으로 보고하지 않는다.

독립 데이터·코드 감사, 실행 전후 SHA, 별도RGB-only 예측 동일성,48PPT native/COM 확인, 복잡 원본1PPT COM/후보 진단을 완료했다. COM 슬롯은 반환했다.

데이터 manifest: `C:/Users/lpaiu/.codex/worktrees/9cae/ImageToEditablePPT/artifacts/r17-ppt-primitive-data-v1/dataset_manifest.json`

SHA: `36e2c3a5c9a43774bb8d64657f6a4147236699edc34129b7e28cd9c920f25d96`

root 증거는 `C:/vs/ImageToEditablePPT/artifacts/region-image-only-r17/` 아래에 보존한다.

| 증거 | SHA256 |
|---|---|
| positive-v1/positive.json | 158bf4e4091200b74635cb33a4c4595c0151918050627cb8cd5a184a0432ca45 |
| positive-v1/lock.json | 8940c3742406acfad11f78bc2d0bb99f6b54694b688466205150af16f5e14735 |
| training-v1/training.json | 6c0a61127e97f41452aa36754debfbd70d7fc4dba0eee9d78164fab60890e750 |
| training-v1/lock.json | d805c4ed443fe89161d49c068e5bf28c4fc4580985c034a0245af5f1e2a146ac |
| eval-v1/results.json | 8dcf34160b78899c2f00700a19a1a09518c1bb03588396e9b0de41bdf20980d2 |
| eval-v1/calibration.json | 65919af2e919a3d91528fe9b644ca23e39eb62ac007c1f87eed47c65af9431ac |
| eval-v1/lock.json | 9652f4655c094d15793556bde9d94bbb942700f7018346ff6313eb0c09126a22 |
| com-v1/audit.json | 3eb2a9634d0fbd0f73f358e7d2ca1a48b7a26af57a5cf72062b97848ed89ac1c |
| audit-v1/audit.json | 3cb8b50115d9e5599f834abe8d6d833a147cc3d08a19cbf14f8dfa34c58c6035 |
| original-diagnostic-v1/result.json | 221358c70b890ac61900f7c608e271c32b80bf4702403b329aef268d8025c40f |

재현 도구는 `r17_object_primitive.py`의 positive→train→evaluate→predict, 기존 `r16_primitive_visual_audit.py`와 COM renderer, 새 `r17_result_audit.py`다. 새 출력 폴더에만 실행하며 역사 lock을 무시하거나 실패 artifact를 덮어쓰지 않는다.
