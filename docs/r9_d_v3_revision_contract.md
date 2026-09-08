# D-v3 revision 1: raster-valid expectations and shared safety mechanisms

## 범위

D-v1/v2 원 기록을 보존하고 새 revision에서 오류를 고친다. 이 작업은 연구용 D-v3 controls까지이며 실제 15개/C 결합/학습/COM은 루트와 조정한다. 실패 동결은 checkpoint이고 종료 조건이 아니다. 원 PP의 두 glyph 방향/대표 선택은 루트와 공통 관측 API로 연결한다.

신규 관측 함수는 RGB와 예측 bbox만 읽는다. fixture의 reference RGB, 의미 역할, 기대값은 별도 evaluator에만 있다. 원 threshold를 통과시키려고 기대값을 바꾸지 않는다. 대신 **최종 raster 자체에서 검사할 정보가 남았는지**를 관측 실행 전에 고정한다. 새로운 D-v3 파일 하나에서 정수 밝기, contact 보호, support-loss 판정 함수를 공유하며 v2를 매번 복제한 v3a/v3b 모듈을 만들지 않는다. revision마다 code/fixture/expectation SHA를 잠근다.

## 정수 밝기 계약

`L=2126R+7152G+722B`를 signed int64로 계산한다. 단위는 1/10000 luminance이다. 배경 median이 두 값 사이일 수 있으므로 `median2 = sorted_ring[(n-1)//2] + sorted_ring[n//2]`, `contrast2=max(0,median2-2L)`로 정의한다. core80/weak12 판정은 각각 contrast2≥1,600,000 / 240,000의 **정수 비교**다. epsilon이나 데이터별 threshold 변경은 없다. scalar, 1D, crop, contiguous/noncontiguous 배열과 채널별 극값을 검사한다.

core/weak mask 밖에도 `0<contrast2<240000`인 **residual contrast**를 별도 기록한다. 이를 확정 glyph로 승격하지 않는다. core-connected component의 경계 약화 또는 행 가까운 orphan이 후보 선택으로 사라질 수 있으면 unresolved로 기권한다. weak12를 낮춰 성능을 맞추는 규칙이 아니라, 관측 mask 바깥 정보가 없다는 잘못된 결론을 막는 불확실성 검사다.

모든 1px을 의미 있다고 선언하지 않는다. 배경 speck 예외는 v2처럼 core 없고 area≤max(1,s²), contrast≤24, 행 bbox에서 2 glyph-height보다 멀며 행 band 밖인 성분에 한정한다. 행 가까운 작은 점은 punctuation/noise 의미가 미확정이므로 보호 기권한다. 동일 component의 미약한 AA fringe는 아래 경계 계약으로 다룬다.

## padding과 boundary 계약의 단일화

raw padding의 부호를 곧바로 eligibility로 사용하지 않는다. pixel-center 포함으로 support가 모두 남으면 음수 padding≤.5px는 cell extent와 float bbox의 표시 차이다. 이를 실제 손실로 세지 않는다.

후보별 각 connected support에 대해 retained core coverage≥.98, weak coverage≥.95, whole-component 소실 0을 요구한다. 일부 잃는 점이 있으면 원본 bbox 경계까지 거리≤1 원본 px여야 한다. residual fringe는 동일 core-containing component에 붙어 있고 위 core/weak 조건을 만족할 때에만 경계량 차이로 허용한다. core가 전혀 없는 orphan 성분은 근접 의미를 알 수 없으므로 whole/partial 소실을 기권한다. 음수 padding이 이 support 검사와 무관하게 허용되거나 금지되는 두 번째 규칙을 만들지 않는다.

이 규칙은 1px 무손실 이동과 실제 component 소실을 구별한다. core/.98와 weak/.95는 v2 값을 유지한다. 음수 padding 및 actual loss 조건을 각각 sidecar에 기록하고, eligibility는 이 단일 함수에서만 계산한다.

## explicit shaft–glyph contact 보호

shaft candidate는 기존 긴 외부 성분 TLS 관측으로 찾되, 제거 전에 다음을 기록한다.

1. shaft mask와 retained glyph/residual mask가 8-neighbour로 접촉하면 `shaft_glyph_contact`.
2. component가 source weak/core에서 분리/접촉 상태가 다르면 `shaft_glyph_uncertain`.
3. 한 connected component에 glyph-like 성분과 shaft가 이미 붙어 있어 단순 두 mask 인접 검사가 불가능한 경우, owner 내부 core component와 외부 잔여 원본 ink의 경계 접촉도 검사한다. 이를 제거한 선의 단독 evidence로 간주하지 않는다.

contact는 원본 ink에서 계산하고 결과 mask에 morphology를 적용하지 않는다. neighbour dilation은 거리 질의로만 사용한다. contact면 suppression을 기권하며 문자를 절단하거나 보조 객체를 만들지 않는다. 내부/외부 구분은 검사 근거일 뿐 모든 bbox를 관통하는 선이 글자라는 주장은 아니다. 보수적 기권은 기록한다.

## 최종 raster 이후 expectation 생성

의미 perturbation control은 같은 renderer/scale/AA를 거친 baseline RGB와 변경 RGB를 쌍으로 저장한다. `added=max(0,L_reference-L_changed)`를 정수로 계산한다. 추가 획의 존재를 base 이름이나 연속좌표에서 가정하지 않는다.

- added pixel이 없으면 `rasterized_away`: 실제 추가 내용 손실 control에서 제외하고 무손실/양자화 대조로 별도 집계한다. 원 v2 preserve 결과는 historical로 그대로 기록한다.
- 최대 added가 양수일 때 feature body는 `2*added>=max(added)`인 pixel 집합이다. 이 **feature-relative 반치폭**은 observer core80/weak12와 독립이며 렌더링된 perturbation 본체와 낮은 AA halo를 구별하는 검사 정의다. 생물학적 의미/가독성 판단이 아니다.
- 모든 후보가 feature body를 포함하면 `body_shared`: 어느 기존 bbox를 선택해도 그 feature body를 잃지 않는다. bbox 밖 낮은 halo만의 차이는 geometry/uncertainty 열에 남긴다.
- 일부 후보만 body를 포함하면 각 keep-set의 body 보존 여부를 검사해 허용 집합을 고정한다. body 없는 후보만 남기는 선택은 support-loss 위반이다. 더 큰 bbox나 둘 다 유지하는 선택도 통과 가능하며 무조건 preserve를 강제하지 않는다.
- 얇은 orphan 점/획의 body 전체가 사라지는 경우는 면적이 1px이어도 loss다. 먼 speck로 사전 구성한 noise control은 위 예외의 **위치/contrast/면적 조건을 최종 raster에서 독립 검증**한 경우에만 noise 대조로 인정한다.

반치폭은 “실제 semantic 문자”의 GT가 아니다. 독립 owner control의 객체 수 기대는 생성기의 별도 구성에서 유지한다. 범위 위반, body 손실, 전체 pixel fringe 차이, 사람의 의미 판정 미확정을 분리한다. expectation 생성에는 observer 결과/선택 ID를 읽지 않는다.

## controls와 gate

v1/v2 원 결과는 변경하지 않는다. 신규 D-v3 실행은 v2 입력 replay를 유지하면서 old expectation 위반과 raster-valid expectation 위반을 각각 집계한다. 새 숫자 메커니즘 controls는 RGB gray 242/243/244 및 색 극값, row/crop/array layout, 짝수 ring median을 포함한다. contact controls는 touching/separated shaft–glyph, 동일 component 접촉, weak bridge, 관통선과 닫힌 loop를 포함한다. boundary controls는 cell extent만 음수인 경우, core 일부 경계량, whole tiny 소실, 강한 partial 소실, 먼 speck를 포함한다.

code와 생성된 전체 fixture/expectation SHA 및 정확한 개수를 최초 관측 전에 잠근다. threshold/기대값을 결과로 튜닝하지 않는다. 명백한 계산·fixture 구현 bug는 원 revision과 실패를 보존하고 새 build revision에서 수정한다. 정의 자체가 부족하면 다음 계약 revision을 제안해 루트와 연결한다.

G0: 정수 경계 정확성·입력 경계·파일 IO. G1: 무개입 불변, score/order/ID, crop/full, contact/boundary 명세. G2: raster-valid body/독립 owner 손실 0, 지원 범위 위반 0, 새 clean 및 검증된 noise-positive에서 적어도 한 실효 선택. oldpositive 기권은 별도 표로 남긴다. PP의 두 glyph 지원을 통과로 주장하지 않고 루트 대표 선택 연구에 관측/보호 함수를 제공한다.
