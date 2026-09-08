# label_anchor 중복 owner 원인 진단과 교정 계약 초안

## 결론

28개 anchor가 평가 GT 25개에 대응하는 이유는 세 위치에서 서로 어긋난 bbox 두 개씩이 선택됐기 때문이다. 같은 클래스의 위치 중복이며 class remap, OCR 또는 native adapter가 객체를 늘린 사례가 아니다. score ≥ 0.5, IoU NMS 0.7, 작은 bbox 대비 교집합 0.85라는 현재 선택 조건은 세 쌍을 모두 남긴다. 이후 추적이 서로 다른 ID를 독립 owner로 사용하면서 잘못된 owner 부착, 중복 fanout, multi-owner 기권이 발생했다.

**일괄 IoU 기준 하향이나 같은 문자열 병합을 구현할 근거는 없다.** 특히 PP에서는 더 높은 score의 bbox가 평가상 부정확하다. 교정 후보는 RGB에서 동일한 글자 영역을 중복 소유하는지 판단하는 연구 단계로 제한하고, 별도 문자 영역이라는 반증이 있거나 대표 bbox를 고를 근거가 부족하면 병합하지 않아야 한다. 아직 교정 알고리즘·threshold를 구현하거나 실험하지 않았다.

## 근거와 재현 경계

`benchmarks/duplicate_owner_diagnosis_v1.json`에 handoff, source predictions, 원본 annotation(평가용), A-T source report, R8-P tracing report, 관련 코드의 SHA256과 세 트리의 raw/selected bbox·score·ID·trace를 저장했다. 원본 파일은 수정하지 않았다.

- v2 final handoff SHA256: `346c4090c209e13243ed7a4d96723fe09921e037660acf4f3e8dd776c08f45e4`.
- source prediction SHA를 declaration과 대조했다. 현재 `detection_postprocess.py` SHA가 동결 declaration의 구현 SHA와 일치함을 확인했다.
- handoff의 selected + omitted를 detection index 순으로 재구성해 **15개 전체의 선택 ID/순서를 현재 함수로 재현**했다. 모델 inference는 실행하지 않았다.
- 세 트리의 selected raw bbox = handoff bbox = A-T source_scene bbox를 확인했다. semantic ID도 그대로다.
- GT는 이미 저장된 평가 매칭을 확인하고 bbox IoU를 독립 계산하는 데만 읽었다. 교정 후보의 inference 입력으로 쓰지 않았다.
- 원본 RGB 두 장을 직접 확인했다. CP/Adj/PP 각 위치에는 하나의 라벨이 보인다. 훈련 시점이나 model 내부 pre-NMS proposal은 조사하지 않았다. 여기서 raw는 저장된 detector output이며 RPN raw proposal이라는 뜻이 아니다. checkpoint 학습 원인까지 확정할 수 없다.

## 28 대 25의 분해

| 이미지 | 저장 raw / 선택 anchor / GT | 중복 쌍(det index) | score | 쌍 IoU / 작은 bbox 겹침 |
|---|---:|---|---|---|
| tree_1302_00036 | 13 / 8 / 7 | CP: 5, 7 | .951933, .910889 | .475431 / .680706 |
| tree_1302_00079 | 10 / 8 / 8 | 없음 | — | 선택 bbox 사이 교집합 없음 |
| tree_1302_00149 | 16 / 12 / 10 | Adj: 1, 10 | .989696, .733070 | .468708 / .715626 |
| tree_1302_00149 | 위와 같음 | PP: 9, 11 | .889751, .523675 | .432237 / .705769 |

세 쌍은 모두 같은 label_anchor(source label 4 → 현재 label 5)다. 각 쌍의 score는 모두 .5 이상이고 IoU는 .7 미만, 작은 bbox 겹침도 .85 미만이다. 따라서 score순 NMS 뒤 containment 검사에서도 모두 생존한다. tree00036의 det8(score .550897)은 선택되지 않았고 나머지 omitted score는 .5 미만이다. tree00079와 tree00149의 omitted는 모두 .5 미만이다. 이 집계에는 새로운 검출이나 선택 조건 변경이 없다.

| 위치 | 첫 bbox (x0,y0,x1,y1), px | 두 번째 bbox, px |
|---|---|---|
| CP 5/7 | (383.722,30.714,401.840,42.839) | (382.956,31.979,397.491,48.793) |
| Adj 1/10 | (338.372,29.148,362.919,44.756) | (341.109,32.973,359.837,49.439) |
| PP 9/11 | (355.687,176.766,374.461,192.395) | (356.996,172.567,372.354,186.840) |

중복 bbox는 수직으로 어긋나며 글자 아래 선이 있는 쪽으로 더 뻗는다. 실제 glyph와 shaft의 중복 소유 정도는 아직 픽셀 마스크로 측정하지 않았다. 이 관찰은 후속 RGB 진단 가설이며, 현 자료만으로 glyph/shaft 혼동을 detector 내부 원인으로 확정하지 않는다.

## 평가 실패는 자리 경쟁만이 아니다

동결 평가는 role별 IoU ≥ .5 후보를 IoU 내림차순으로 일대일 매칭한다. annotation과 독립 재계산한 최대 GT IoU는 다음과 같다.

| 위치 | matched 검출 / 최대 GT IoU | unmatched 검출 / 최대 GT IoU |
|---|---|---|
| CP | det5 / .636749 | det7 / .396883 |
| Adj | det1 / .816608 | det10 / .422498 |
| PP | det11 / .664244 | det9 / .477633 |

세 unmatched 검출은 전부 .5 미만이다. 중복 물체 수뿐 아니라 bbox 정합성도 실패한다. 이들을 GT alias로 치환해 TP로 계산하면 동결 identity 계약을 바꾸는 것이다.

PP가 점수순 제거의 직접 반례다. 세 중복을 모두 억제하려고 NMS IoU를 .43으로 내리면 det9가 det11보다 먼저 남아 정확한 det11을 억제한다. 이는 현재 bbox에 대한 기하·score 계산으로 예측한 반례이며 수정된 실행 성적으로 보고하지 않는다. 낮은 threshold가 28→25로 숫자를 맞추더라도 25개의 정확한 owner를 의미하지 않는다. CP에서도 det5를 남기면 OCR `CP.` 오답은 별도 문제로 유지된다.

## 추적 owner로 사용된 경로

`region/tracing.py:123` 이후는 eligible node 각각을 별도 owner로 취급한다. 각 bbox를 pad 2px로 지운 mask에서 성분을 찾고, **각** owner까지 거리 ≤ 6px이면 contact에 포함한다(현재 세 트리의 저장 audit). 이 단계는 detector score나 OCR 문자열로 identity를 다시 결정하지 않는다.

- tree00036 component 3의 contact는 det4(V)와 det7(CP)뿐이다. 그 결과 `connector:r3:0`, det7→det4가 생성됐다. det5의 더 높은 score는 owner contact 선택에 사용되지 않는다. 다른 component 1/2는 각각 det5·det7을 함께 만나 `ambiguous_multi_owner`로 기권했다.
- tree00149 component 3의 contact는 det9(PP), det10(Adj), det11(PP)다. `unique_straight_fanout`이 det10을 hub로 삼아 **같은 661px 성분**에서 det10→det9와 det10→det11 두 경로를 생성했다. raw path length는 둘 다 121이다. 이는 두 개의 독립 선 관측이라는 증거가 아니다.
- 같은 이미지의 component 1/2는 det1·det10의 중복 접촉으로 multi-owner 기권했다. component 6은 ROOT→det9에 부착됐지만 native fitting에서 기권했다. 따라서 영향을 native FP3에만 한정할 수 없다.
- A-T의 새 native FP는 det7→det4 한 개와 det10→det9/11 두 개다. 이는 저장 trace와 emitted scene으로 확인된다. adapter는 owner ID나 방향을 바꾸지 않았다.

중복 제거가 추적 이전 mask 및 contact 집합을 바꿀 수 있으므로, 출력 connector의 endpoint ID만 바꾸거나 중복 선만 지우는 후처리는 전체 원인을 해결했다고 주장할 수 없다.

## 이미지 단독 교정 계약 제안 — 구현 전

1. 입력은 원 RGB와 예측 bbox/score/semantic kind만 허용한다. GT bbox·ID·문자, source PPT geometry, family별 정답 노드 수는 금지한다. OCR을 추가로 사용하는 별도 arm도 문자열 일치만으로 동일 owner를 선언하지 않는다.
2. 대상은 label_anchor의 공간적으로 겹치는 쌍이다. 겹침은 **검사 후보 생성 조건**일 뿐 제거 조건이 아니다. 문자열이 같아도 공간적으로 분리된 라벨은 후보로 합치지 않는다.
3. 두 bbox의 공통 주변 crop에서 glyph 후보와 길게 이어지는 connector stroke를 구분하는 관측을 만든다. 동일한 글자 영역을 두 bbox가 소유하는지, 각 bbox에 독립된 글자 영역이 있는지, 서로 다른 baseline/방향/문자열 일부인지 측정한다. 단일 connected component나 공백 부족만으로 같다고 판정하지 않는다. 글자와 선이 닿으면 분리 실패를 명시한다.
4. 동일 glyph 집합이라는 강한 근거와 **별도 라벨이라는 반증의 부재**가 함께 있어야 suppression 후보가 된다. 선택 bbox는 glyph 누락·불필요한 선 포함 등 RGB 적합 근거로 결정한다. confidence는 해당 근거가 동률일 때의 결정적 순서에만 사용한다. PP처럼 어느 bbox가 더 정확한지 판별하지 못하면 억제하지 않고 `ambiguous_owner_identity`를 보고한다. bbox 평균/합집합으로 새 owner를 만들지 않는다.
5. surviving ID/bbox/kind는 기존 검출 중 하나를 그대로 유지한다. suppressed ID와 근거를 audit에 기록하고 inference에서 GT ID로 바꾸지 않는다. transitive overlap만으로 A–B–C를 모두 합치지 않는다. cluster 전체에 동일 glyph 소유 근거가 없으면 cluster 교정을 기권한다.
6. 실제 교정 arm을 승인받아 실행할 때는 추적 **이전**에 적용하고 동일 RGB에서 mask/contact/path를 재계산한다. 후속 경로 변화는 별도 개입 결과로 평가하며 이전 source_scene가 불변이라고 주장하지 않는다. ambiguity 때문에 fanout을 제한하는 실험도 별도 arm으로 분리한다.
7. 기록할 최소 항목: source RGB SHA, 입력/출력 owner IDs, 원 bbox/score, pair overlap, glyph evidence 영역/coverage, independent-glyph 반증, shaft 분리 불확실성, 결정/기권 사유, mask/contact 변화, trace와 native 관계 성적. 비어 있는 OCR 라벨은 여전히 유용한 라벨 성공이 아니다.

현재 세 양성 사례만 보고 glyph coverage threshold를 정하지 않는다. 관측량 구현 전에 아래 반례·측정 정의·허용 조건을 고정하고, 다른 이미지에 있는 개발군과 미관측 검증군을 분리해야 한다. 현재 자료는 이미 본 합성 validation의 진단이다.

## 필수 negative controls 및 중단 조건

| control | 구성 / 현재 근거 | 금지해야 할 오류 |
|---|---|---|
| 현재 PP score 역전 | det9 .889751 vs det11 .523675, 동일 라벨이지만 정합성 역전 | 높은 score만으로 det11 삭제 |
| 반복 문자 실제 별도 node | tree00036의 서로 떨어진 CP 2개·PP 2개, tree00079의 cat 3개·runs 2개, tree00149의 Adj 2개 | 동일 문자 전체 병합 |
| 가까운 동일 문자 | 두 독립 `PP` glyph 묶음을 서로 가까이 두고 bbox padding을 겹치게 함. 예: 20×16 bbox의 x offset 7 → IoU 13/27≈.481; 두 glyph core는 공통 bbox 영역에 공유되지 않도록 배치 | .43/.45 NMS로 서로 다른 owner 삭제 |
| 가까운 다른 문자/두 줄 | 별도 baseline의 `CP`·`PP`, `A`·`B`; 큰 bbox padding 때문에 겹쳐도 실제 glyph core는 분리 | 겹침·문자 일부 유사성으로 병합 |
| 한 라벨 안의 부분 검출 | `ROOT` 전체와 `OO` 부분, 본문과 superscript/subscript | 부분 glyph 공유를 전체 owner 동일성으로 오인 |
| 선이 문자에 닿는 경우 | 두 라벨을 연결하는 shaft, 접촉/교차선, anti-alias/그림자 추가 | 하나의 픽셀 성분이라는 이유로 두 라벨 병합 |
| 겹침 chain | A–B, B–C는 겹치지만 A·C는 독립 glyph/다른 node | transitive closure로 세 owner 삭제/통합 |
| 불확실/빈 OCR | 같은 glyph의 한쪽만 인식, CP/CP., 양쪽 공백 | OCR 일치 부재를 별도 owner 증거로 쓰거나 공백을 성공 집계 |
| 실제 fanout | VP→Det/dog처럼 서로 다른 두 terminal과 독립 가지 관측 | 중복 방지 규칙으로 정상 fanout 한 가지 삭제 |
| 양성 perturbation | 같은 glyph에서 bbox 이동·크기·score 순서·입력 순서를 변화 | score/order에 따라 의미 결론이 뒤집힘 |

가까운 별도 node fixture는 단순 bbox 수치만으로 끝내지 않고 실제 RGB glyph와 각자 연결 stroke를 포함해야 한다. 단어·간격·해상도·회전·noise를 교차시키며 정상 예제를 삭제하면 교정 채택을 중단한다. 비-anchor 12개 원본은 identity 불변 회귀 대상으로 유지한다. 모델 학습, 제품 변경, COM은 이번 진단에서 수행하지 않았다.
