# R9-C v2 결과 및 두 트랙 통합 판정

## 결론

원본 선 중심 관측은 제한된 개발 사례에서 유효했다. 고정 A-T 15장 중
`tree_1302_00079`의 native 연결이 1개에서 7개로 늘었고 신규 6개는 모두 정답 관계다.
실제 PowerPoint 렌더에서도 트리 분기가 읽히는 것을 확인했다. 그러나 다른 14장에는
개선이 없으며 전체 오답 연결 5개와 누락 35개가 남는다. **연구상 부분 개선이며 제품 승인 아니다.**

별도 작업의 R9-D v1은 보존해야 할 owner를 376건 제거하여 기각했다.
두 개입을 결합하지 않았고 제품 runtime·native 4px gate는 수정하지 않았다.

## 잠금과 입력 경계

- v1의 29 passed / 6 failed를 보존했다. v2 명세는 `2f1c45f`, 모듈·대조는
  `15f761b`, 실제 실행기는 `1a20cc7`에서 각각 실행 전 고정했다.
- v2의 변경은 물리적 픽셀 cell 투영 지지율과 실제 래스터 정수 좌표 기대값이다.
  수치 tolerance를 완화하지 않았다. 24 positive·10 negative·helper/범위 대조 총43개 통과 후 실제15장에 진입했다.
- 고정 예측 owner와 OCR scene, 해당 RGB만 각 추론 worker에 전달했다. annotation,
  원본 정답 PPT, offline target은 입력하지 않았다. GT는 PPT 생성·렌더 이후 별도 평가에서 읽었다.
- 기존 trace 51개를 전 필드 정확히 재현한 뒤 적용했다. node bbox/ID/kind/label,
  source/target/화살촉/기타 connector 필드는 모두 불변이며 path만 바뀌었다.
- 파일 접근 Python audit hook에서 차단0건. OS sandbox 전체 보장으로 해석하지 않는다.
  데이터는 기존 모델 선택에 사용된 합성 validation 15장으로, 미관측 논문 일반화 검증이 아니다.

## 수치와 불변성

| 항목 | A-T 동결 기준 | C-v2 |
|---|---:|---:|
| native 정답 연결 | 26 | 32 |
| native 오답 연결 | 5 | 5 |
| native 누락 연결 | 41 | 35 |
| native fit 기권 | 20 | 14 |
| matched label 정답/오답/공백 | 82/1/8 | 82/1/8 |

trace 관계 자체는 35 TP / 16 FP / 32 FN으로 동일하다. 새로운 관계를 발견한 것이 아니라,
이미 추적된 올바른 관계 6개가 출력 가능한 직선 표현을 얻었다.

판정 51개 중 범위 밖43개, raw 직선성 부족 기권1개, 중심선 지지 통과7개다.
**실제 좌표 변경은6개**다. 나머지 통과1개인 수직선은 기존 좌표와 완전히 같다.
결과 동결용 후처리 검사기의 최초 `7개 변경` 가정은 실패했으며, 개별 path 비교로 이 차이를
확인해 집계만 정정했다. 추론·임계값·PPT·평가 결과는 재실행하거나 수정하지 않았다.

나머지14개 실제 native 렌더 PNG는 A-T와 SHA가 완전히 같다.
PPT 객체/endpoint binding 및 raster 부재는 기존 별도 evaluator로 검증했다.
자동 XML/렌더 검증은 사람이 객체를 움직이고 고친 사용성 시험을 대신하지 않는다.

## 직접 육안 검토

15개 원본/실제 PPT 비교를 contact sheet 3장으로 모두 확인하고 트리3장은 개별 확대 확인했다.

- `tree_00079`: DP에서 cat/Adj로, 두 하위 분기로 이어지는 대각선6개가 복구됐다.
  기존 ROOT–runs 수직선도 유지되어 전체7개 관계가 보인다. 선 두께와 라벨 간격은 원본과
  다르지만 구조를 읽고 수정하는 데 유용한 부분 복원이다. 원본 bitmap 삽입이 아니다.
- `tree_00036`: CP/CP. 겹침, dog/V/Adj 라벨 누락 및 대부분의 연결 누락이 남는다.
  남은 CP→V도 owner 매칭상 오답이며 이번 범위 밖이다.
- `tree_00149`: Adj/PP 중복 글자와 겹치는 연결, ROOT/CP/cat 쪽 분기 누락 및 V 공백이 남는다.
  중심선을 바꾸는 것만으로 잘못된 owner 집합을 고칠 수 없다.
- block/cycle/graph: 대각선·관계 누락과 일부 오방향이 남는다. graph의 원→사각형 문제는
  기존 annotation kind와 실제 PPT preset 불일치 한계도 상속한다. exact-kind 숫자로 가리지 않는다.
- layered stack/table: 기존의 읽을 수 있는 부분 구조는 유지된다. 흐린 테두리와 스타일 차이는
  남지만 이번 개입의 성과도 퇴행도 아니다.

## 별도 R9-D 트랙 교차 확인

작업 `PPT 정답쌍 기반 이미지 단독 학습·평가 트랙`의 최종4커밋을 순서대로 통합했다.
원본 결과 파일 SHA, 관측 모듈 SHA 및 결과 record 집계는 이 작업에서 독립 확인했다.
3,656건 중 3,280 pass / 376 false suppression이다. 전체 geometry 실행을 여기서 다시 돌린 것은 아니다.
상세 원인·반례·실행환경 실패 이력은 `r9_duplicate_owner_v1_results.md`에 있다.

현재 해석은 다음과 같다. 회전/세로쓰기 미지원 선언을 실제 관측으로 판별하지 못했고,
희미한 획·작은 punctuation 손실을 mask 합의가 가렸다. 원 PP 사례는 정답 owner 선택 성공이
아니라 기권으로 보존한 것이다. 3,656 records는 498개 서로 다른 PNG SHA의 변형 대조이며
독립 이미지 3,656개가 아니다. 실제15장 D-S나 C+D 결합은 실행하지 않았다.

## 검증 및 후속 우선순위

- 현재 C-v2 + D 입력경계 unit: 55 passed.
- 전체 pytest: **542 passed / 6 failed / 2 xfailed / 9 warnings**.
  6개 실패는 동결 C-v1 대조이며 감추거나 xfail로 바꾸지 않았다. 기존2 xfail은 별도의
  visual connector 방향 알려진 실패다. 전체 test suite green이라고 보고하지 않는다.
- 신규 학습 실험·배포·사용자 인간 수정 시간 측정은 하지 않았다. 전체 pytest에 포함된
  기존 학습 smoke test는 실행됐지만 이를 연구 모델 개선 결과로 사용하지 않는다.

다음은 두 문제를 다시 구분해야 한다. C는 올바른 owner 사이의 선 표현을 개선하는 제한된
후보로 보존한다. D는 현재 삭제 규칙을 승격하지 않고, 작은/밝은 잉크 손실과 지원 밖 방향을
실제로 거부할 수 있는지부터 새 명세에서 다룬다. detector 자체 bbox/중복 품질 개선은
PPT 정답쌍 기반 offline 감독의 별도 연구 항목이다. 어떤 경로든 추론 입력은 이미지이며,
정답쌍을 렌더링 정답으로 공급하는 방식으로 돌아가지 않는다.

산출물은 `benchmarks/r9_centerline_v2_results.json`에 SHA로 묶었다.
PPT/렌더/IO/audit는 `artifacts/region-source-evidence-r9/centerline-v2`에 보존한다.
프로덕션 승격 전에는 고정 미관측 사례, 직접 편집 검증, 실제 인간 수정 비용 측정이 필요하다.
