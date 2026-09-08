# R15 실행 결과: 분기6개 회복, 전체 품질은 기준 미달

2026-09-09. 사용자 승인 후 R15.1-A와 R15.2-A를 실제 RGB 추론 및 PowerPoint 렌더까지 실행했다. **R15 전체 완료 또는 production 승인이 아니다.** `closed-native-v4`의 기본 설정은 그대로이며 두 실험 옵션 모두 기본값 false다. 실패 결과를 덮어쓰지 않았다.

## 1. 결론

| 실험 | 실제 개선 | 안전성/한계 | 결정 |
|---|---|---|---|
| R15.1-A 작은 경계 틈 보완 | CogBot 후보11→15, 최종은8노드/7라벨/4연결 그대로 | 안전성43 중11회귀, 사진 캡션 누출 및 기존 연결2개 손실 | 채택 불가, v2 임계값 튜닝 보류 |
| R15.2-A hub 출발 탐색 | reasoning-full 방향 연결18→24, 누락 분기6개 회복 | 안전성43 불변, 다른 복잡6 불변. 별도 source PPT 직선 양성은0/3으로 실패 | 한정 개선을 보존, 일반 분기 복원/제품 승격은 불승인 |

원래 CogBot은 핵심 노드8/17, 명확히 확인한 방향 관계4/20 그대로다. 기존 손실 장부의20관계는 전체 연결 수가 아니라 확실하게 열거한 부분집합이다. 주요 검색·생성·ACT 흐름을 여전히 다시 그려야 한다. 성공한 일부 분기로 이 기준 미달을 상쇄하지 않는다.

## 2. 경계 후보 증가가 실제 개선이 아니었던 이유

원본 Canny에 이미 남아 있는 경계의 작은 디지털 틈만 보완하도록3×3 cross closing, 모든 contour point의 원본 edge 거리≤sqrt(2), 기존 threshold agreement·형상 cutoff를 유지했다. 새 후보는 Reflection Handler, LTM Handler, Working Memory, Fast Model API다. 모두 내용 veto에서 빠져 실제 원본 PPT는 개선되지 않았다.

더 중요한 반례는 사진의 흰 caption strip이다. 새 후보를 독립 라벨 seed로 취급하자 원래 사진 카드의 frame-only 판정까지 뒤집혔다. 기존 후보 ID와 bbox가 보존되어도 내부 소유 관계와 최종 admission은 보존되지 않았다. gray-flow에서는 사진 캡션·어두운 부모 채움이 살아났고, flower-flow에서는 기존 빈 frame과 방향 연결2개가 사라졌다. 대표 actual COM을 root도 직접 보았다.

43건의 새 후보14개는 모두 caption strip이며 정상 gap-closed 양성 증거는 없었다. 따라서 이 집합만 통과하도록 내부 후보를 차단하는 수정부터 하지 않았다. 경계/역할/내용 분리를 입증하는 정상 양성 대조가 먼저 필요하다. 상세는 `r15_boundary_gap_v1_independent_audit.md`, 계약은 `r15_boundary_gap_spec.md`다.

## 3. 분기6개 복구의 원인과 한계

기존 `straight_fanout`은 owner index의 작은 쪽→큰 쪽 BFS 경로를 무방향 캐시에 넣고 필요하면 뒤집었다. 그러나8-neighbor BFS의 동일 비용 격자 경로는 탐색 방향에 따라 달라진다. reasoning-full에서 같은 mask·접점인데도 hub 출발과 leaf 출발의 직선 잔차가 달라졌다. 일부 leaf 출발 잔차는5.44/5.07px로 기존2.817px 조건을 넘었다.

수정은 hub→leaf로 탐색 방향과 캐시 key를 고정하는 것이다. 허용 오차, mask, 고유 hub, 모든 leaf의 arrowhead, OCR/content, native preset은 그대로다. 새 거대 graph 구현 없이 기존 helper를 재사용했다. 테스트에는 owner 순서6가지와 무방향/일부 방향/굽은 구조 기권을 넣었다.

실제 reasoning-full 결과:

- Text Embedding→Decoder1/2/3, Predictor1/2/3의6개 방향 관계가 복구됐다.
- 기존18개 연결은 ID/port ID 재번호를 제외한 geometry·owner·방향·provenance가 정확히 보존됐다.
-24개 노드와 전체 스타일은 이전과 같다. 라벨23개는 텍스트 완전성23개라는 뜻이 아니다.
- 열거된29관계 대비18/29(62.1%)→24/29(82.8%). 남은5개는 Symbolic Prediction1/2/3 및 Neural Prediction2/3→Mixture 합류다.
- Mixture-of-Experts 제목과 Symbolic Prediction1의 제목 뒷부분은 여전히 없다. 배경 구획도 이번 수정 범위가 아니다.

**독립 대조에서 남은 반례:** source PPT로 작성하고 실제 PowerPoint에서 렌더한 단순3방향 분기는 노드4/라벨4/접점4가 모두 관측됐지만 간선0개다. 화살표 sign은 세 ray 모두+1인데 상하 BFS 경로 잔차4.80/4.85px가 기존2px를 초과한다. 방향 고정은 owner 순서 의존을 없앴을 뿐, BFS 한 경로가 물리적 잉크 중심선이 아니라는 문제는 해결하지 않았다. 양성 source나 cutoff를 바꾸지 않았다.

## 4. 실제 렌더·편집·회귀 확인

복잡7개의 actual COM과 원본을 root가 모두 직접 비교했다. reasoning의 왼쪽 분기 fan은 복구됐지만 오른쪽 합류는 끊겨 있다. 다른6개는 emitted scene과 styles가 R14와 완전히 같으며 시각 손실도 남는다.

| 그림 | node/label | 이전 연결→현재 연결 | 남은 육안 문제 |
|---|---:|---:|---|
| original | 8/7 | 4→4 | 주요 흐름 단절, 노드/패널/설명 대량 누락 |
| reasoning-full | 24/23 | 18→24 | 합류5개와 Mixture 제목 누락 |
| blue-flow | 6/6 | 4→4 | Compact 박스·연결, Large Language 뒷부분 누락 |
| nested-panels | 30/30 | 0→0(N/A) | CFAPP 외곽·Audio/Text, 일부 설명 누락 |
| contrastive | 22/22 | 1→1 | Decoder/일부 MLP·토큰과 다수 연결 누락 |
| dark-transformer | 7/5 | 2→2 | Add & Norm 제목·방향표시·잔차 경로 누락 |
| fusion | 4/4 | 1→1 | GRU·상위 구조와 거의 모든 연결 누락 |

reasoning 복사본의 Text Embedding을 PowerPoint COM으로12pt/8pt 이동하고 라벨을 변경했다. 연결된8개 owner-pair(새6개 포함)가 유지됐고, 저장·종료·재열기 후 COM으로 attachment와 변경 텍스트를 다시 확인했다. 재열기 렌더에서도 새6개가 이동한 hub를 따라 연결됐다. 이는 자동 편집성 검사이며 사람의 수정 시간 측정이 아니다. 기존 Gating elbow는 PowerPoint가 이동 후 재라우팅하므로 원래 경로의 완전 보존으로 해석하지 않는다.

회귀: 경계 arm은1366 passed/기존2 xfailed, 분기 arm은1370 passed/기존2 xfailed. 두 실행 모두 기존 `tests/test_source_centerline.py`를 제외한 동일 테스트 범위다.9개 기존 경고가 있다. 기존43의 scene/style 동일성을 확인했고, source4의 전체 실행·추론 소스 해시 검사도 통과했다. 테스트 통과를 시각 품질 통과라고 부르지 않는다.

## 5. 육안 기록의 정정

이전 동결 보고서 `r15_visual_loss_review.md`의 “Neural Prediction1→Mixture 원본 점선이 실선으로 바뀌었다”는 관측은 잘못됐다. 이번 원본 RGB 재관측에서 해당 ray는 **원래 실선**이며, 다른5개 합류가 점선이다. 따라서 이 보존된 관계를 점선 스타일 손실로 세지 않는다. 노드/연결의 기존 분모·누락 수는 바뀌지 않는다. 이전 원문과 동결 장부는 보존하고 이 문서에 정정을 남긴다.

## 6. 다음 구현 전에 해결할 설계 항목

우선순위는 임계값 완화가 아니라 **경로 존재의 탐색과 잉크 중심선의 추정을 분리**하는 것이다. BFS는 연결성을 확인하는 용도로 두고 실제 shaft 폭/원본 support를 이용해 ray의 중심선을 관측해야 한다. 기존 `fit_observed_line`과 pixel-cell support를 재사용할 수 있는지 먼저 검사한다. ray 주변 픽셀을 임의로 잘라 바깥의 굽은 부분·분기·교차 증거를 숨겨서는 안 된다.

현재 source 직선 양성을 그대로 유지하고 굵기/방향/스케일·객체 순서 대조를 사전 고정한다. 동일 template 변형은 독립 일반화 표본이 아니다. 중심선 확인 이후에만 점선 구간 연결, 실제 접합과 단순 교차, fanin의 방향을 다룬다. 잘못된 source path를 더 많은 native preset으로 출력하는 순서는 계속 금지한다. 전체 CogBot 복원에는 경계 역할과 내용 veto 문제도 별도로 남아 있다.

이 후속 중심선 arm은 **이번에 구현·검증하지 않았다**. 현재 한정 수정은 연구 옵션으로만 남기며 production 기본값을 바꾸지 않는다.

## 7. 실행 증거 위치

모든 root 상대 경로는 `C:/vs/ImageToEditablePPT/` 기준이다. 독립 대조 경로는 `C:/Users/lpaiu/.codex/worktrees/9cae/ImageToEditablePPT/` 기준이다.

- R15.0 동결: `c9a503f`; 경계 arm: `c9b5d17`; 분기 arm: `eee6895`.
- root 경계 실행: `artifacts/region-image-only-r15/gaps-v1/`(original COM만 실행, 다른6개는 추론).
- root 분기 실행/전체 COM: `artifacts/region-image-only-r15/fanout-v1/`.
- source/PPT/XML/COM 연결 검사와 비교 이미지: `artifacts/region-image-only-r15/fanout-v1-review/audit.json` 및 같은 폴더 그림.
- reasoning 결과 PPT SHA: `18d690741b3c008078973acee206e53885182638f6d6a3e9cce2d13d36886d4b`.
- reasoning 결과 render SHA: `d6f2b008c8c5d1fbcdfaa6351650213cd29aa22c3b66fe14793fe6337c8529ef`.
- 이동/텍스트/연결 검사: `artifacts/region-image-only-r15/fanout-edit-v1/edit-probe.json`, `reopened/` actual COM. 원본 PPT는 변경하지 않았다.
- 진단: `fanout-diagnostic-v1/`는 hub 출발, `fanout-diagnostic-v2/`는 기존 캐시 방향 재현. `fanout-control-diagnostic-v2/` 역시 기존 캐시 방향이며 directed 실행의 정확한 진단은 독립 `straight-diagnostic.json`을 쓴다. `fanout-control-diagnostic-v1/`는 입력 경로에 native 하위 폴더를 빠뜨린 실패이며 결과 증거로 사용하지 않는다.
- 독립 source4/47회귀/4 baseline: `r15_directed_fanout_independent_audit.md`와 `r15_directed_fanout_controls.md`에 SHA와 범위 기록.

추론은 RGB만 사용했다. 수작업 장부·source PPT/annotation은 예측 입력으로 주지 않았다. Phase16 holdout/val/test payload는 열지 않았고 새 모델 학습·사진 다운로드는 하지 않았다. 전체 regression 안의 기존 synthetic training smoke test 실행은 별도 연구 모델 학습/채택이 아니다.
