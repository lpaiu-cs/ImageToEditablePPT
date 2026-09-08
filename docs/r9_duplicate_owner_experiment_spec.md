# R9-D: RGB owner 관측과 보수적 suppression 실험 명세 v1

## 상태와 목적

이 문서는 **구현 전 실험 계약**이다. 아래 수치는 효과를 측정해 고른 최적값이 아니라 최초 반례 검증을 위한 사전 고정값이다. 구현·fixture 결과·실제 15개 suppression 결과는 아직 없다. 실패하면 이 버전을 실패로 남기고 별도 버전을 제안한다. 기존 R8-P/T/A 및 4px native fitting 기준은 변경하지 않는다.

질문은 두 개다. (1) RGB에서 두 예측 bbox가 같은 글자 영역을 중복 소유한다는 관측을 만들 수 있는가? (2) 그 관측으로 기존 bbox 중 하나를 안전하게 선택할 수 있는가? 동일 위치를 찾는 것과 대표 bbox를 정확히 고르는 것을 별도 판정한다. 28개를 25개로 줄이는 것은 목표/통과 조건이 아니다.

근거는 `duplicate_owner_diagnosis_v1.md`와 `benchmarks/duplicate_owner_diagnosis_v1.json`이다. 세 중복 쌍의 IoU .432–.475, IoS .681–.716은 기존 .7/.85 규칙을 통과한다. unmatched bbox의 GT 최대 IoU .397/.422/.478은 모두 .5 미만이다. PP에서는 부정확한 det9의 score .890이 정확한 det11의 .524보다 높다. 따라서 .43 NMS, score만 사용한 승자, GT alias, 같은 문자열 병합은 허용하지 않는다.

## 1. 범위, 입력, 두 arm

관측 함수의 입력은 RGB uint8 H×W×3와 `id, semantic_kind, bbox_xyxy, confidence` 목록만이다. ID는 opaque key이며 이미지명·ID 문자열에서 family/GT 의미를 추론하지 않는다. OCR 문자열, label, connector, GT/annotation, source PPT, 정답 노드 수를 관측 함수에 전달하지 않는다. bbox는 유한수이며 양의 면적, 이미지 내부여야 한다. 위반하면 해당 파일을 오류로 종료한다. 자동 clamp/rescale은 하지 않는다.

- **D-O observations-only**: 동일 입력 owner 목록을 순서/필드까지 그대로 반환한다. 아래 관측과 `proposed_decision`만 sidecar에 기록한다. trace/OCR/출력 개입이 없다.
- **D-S suppression**: D-O와 동일 코드·파라미터로 관측한 뒤, 승인 조건이 완성된 cluster에서만 기존 owner를 제거한다. 살아남은 ID/bbox/kind/score는 입력 객체와 동일하다. ambiguous는 모든 owner 유지다. ambiguous라는 이유로 연결까지 삭제하는 arm은 이번 범위에 없다.

D-S는 D-O sidecar를 수동 편집해서 적용하지 않는다. 동일 입력 SHA로 관측을 다시 계산하거나 SHA로 묶인 변경 불가 sidecar를 검증한다. 새 평균/합집합 bbox, 새 owner ID, suppressed ID를 GT ID로 바꾸는 alias는 금지한다. 원 trace endpoint를 다른 owner ID로 덮어쓰지 않는다.

예정 모듈은 research 전용이며 제품 postprocess/tracer/writer는 건드리지 않는다. 실제 15개 D-S 실행은 fixture 단계 종료와 별도 실행 지시 이후에만 한다. source-centerline 개입과 결합하지 않는다.

## 2. 좌표 및 픽셀 계약

모든 bbox·거리·mask는 **원본 이미지 좌표**다. native의 1.2 정규화 좌표를 사용하지 않는다. 파라미터 길이 단위는 `s = H / 360`인 기준 pixel이며 면적 단위는 s²이다. 초기 지원은 가로쓰기, 밝고 대체로 균일한 배경의 작은 text-only owner다. 회전/세로쓰기·복잡한 배경을 맞추려고 확대 해석하지 않는다.

float bbox 안 픽셀 여부는 pixel center `(x+.5,y+.5)`의 half-open 포함 조건으로 결정한다. crop은 floor(min)-padding / ceil(max)+padding, 이미지와 교차한다. 이미지 경계 때문에 요구 padding이 잘리면 cluster는 `crop_clipped`로 기권한다. 두 bbox의 양의 면적 교집합이 있을 때만 candidate edge를 만든다. IoU/IoS는 기록하지만 suppression threshold로 쓰지 않는다.

candidate graph의 connected component를 검사 단위로 사용한다. 구성원이 2개 미만이면 no-op, 4개 초과면 `cluster_too_large`로 기권한다. 3~4개 cluster는 모든 쌍이 candidate edge인 clique여야 하며, 아니면 `overlap_chain`으로 전체 유지한다. 처리 순서로 먼저 삭제해 chain을 풀지 않는다.

각 cluster의 bbox union에 `padding=ceil(3h)`를 둔다. `h`는 cluster bbox 높이 median, 단위는 원본 px다. crop 상한은 한 변 256s px이며 초과하면 `crop_too_large`다. union은 관측 crop 계산에만 쓰고 출력 bbox로 쓰지 않는다.

## 3. 원본 ink와 shaft 관측

### 3.1 세 가지 ink 관측

RGB를 float로 바꾸고 `Y=.2126R+.7152G+.0722B`를 계산한다. crop 가장자리 두께 ceil(2s)의 ring에서 channel median과 Y의 10/90 percentile을 기록한다. ring의 median Y <225 또는 Y90−Y10 >30이면 `background_unsupported`다. ring에 검은 선이 조금 들어간 상황을 median만으로 안전하다고 선언하지 않고 아래 mask 안정성도 확인한다.

`T ∈ {110,140,170}` 각각에서 `M_T = (Y <= T)`를 만든다. blur, closing, dilation, hole fill 없이 원본 threshold ink를 사용한다. mask별 SHA, foreground pixel 수를 기록한다. 세 결과 중 유리한 threshold를 골라 사용하지 않는다. 관측 실패·기권 사유·승자 결정이 세 mask에서 모두 같아야 D-S를 허용한다.

### 3.2 shaft를 지우기 전에 불확실성 표시

각 M_T에서 8-connected component를 구한다. 면적 < max(1,ceil(2s²))는 tiny ink로 별도 기록하며 삭제하지 않는다. 나머지 component마다 모든 pixel center의 PCA/TLS 주축, 주축 투영 span, 수직거리 p95/max, bbox, bbox union 내부/외부 pixel 수를 기록한다. 동일 eigenvalue면 축을 임의 선택하지 않고 uncertain이다.

shaft candidate 조건은 다음 모두다.

1. 주축 span ≥ 3h이고 union 밖 주축 투영 span도 ≥ h.
2. 수직거리 p95 ≤ 1.5s, max ≤ 3s.
3. 주축과 수직 방향의 전체 폭 ≤ 6s.

이를 만족한 component만 `S_T`(shaft-like)로 분리한다. 문자 I/l처럼 짧은 선은 길이 조건 때문에 제거하지 않는다. 길지만 위 조건을 통과하지 못하고 union 안팎에 모두 ink가 있는 component는 `U_T`(glyph/shaft unresolved)로 둔다. U_T가 어느 owner 내부에서든 max(1,ceil(2s²)) 이상이면 `shaft_touch_uncertain`으로 기권한다. shaft candidate와 잔여 ink가 1픽셀 이웃이면 `shaft_glyph_contact`로 기권한다. 접촉을 절단해서 문자를 복구하지 않는다.

이 규칙은 shaft라는 의미를 증명하지 못한다. 긴 글자열/밑줄/접촉선이 오분류될 수 있으므로 해당 반례 통과가 선행 조건이다. 조건을 벗어나는 선은 더 공격적으로 제거하지 않는다. 원본 ink는 보존하며 S_T/U_T는 sidecar mask다.

## 4. glyph 후보와 소유 관측량

잔여 `G_T=M_T−S_T−U_T`를 8-connected component로 분해한다. 이를 글자라고 확정하지 않고 **ink atom**으로 부른다. component ID는 `(top,left,bottom,right,area,mask_sha)` 정렬 순서로 생성한다. tiny ink와 crop 경계 atom도 기록한다.

각 atom k와 owner i에 대해 `coverage(i,k)=|atom_k ∩ bbox_i| / |atom_k|`를 계산한다. 다음을 고정한다.

- **owned atom**: coverage ≥ .95이고 area ≥ max(1,ceil(2s²)).
- **partial atom**: .05 < coverage < .95. 하나라도 있으면 해당 cluster는 `partial_glyph`로 기권한다.
- **foreign/tiny evidence**: 어느 bbox 안에 들어 있는 tiny atom 총면적이 2s²를 초과하면 `small_ink_uncertain`. punctuation을 noise로 버리며 병합하지 않는다.
- **shared signature**: cluster 모든 owner의 owned atom ID 집합이 정확히 같고 비어 있지 않아야 한다. 다르면 `different_ink_ownership`으로 유지한다. 문자열은 비교하지 않는다.

shared atom의 union bbox를 `B_g`로 두고 총 ink 면적 A_g, atom 수, glyph width/height, 각 atom coverage, 각 owner의 glyph coverage를 기록한다. B_g는 관측량일 뿐 새 출력 bbox가 아니다.

독립 라벨 반증을 위해 atom을 다음의 무방향 graph로 묶는다. 두 atom bbox의 세로 겹침 / 작은 높이 ≥ .5이고 가로 gap ≤ .35×median(atom 높이)일 때만 edge를 만든다. atom graph가 하나의 connected component가 아니면 `multiple_ink_groups`로 기권한다. shared atom 높이 median이 3s 미만 또는 24s 초과면 지원 밖이다. 서로 다른 baseline, superscript/subscript는 이 초기 계약에서 적극 병합하지 않는다.

**식별 불가능성**: 매우 가까운 별도 node 두 개가 같은 bbox들에 함께 포함되고 단일 글자열과 같은 RGB를 만들면 이미지 정보만으로 의미적 node 수를 항상 구분할 수 없다. 이런 경우를 해결했다고 주장하지 않는다. 아래 독립-glyph controls에서 한 번이라도 잘못 병합하면 이번 D-S 버전은 실패다. control 통과도 일반적인 동일 객체 판정의 증명은 아니다.

## 5. 대표 bbox 선택 — identity 통과와 별개

위 검사를 모두 통과한 cluster에서만 각 owner의 벡터를 계산한다.

- `glyph_coverage = |G_shared ∩ bbox| / A_g`.
- `shaft_fraction = |S_T ∩ bbox| / max(1, |M_T ∩ bbox|)`.
- B_g와 bbox의 네 방향 padding, 음수 여부.
- `padding_excess = max(0, (area(bbox)−area(B_g))/area(B_g))`.
- `padding_asymmetry = (|left−right|+|top−bottom|)/height(B_g)`.

승자 후보는 glyph_coverage ≥ .98, 네 padding 모두 ≥0을 만족해야 한다. 최우선은 글자 누락 방지이며 score는 이 조건을 우회하지 못한다.

두 후보 i/j 비교에서 i가 j보다 나쁘지 않다는 것은 세 손실(shaft_fraction, padding_excess, padding_asymmetry)이 각각 j+(.01,.05,.05) 이하라는 뜻이다. i가 j보다 낫다는 것은 그 조건을 만족하면서 적어도 하나의 손실이 j보다 각각 (.05,.25,.25) 이상 작다는 뜻이다. 모든 다른 후보보다 낫다는 **유일한** i가 있을 때만 i를 남긴다. tradeoff/비교 불능/동률은 `representative_ambiguous`로 전부 유지한다. score 차이만으로 동률을 깨지 않는다. 완전히 동일 bbox도 이번 초기 버전에서는 동률로 남긴다.

세 threshold mask에서 같은 원본 owner ID가 유일 승자여야 한다. 하나라도 달라지면 `threshold_instability`로 전체 유지한다. 관측 confidence는 detector score와 구분하고 확률로 표시하지 않는다. D-S는 `suppress_ids`와 `keep_id`, 사유만 반환하며 label/경로를 수정하지 않는다.

이 선택식은 아직 PP의 det11을 선택한다는 보장이 없다. PP에서는 det11 선택 또는 ambiguous 유지가 허용되며 det9를 남기고 det11을 제거하면 실패다. GT 정합성이 더 좋은 bbox를 자동 추론한다는 주장도 금지한다.

## 6. 구현 가능한 fixture 계약

fixture builder는 모델 없이 RGB와 예측 owner JSON을 만든다. expectation은 별도 evaluator JSON에 두고 관측 함수의 읽기 allowlist에서 제외한다. 기본 canvas는 640×360, 흰 배경, 검은 glyph이며 고정 font 파일 SHA/renderer version을 기록한다. 실제 글자뿐 아니라 atom 위치가 명확한 손으로 정의한 bitmap glyph fixture를 함께 사용한다. 구현 버전·builder·fixture PNG/owner/expectation SHA를 실행 전에 lock한다.

| fixture 군 | 반드시 포함할 구성 | 허용 결과 / 실패 |
|---|---|---|
| positive duplicate | 한 glyph 묶음과 두 bbox: 둘 다 glyph 전체 포함, 하나만 아래 shaft를 더 포함하거나 padding이 명백히 과다. 실제 다른 node 없음 | 열화 없는 clean 기본 사례 최소 1개에서 올바른 bbox 하나 선택. 나머지는 선택 또는 ambiguous. wrong bbox 선택 실패 |
| PP score 역전 | R8 det9/11 원 bbox·score와 해당 RGB의 고정 crop. 전체 이미지 입력도 별도 고정 | det11 선택 또는 둘 다 유지. det9만 남으면 실패. score swap으로 결과 바뀌면 실패 |
| 근접 독립 glyph | 별도 PP 두 개의 core를 분리하고 padding만 겹침. bbox (0,0,20,16), (7,0,27,16)의 평행이동 예시 IoU=.481. 두 별도 glyph가 실제로 들어가도록 fixture 크기/글꼴을 명시 | 두 owner 유지. .43 NMS라면 한 개 사라지는 대조는 evaluator 계산으로만 기록 |
| 반복 문자 | 떨어진 CP/CP, PP/PP, cat/cat/cat, runs/runs. 서로 다른 연결 stroke 포함 | 모두 유지. OCR field 없음/동일/다름이 관측 결과에 영향 없어야 함 |
| 부분 문자 | ROOT 전체와 OO 부분, I/l, punctuation dot, superscript와 본문 | 모두 유지 또는 cluster ambiguous. 작은 조각 제거 후 같은 signature로 강제 병합하면 실패 |
| 두 baseline | CP/PP를 두 줄로 배치, bbox padding 겹침; 위아래 gap 2/4/8 기준 px | 별도 owner 유지 |
| 선 접촉/교차 | glyph에 shaft가 0/1/3 px 간격, 밑줄, 글자 I와 평행 선, 두 글자를 연결한 선 | 독립 node 삭제 금지. 접촉 분리 불명확하면 ambiguous |
| overlap chain | A–B/B–C만 겹치는 세 bbox와 독립 양끝 glyph; 입력 순열 6개 | 모든 owner 유지, overlap_chain |
| 정상 fanout | VP→Det/dog의 두 독립 terminal 및 공통 shaft/두 가지 | owner 전부 유지. 후속 고정 tracer에서 기존 정상 두 관계 유지 |
| empty/unsupported | blank, gray/색 배경, gradient, 사진 texture, crop 잘림, 세로·회전 글자 | suppression 금지, 이유 기록 |
| bbox tie/score | 동일 bbox 두 개, 손실 tradeoff, score 역전, ID 이름 변경 | tie는 유지. geometry 판정은 score·ID 이름에 독립 |

각 synthetic 기본 fixture에 동일한 사전 고정 변형을 적용한다: scale .75/1/1.5(크기 및 bbox 동시 변환), 0/1 기준 px의 shaft 간격 이동, 입력 순서 역전, score swap. 색 변형은 black 0과 gray 100, antialias 유/무 두 경우다. 회전 ±15°/90°는 지원 밖 control로 suppression 금지다. 무작위 noise가 필요하면 seed 901로 1% 픽셀에 ±20 밝기 변화만 적용한다. 전체 조합 수와 파일 목록은 builder가 생성한 후 결과를 보기 전에 lock한다. 실패 조합 삭제 금지.

R8 실제 crop의 expectation은 평가용이며 알고리즘은 sample ID나 사전 지정 keep ID를 읽지 않는다. R8 fixture는 이미 관찰한 진단군이다. 신규 합성 controls도 일반화 검증을 대체하지 않는다.

## 7. 단계별 gate와 실패 처리

**G0 구현 확인:** 새 research module/fixtures/test만 작성. 모델·OCR·제품 코드·COM 불사용. 입력 field를 whitelist하고 GT/label/connector 접근을 차단한다. 실행환경(OpenCV/NumPy 등), 소스 SHA와 파라미터를 lock한다. NaN/중복 ID/범위 밖 bbox는 오류여야 한다.

**G1 관측 회귀:** D-O의 반환 owners가 입력과 완전히 동일하고 D-O proposed decision과 D-S decision이 같은 계산에서 나옴을 확인한다. 원 RGB/JSON 수정 0. 순열과 score swap 결과가 ID 매핑 후 동일해야 한다. mask별 관측이 달라지면 안전하게 ambiguous가 되어야 한다.

**G2 반례 gate:** 독립 node의 잘못된 suppression 0, PP det11의 잘못된 제거 0, 금지 입력 접근 0. positive clean 기본 fixture 최소 1개에서 올바른 suppression이 있어야 한다. 전부 ambiguous면 안전한 무개입 관측기일 수 있으나 유효한 suppression 후보로 통과시키지 않는다. 접촉/rotation 등 unsupported는 기권이 올바른 결과다. 하나라도 실패하면 D-S 실제 15개 실행으로 진입하지 않는다. 수치를 고쳐 같은 버전의 통과로 바꾸지 않는다.

**G3 실제 15개 관측:** 별도 지시 후 기존 handoff와 RGB를 D-O에 통과시킨다. 먼저 observation audit와 SHA를 동결한다. 기존 15개 source scene은 그대로다. GT 평가로 threshold를 조정하지 않는다.

**G4 실제 suppression 대조:** 별도 지시 후 D-S를 추적 전에 적용한다. R8 고정 RGB/예측, 원 tracer/mask/4px fitter/native adapter를 그대로 사용한다. OCR은 기존 고정 ID별 값을 살아남은 owner에 그대로 운반해 새 OCR 효과를 배제한다. owner 집합이 바뀌므로 trace를 재실행하고 path/방향 변화는 결과로 기록한다. 중심선 교정은 끈다. D-O 무개입 trace가 baseline과 일치해야 한다. 다른 12개 non-tree는 owner 불변이다.

후속 평가는 원래 role/IoU≥.5 일대일 node matching과 endpoint ID 기반 관계 평가를 그대로 사용한다. node TP/FP/FN, trace/native 관계 TP/FP/FN, multi-owner 기권 수, 겹친 connector 수, matched label 정답/오답/공백, 제거 owner별 이유를 모두 보고한다. native 수 증가/FP 감소 하나만으로 채택하지 않는다. 별도 node 손실이나 새 잘못된 관계가 있으면 미채택, 이득 없는 경우 no-benefit이다. 대조 후에도 이미 본 15개의 성과는 제품 일반화·사용자 편집시간 절감의 증거가 아니다.

## 8. sidecar 및 산출물

최상위: schema=`r9_duplicate_owner_observations_v1`, arm, rgb_sha256, owners_sha256, spec_sha256, code/runtime SHA/version, parameters, input_count, kept_ids, suppressed_ids, unchanged_nonanchors.

cluster별: 원 IDs/bbox/score, crop xyxy, IoU/IoS, threshold별 M/S/U/G mask SHA와 artifact 경로, background 요약, component TLS/span/residual/inside-outside counts, atom coverage matrix, owned signature, independent-group 수, 각 후보 손실 벡터, pairwise dominance matrix, mask별 proposed winner, 최종 decision/reasons. mask와 crop은 원본에서 유도된 진단 산출물로 보관하며 원본을 덮어쓰지 않는다.

suppression ledger에는 원 bbox/score, surviving ID, 조건별 boolean, ambiguity 사유를 남긴다. `duplicate=true`라는 의미적 확정 대신 `shared_ink_supported`와 `representative_supported`를 분리한다. expectation/GT metric은 별도 evaluator 산출물이며 observation JSON에 섞지 않는다.

이 명세의 완료 조건은 구현 가능한 측정·판정·반례·gate가 고정되는 것이다. 현재 전달은 이 명세와 원인 근거까지이며, 반례 테스트 통과나 실제 suppression 개선을 주장하지 않는다.
