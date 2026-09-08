# R9-C v2: 픽셀 면적 지지와 래스터 기대값

## 이전 실패 보존 및 변경 범위

v1의29 passed/6 failed 및 code/test SHA는 그대로 보존한다. v2는 별도 연구 모듈과
별도 테스트다. owner/방향 고정, 원본 stroke 관측, 두 text-only owner의 단일 무방향
성분만 적용하는 범위와 모든 수치 기준은 v1과 같다. 제품 코드·4px gate는 바꾸지 않는다.

변경은 다음 두 좌표 계약에 한정한다.

1. 연결 지지율은 정수 픽셀 중심이 들어간 subpixel bin 수가 아니라 **선택된 물리적
   픽셀 cell의 주축 투영 구간 합집합 길이 / 전체 투영 span**이다.
   중심 `(x,y)`의 cell은 `[x-.5,x+.5]×[y-.5,y+.5]`이고, 단위 주축 `(vx,vy)`에 대한
   반폭은 `.5*(|vx|+|vy|)`다. 겹친 구간은 병합한다. 원본 픽셀을 새로 만들지 않는다.
   지지율 ≥.90 및 최대 비지지 gap ≤2s는 유지한다. span ≥24s, 직선성 잔차, endpoint
   외삽 등은 v1처럼 원본 중심점 기준으로 계산한다.
2. fixture의 기대 직선은 알고리즘 출력이 아닌 **실제로 rasterizer에 전달한 정수화된
   두 점**에서 독립 해석 기하로 계산한다. 원 bbox와 교차시키며 tolerance .8px는
   유지한다. 정수화 전 이상적 연속 선과 실제 관측 선은 별도 기록한다.

## gate

v1과 동일한24개 clean positive와10개 negative, 선분 helper를 유지한다. 픽셀 cell의
연속 투영/명백한 gap을 확인하는 단위 대조를 추가한다. wrapper에서는 normal box,
directed arrow, multi-owner/fanout, 다른 source의 연결이 전혀 바뀌지 않아야 한다.
적용되는 경우에도 path 외 모든 semantic 필드는 동일해야 한다.

첫 실행 전에 spec/module/test를 커밋해 고정한다. 24개 positive와 모든 negative 및
wrapper gate가 통과해야 실제15장 실행을 허용한다. failure가 나오면 v2 실패로 기록하고
같은 이름으로 조정하지 않는다. 기존 v1 실패를 v2 성적으로 대체하거나 xfail로 숨기지 않는다.

## 실제 대조

gate 통과 후 동결 A-T15개만 사용한다. 기존 trace를 먼저 정확히 재현한 다음 C-v2만
적용한다. node/OCR/방향/owner집합은 고정, D suppression은 끈다. GT는 별도 평가에서만
읽고, 실제 native PPT를 렌더해 육안 검토한다. 원본 중심을 더 잘 따르더라도 중복 owner
및 잘못된 방향 문제는 남을 수 있다. 신규 FP/기권/변경된 경로를 분리해 보고한다.
