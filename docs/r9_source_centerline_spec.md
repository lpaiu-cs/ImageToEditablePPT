# R9-C v1: 원본 선 중심 관측의 제한된 대조

## 연구선과 사전 고정

R8 연구선은 `531866f`에 동결했다. 새 `codex/source-evidence-r9`에서 R9-D 중복 owner
실험과 독립적으로 진행한다. R9-C는 owner 집합·bbox·ID·종류·OCR·관계 방향을 고정하고
기존에 추적된 일부 경로만 원본 선 중심으로 관측한다. 새 연결을 탐색하거나 GT/PPT/
offline target을 읽지 않는다. 기존 tracer/emitter/4px native gate는 변경하지 않는다.

진단 근거는 `trace_fit_diagnosis_r8a.md`다. 아래 숫자는 이미 관찰한 개발 사례에서
출발한 최초 후보 설정이며 미관측 최적값이 아니다. 반례 실패 시 v1 실패를 보존하고
같은 이름으로 임계값을 바꿔 통과시키지 않는다.

## 적용 대상

기존 RGB 및 예측 owner로 `region.trace_scene`을 실행한다. 그 출력의 component와
connector 대응을 사용한다. 다음 모두를 만족할 때만 후보로 삼는다.

- 서로 다른 두 owner만 접촉한 component이고, 해당 component에서 연결이 정확히 1개다.
- 두 owner 모두 예측 `label_anchor`이며 기존 연결은 무방향이다.
- source가 `r3_stroke_trace`다. multi-owner/fanout/방향 화살표에는 적용하지 않는다.
- 유한·정상 이미지/bbox/경로이며 관측 픽셀이 있다.

범위 밖 또는 관측 부족이면 원래 connector를 그대로 보존한다. 기권은 원래 연결의
방향이나 native 지원을 승인하는 의미가 아니다. R9-D suppression은 꺼둔다.

## 원본 픽셀 관측과 판정

좌표는 원본 RGB이며 `s=H/360`. 기존 tracer와 동일한 정수 픽셀 중심 `(x,y)`를 사용한다.
연결용 repair/dilation mask의 component와, 같은 RGB의 repair/dilation 이전 `stroke_mask`
선택 픽셀을 교차한다. 이 방법은 source stroke 선택기의 한계를 상속한다.

1. 픽셀 최소 12개. PCA/TLS 최소제곱 직선을 구한다. 관측 span은 주축 투영 max−min이다.
2. span ≥24s, 수직거리 p95 ≤2s, 최대거리 ≤3s. PCA 큰/작은 분산 비가 4 이하이면 기권한다.
3. span을 폭 s의 bin으로 나눠 원본 잉크 지지를 검사한다. 채워진 bin 비율 ≥.90,
   연속 빈 bin 길이 ≤2. 단절을 새 선으로 연결하지 않는다.
4. TLS 직선이 기존 두 bbox 경계와 교차해야 한다. 각 owner에서 기존 endpoint에 가장
   가까운 교점을 선택한다. endpoint 이동 ≤6s이며, 관측 span 밖 외삽은 각 끝 ≤8s다.
5. 교점을 잇는 선분이 다른 예측 node의 bbox 내부와 교차하면 기권한다. 기존 두 owner
   외의 bbox와 경계만 스치는 경우도 보수적으로 차단한다.
6. 모든 조건을 통과하면 기존 connector의 path_points만 두 교점으로 교체한다.
   ID/source/target/kind/신뢰도/화살촉 플래그는 그대로다. 판정 사유·픽셀수·잔차·지지율·
   span·endpoint 변위·이전/새 path를 sidecar에 남긴다. 직선이라는 사실로 방향을 추측하지 않는다.

TLS 잔차와 native fitter의 양방향 최대 거리 및 정규화 단위를 혼동하지 않는다.
기존 native 4px gate를 그대로 실행하며 후보 경로를 새로 정의했다는 사실을 명시한다.

## 사전 반례와 gate

반례는 GT 없는 관측 함수와 별도 테스트 기대값으로 나눈다. RGB 선 fixture는 모델 없이
만들며 OpenCV 버전과 파일/코드 SHA를 기록한다. 모든 fixture 목록/설정은 첫 실행 전에
고정한다. 초기 정방향/역순 × 수평/수직/양방향 대각선 × scale .75/1/1.5의 24개
깨끗한 직선 사례를 positive로 사용한다. 검은 굵기3s 선, 흰 배경이다.

negative는 빈 픽셀, 짧은 선, 긴 단절, 엘보, 곡선, 평행 이중 선, owner를 빗나가는
직선, 큰 endpoint 이동, 긴 외삽, 제3 owner 교차를 고정한다. 조건 통과를 위해 픽셀이나
endpoint를 몰래 제거하지 않는다. 별도 wrapper 회귀에서 방향 화살표/일반 box/fanout은
불변이어야 한다. 반환된 경로 외 의미 필드는 모든 경우 불변이어야 한다.

positive 24개 모두 올바른 교점 직선, negative 모두 기권, 범위 밖 불변을 요구한다.
하나라도 실패하면 실제 15장 대조에 진입하지 않는다. all-abstain은 positive에서 실패다.
이 반례 통과는 일반적인 선 복원 정확도의 증명이 아니다.

## 실제 개발 대조(반례 통과 후)

고정 A-T 15개 RGB/scene으로 현재 trace를 먼저 재현하고 connector 전체 필드 동일성을
검사한다. R9-C만 적용하여 기존 native label-anchor adapter로 출력한다. OCR은 고정
라벨을 운반하며 새 인식/중복 제거는 없다. 각 source-only worker의 파일 접근을 기록한다.

원래 node/라벨/관계 매칭 계약으로 trace와 native TP/FP/FN을 평가하고 15개 실제 PPT
렌더를 육안 확인한다. bbox/라벨/owner/direction 불변, 변경 경로/출력 증가/새 FP를
분리한다. 실패 사례를 제외하거나 새 FP를 평가 규칙 수정으로 구제하지 않는다.
결합 실험은 D와 C 각각의 결과를 본 다음 별도 명세로 다룬다. 제품 승격·미관측 일반화·
인간 수정 시간 절감은 이번 개발 대조로 승인하지 않는다.
