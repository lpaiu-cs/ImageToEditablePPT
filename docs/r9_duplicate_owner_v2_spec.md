# R9-D v2 계약: 위치 오차와 관측 정보 손실을 분리

## 상태와 변경 목적

이 문서는 구현 전 검토용 명세다. 코드 구현·실행·새 fixture 생성·학습·COM·C와의 결합은 수행하지 않는다. 루트 검토와 후속 지시 이후에만 구현한다. D-v1의 3,656건 중 376건 실패, 원 코드/기대값/결과를 그대로 보존한다. v2 통과로 v1을 소급 구제하지 않는다.

사용자 기준은 **1px 위치 차이 자체가 실용 실패는 아니지만 실제 글자·관계·객체 손실은 별개**라는 것이다. 따라서 모든 1px을 의미정보로 강제하지도, 작은 차이를 일괄 noise로 버리지도 않는다. 이미지로 의미를 구별할 수 없으면 불확실성을 표시하고 suppression을 기권한다. 객체 수를 28→25로 맞추는 목표는 없다.

v1에서 드러난 네 경계를 바꾼다: (1) 지원 방향을 측정하지 않은 선언, (2) 세 dark threshold에서 공통으로 누락된 밝은 획, (3) 기록만 하고 판정에서 제외한 tiny 점, (4) crop 높이를 원본 높이로 사용한 scale 변화. 기존 bbox 선택만 허용하며 score tie-break, .43 NMS, 문자만 병합, GT alias, 새 평균/합집합 bbox는 금지한다.

## 1. 입력과 좌표 계약

관측 입력은 원본 RGB uint8와 예측 owner의 opaque ID/semantic kind/bbox/confidence만이다. OCR 문자·GT/annotation·PPT·connector는 관측 입력에 없다. 관측 함수는 파일을 읽지 않는다. 외부 파일 경계는 전용 실행기가 검증한다.

정식 진입점은 **전체 원본 RGB**다. `s=원본 H/360`을 한 번 계산한다. 내부 crop은 `(origin_xy, full_size, s)`를 유지하며 모든 pixel center와 bbox는 원본 좌표로 환산한다. crop 높이로 s를 재계산하지 않는다. 단독 crop을 새 원본인 것처럼 넣어 같은 결과를 기대하는 API는 지원하지 않는다.

crop/full control은 동일 전체 RGB에서 같은 관측 window를 내부적으로 추출하는 두 계산 경로를 비교한다. crop 경로에는 runner가 전체 RGB로 검증한 원점/원본 크기/원본 SHA를 운반한다. 이 metadata는 좌표 정보이지 GT가 아니다. source 크기가 없는 외부 crop은 `missing_frame_context` 오류다. 필요한 halo가 잘린 crop은 `insufficient_context`로 기권한다.

pixel center는 `(x+.5,y+.5)`, bbox 포함은 half-open이다. 관측 bbox는 변경하지 않는다. 길이 단위 `s`와 pixel cell 반폭 .5 원본 px를 구분한다. 정수화 전에 bbox를 움직여 coverage를 높이지 않는다. 출력 survivor bbox는 입력과 동일하다.

## 2. 두 단계 출력과 후보 범위

**V2-O**는 owner를 완전히 보존하고 관측/제안만 출력한다. **V2-S**는 동일 관측으로 승인된 cluster에서만 기존 owner를 제거한다. ambiguous owner와 연결을 같이 삭제하는 별도 정책은 없다. 실제 추적 전 적용 여부는 fixture gate 이후 별도 승인 범위다.

v1의 양의 bbox 교집합 candidate, 최대 4개 cluster, clique 요구, overlap chain 기권은 유지한다. IoU는 후보 설명값이며 삭제 threshold가 아니다. cluster 내부에는 동일 관측 정보의 중복 소유와 대표 bbox 선택을 별도 판정한다.

상태는 `unsupported_orientation`, `different_support`, `possible_information_loss`, `insufficient_context`, `representative_ambiguous`, `supported_duplicate` 등으로 구분한다. 같은 문자/같은 의미라는 확정은 하지 않는다.

## 3. 배경과 밝은 ink 관측

원본 luminance는 v1과 같은 Y 식을 사용한다. crop ring channel median/Y percentile을 기록하고 배경 median Y≥225, Y90−Y10≤30을 초기 지원 조건으로 유지한다. 복잡한 배경은 보수적으로 기권한다.

배경 `Y_bg=ring median` 대비 contrast `D=max(0,Y_bg−Y)`를 계산한다. **core**는 D≥80, **weak support**는 D≥12다. 이 수치는 최초 v2 fixture용 후보로 사전 고정하며 결과 후 같은 버전에서 튜닝하지 않는다. v1의 Y≤110/140/170 mask도 진단용으로 함께 저장하지만 결정 투표로 사용하지 않는다. core가 없는 밝은 글자만 있는 cluster는 `insufficient_core`로 기권하며 “글자 없음”으로 처리하지 않는다.

8-connected weak component 각각에 core 포함 여부, 면적, contrast min/median/max, 원본 좌표 bbox, owner별 포함량을 기록한다. core-connected weak component는 전체를 획 지원 영역으로 취급한다. core와 분리된 weak component도 삭제하지 않고 **orphan support**로 따로 둔다. v1 Il처럼 밝은 별도 획이 core와 연결되지 않아도 손실 검사 대상에 남는다.

shaft 분리는 v1의 긴 외부 성분 TLS 조건을 유지하되 core/weak 양쪽 관측을 기록한다. 긴 성분이 glyph와 닿거나 분리 결과가 core/weak에서 달라지면 `shaft_glyph_uncertain`으로 기권한다. 관측 안정화를 위해 글자를 dilation/closing으로 연결하거나 선을 잘라내지 않는다. 원본 M/S/U 및 weak/core mask는 모두 보존한다.

## 4. 회전·세로쓰기의 실제 지원 판정

지원 방향을 알 수 없는 single atom을 가로쓰기라고 기본 승인하지 않는다. 초기 v2는 **방향 근거가 있는 다중 atom 가로 행만** suppression 대상으로 제한한다. 이는 single glyph 복원을 개선했다는 주장이 아니라 판정 가능 범위를 좁힌 것이다.

shaft를 제외한 core-containing weak atom 중 높이 3s~24s, 면적≥2s²의 후보에서 중심점들을 구한다. 최소 3개 atom과 중심점 주축 span≥2×median atom 높이를 요구한다. 부족하면 `orientation_unobservable`로 유지한다. 단일 connected word처럼 한 atom으로 합쳐진 글자도 초기 범위에서는 유지한다.

중심점 TLS 주축의 가로축 대비 각도 θ를 구한다. 각 atom 중심은 pixel quantization 불확실성으로 x/y 각각 ±.5 원본 px 범위를 가진다고 보고, 양끝 중심의 최대 상대 변위 √2 px에 따른 보수적 각도 여유 `δ=atan2(sqrt(2), span)`을 사용한다. 이는 의미 오차 허용치가 아니라 방향 판정의 불확실성 한계다.

- `|θ|+δ≤5°`이고 중심점의 TLS 수직 잔차 max≤.25×median 높이일 때만 horizontal evidence 통과.
- `|θ|−δ>5°`이면 `unsupported_orientation`.
- 경계가 겹치면 `orientation_ambiguous`.

세로 배열은 각도 조건에 걸리며 ±15° 행도 관측으로 거부해야 한다. 최소 atom 수를 채우려고 punctuation을 큰 글자 atom으로 승격하지 않는다. 글자 각각만 회전하고 중심 행은 수평인 경우 이 조건만으로는 완전 판별할 수 없다. 이 추가 반례도 필수이며 잘못 승인하면 v2 실패로 남긴다. 사후 각도 heuristic을 추가해 같은 버전을 구제하지 않는다.

## 5. 작은 차이와 가능한 정보 손실

component 대응은 원본 crop의 동일 pixel support ID를 기준으로 한다. weak atom의 owner별 core coverage, weak coverage, bbox와 경계까지 거리, orphan support의 각 owner 포함량을 기록한다. 의미 문자 ID를 추정하지 않는다.

위치 차이는 다음처럼 분리한다.

1. **단순 bbox 경계 이동**: 기존 두 bbox가 동일 support component를 모두 포함하고, 한쪽만 잃는 component나 support topology 변화가 없다. bbox 1px 이동 그 자체는 실패도 삭제 근거도 아니다.
2. **동일 획의 경계량 차이**: 동일 component 일부가 pixel-cell 경계에서 달리 포함됨. 잃는 부분이 1 원본 px 폭의 bbox 경계 band 안에 있고, 각 core component의 retained coverage≥.98, weak coverage≥.95이며, component 전체가 사라지지 않아야 한다. 이를 `boundary_quantization_difference`로 기록한다. 조건에 맞아도 곧바로 동일 의미라고 확정하지 않는다.
3. **가능한 정보 손실**: 한 owner만 포함하는 core component, core 없는 orphan 획, punctuation 후보가 사라지거나 위 coverage 조건을 벗어남. 크기에 상관없이 `possible_information_loss`로 기권한다. 특히 component 전부를 잃는 것은 .98/.95 총면적 비율로 숨기지 않는다.

**모든 1px을 의미정보로 강제하지 않는 예외**도 명시한다. orphan 성분이 (a) core 없음, (b) area≤max(1,s²), (c) 최대 contrast≤24, (d) 관측 glyph 행 bbox로부터 거리>2×median atom 높이이며 모든 owner의 glyph 행 주변 band 밖인 경우에만 `isolated_low_contrast_background_speck`로 분류해 loss veto에서 제외한다. pixel 자체는 audit에 남긴다. 고대비 점, 글자 가까운 점, punctuation이 있을 법한 위치의 점은 이 예외에 해당하지 않는다. 배경 speck인지 점인지 구별할 근거가 부족하면 ambiguous이지 “그 점은 의미 있음”이라는 확정이 아니다.

한 픽셀이 실제 punctuation인지 원래 이미지에 없는 noise인지는 일반적으로 RGB만으로 확정할 수 없다. 이 계약의 약한 speck 예외도 반례를 통과해야 하며, 같은 RGB에 상반된 의미 expectation이 생기는 경우 식별 불가능성을 보고한다. 성공률을 위해 expectation을 고르지 않는다.

## 6. 동일 support와 대표 bbox 선택

모든 owner가 같은 core-containing atom 집합을 소유해야 한다. 별도 행/분리된 glyph 집합/전체와 부분 글자/서로 다른 orphan support가 있으면 유지한다. 중복 후보라도 위 정보 손실 검사 또는 방향 검사에 실패하면 representative 비교로 넘어가지 않는다.

선택 손실은 v1의 shaft_fraction, padding_excess, padding_asymmetry와 유일 dominance 구조를 유지한다. 다만 glyph bbox는 승인된 core-connected weak support 전체에서 계산하고, 정보 손실 veto는 손실 점수보다 우선한다. v1의 no-worse (.01,.05,.05), better (.05,.25,.25)는 초기 v2에서 그대로 둔다. 유일한 승자가 없으면 score가 높아도 유지한다. 같은 bbox tie도 유지한다.

survivor의 원 ID/bbox/kind/confidence는 그대로다. 작은 bbox가 padding 측면에서 좋더라도 밝은 획/작은 점을 잃으면 선택하지 않는다. PP det9/11은 det11 선택 또는 둘 다 유지가 허용되며 det9만 남기면 보호 경계 실패다. PP를 반드시 제거해야 통과하는 조건은 없다.

## 7. 기존 실패와 새 controls

fixture 생성·전체 조합·seed·font/renderer SHA·owner/expectation 목록은 실행 전에 잠근다. builder와 expectation reader를 observer와 분리한다. 원 annotation/PPT는 offline expectation에만 허용한다. 이번 문서에서는 fixture를 생성하거나 실행하지 않는다.

### 기존 v1 controls 보존

원본 3,656 records를 삭제/재라벨링하지 않고 그대로 replay한다. 원 결과와 v2 결과를 병렬 기록한다. 특히 376개 실패와 PP 8개를 별도 표로 유지한다. v1의 clean single-atom positive는 v2에서 방향 기권할 수 있으므로, v1 positive 결과는 historical comparison이며 v2 효과성 gate는 새 다중 atom positive로 따로 정의한다. 이러한 지원 범위 변경을 통과 건수 증가로 숨기지 않는다.

fanout 14건의 baseline 0관계도 그대로 둔다. owner 보존 96건과 baseline 정상 82건의 관계 보존 검증을 분리한다. 기존 AA flag가 font의 기본 AA를 끄지 못한 사실도 유지한다.

### 새 fixture 군과 기대 조건

| 군 | 구성 | 기준 |
|---|---|---|
| 방향이 관측되는 clean positive | 가로 행 3~5개 분리 atom, 동일 전체 glyph를 감싼 tight/loose bbox, 추가 정보 없음 | 적어도 한 clean 기본 장면에서 올바른 suppression. 전부 기권은 no-benefit |
| unsupported orientation | 위 동일 RGB/owner를 ±15°,90° 회전; single atom; 중심은 수평이나 glyph 각각 회전 | suppression 금지. 방향 확인 불가를 성공으로 해석하지 않음 |
| 밝은 독립 획 | v1 Il 원본 + 밝기 D=12/24/32/64인 별도 획, core와 분리/접촉 각각 | 획을 잃는 bbox 선택 금지, 또는 ambiguous |
| punctuation | 1px/2px/4px 고대비 점, 마침표·콜론·첨자 위치, glyph 행 가까이 배치 | 점 전체를 잃는 선택 금지. 면적 비율로 합격시키지 않음 |
| 배경 speck | 위 glyph에서 먼 낮은 contrast 단일 점, 행 band 밖, 두 bbox 중 하나만 포함 | 점 때문에 무조건 의미 손실 선언하지 않음. 조건 충족 clean duplicate에서는 선택 가능해야 함 |
| noise와 점의 경계 | 동일 크기 점의 contrast/거리/위치 변경; 배경 점과 punctuation이 시각적으로 구별 안 되는 사례 | 경계 불확실 시 기권. 모든 점 삭제/모든 점 의미 확정 모두 금지 |
| 1px 위치 이동 무손실 | bbox만 ±1 원본 px 이동하되 모든 glyph/작은 성분 유지 | 평가상 실제 문자/객체 손실로 세지 않음. observer는 선택 또는 기권 가능 |
| 1px 이동 실제 손실 | 같은 이동량으로 가는 획 또는 punctuation 전체가 빠짐 | support loss veto. 이동량이 작다는 이유로 허용 금지 |
| rasterization | bitmap은 nearest 및 area 기반 별도 renderer, font는 명시적인 binary/AA 별도 렌더; .75/1/1.5 scale | 원 연속좌표와 실제 raster support 기대값을 분리. 양자화만으로 문자 손실 label을 만들지 않음 |
| crop/full | 같은 원본 frame/context의 내부 crop 두 경로; halo 부족·원점/scale metadata 누락 control | 충분한 context는 동일 결정/원본좌표 관측. 부족하면 명시 오류/기권 |
| 독립 가까운 node | 같은 문자/다른 문자, bbox padding overlap, 분리 weak 획/서로 다른 baseline | 독립 owner 삭제 0 |
| 기존 구조 반례 | 부분 ROOT, chain, 정상 fanout, score 역전/tie, ID rename, 입력 순열 | 정보 손실·관계 손실·score/순서 의존 금지 |

일괄 full factorial 대신 builder에 명시한 고정 기본군과 변형 목록을 실행 전 모두 잠근다. 정확한 개수는 생성 후 **결과 보기 전** 전달한다. v1 replay와 신규군을 분리해 분모를 보고하고 반복 변형을 독립 이미지 수로 세지 않는다. 실패 조합 삭제나 동일 버전 threshold 조정은 금지한다.

## 8. 평가: 위치, 정보, 구조의 분리

루트의 기하/구조 평가 계약과 맞추되 이 모듈은 독립적으로 다음을 출력한다.

- **기하 진단**: bbox 차이, pixel-cell 경계 support 차이, coverage/방향 불확실성. 1px이라는 이유만으로 practical failure 플래그를 세우지 않는다.
- **관측 정보 보존**: core/weak/orphan component별 생존·부분 절단·전체 소실. 의미 있는 문자 여부를 알고리즘이 GT로 판정하지 않는다.
- **offline fixture 기대값**: 실제 글자/점/독립 owner 손실 또는 허용된 위치 양자화인지 evaluator만 구분한다. 기존 원 annotation/PPT를 쓰는 경우도 inference와 분리한다.
- **구조 보존**: 실제 owner 삭제, 중복 여부, 정상 fanout 관계 손실. endpoint ID만 바꿔 정답으로 만들지 않는다.

G0: 입력 whitelist/좌표/파일 IO/원본 불변/invalid data 검사. G1: V2-O 불변, V2-S와 관측 일치, score/order/opaque ID invariance, crop/full context 재현. G2: 독립 owner 또는 실제 글자/점 손실 0, unsupported 방향 승인 0, PP 잘못된 승자 0, 새 clean positive 최소 1개 성공. weak 먼 background speck 때문에 전부 기권하는 해법도 효과성 gate를 통과하지 못한다.

기하 진단이 1px 차이를 보고해도 offline 기대값에 실제 손실이 없으면 semantic failure로 더하지 않는다. 반대로 1px 점 전체를 잃으면 절대 면적이 작다는 이유로 손실을 무시하지 않는다. 식별 불가능한 사례는 ambiguous 기대를 별도 기록한다.

G2 실패 시 v2도 실패로 동결하고 실제 15개에 진입하지 않는다. 통과해도 실제 15개, C 결합, 학습, COM은 별도 지시 전까지 금지다. 현 단계의 완료 산출물은 이 명세와 반례 계획뿐이다.
