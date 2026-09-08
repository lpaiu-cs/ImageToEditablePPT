# R15.2-A 직선 분기 탐색 방향 고정

실행 전 계약. 실패한 R15.1-A의 `boundary-gaps`는 결합하지 않는다. 제품 `closed-native-v4`는 변경하지 않는다.

## 관측과 최소 변경

reasoning-full의 Text Embedding 분기6개는 `ambiguous_multi_owner`로 탈락했다. 동일 mask와 접점에서 BFS를 hub→leaf로 실행하면6개 모두 기존 직선/끝점/화살표 조건을 충족하지만, 현재 코드는 owner 목록의 작은 index→큰 index 경로를 캐시한 뒤 뒤집는다. 그 경우 일부 shaft residual은5.44px/5.07px로 달라진다(기존2.817px 기준). 최단 경로의 grid tie가 방향에 따라 달라지는데, 이를 무방향 캐시로 취급한 것이 순서 의존 원인이다. 진단 v1은 hub 출발, v2는 실제 캐시 순서를 재현한다. 둘 다 저장 예측 geometry 기반 진단이며 fresh 추론이 아니다.

기존 `straight_fanout`에서 선택한 hub마다 hub→leaf 방향으로 경로를 찾고 방향 있는 key로 캐시한다. threshold, mask, 접점, 고유 hub 요구, 모든 leaf의 arrowhead 요구, 기존 two-owner 처리, OCR, node/content/filter, native 표현은 변경하지 않는다. 새 옵션 `--directed-fanout`은 trace+nested 모드에서만 허용하며 raw-branches/boundary-gaps와 결합하지 않는다.

원본 픽셀상의 진짜 centerline을 추정하는 일반 해법은 아니다. 같은 hub를 같은 방향으로 검사하여 owner 순서의 우연을 제거하는 한정 수정이다. 굽은 분기·교차·점선·fanin을 추가 승인하지 않는다. 신규 일반 graph/skeleton 프레임워크를 만들지 않는다.

## 검증 및 판정

1. 테스트: owner 순서를 바꾸어도 owner-pair/방향 결과 동일. 화살표 없는 분기, 일부만 화살표인 분기, 굽은 구조는 기권. 기존 기본값 결과 유지.
2. 별도 source PPT 통제: 직선 fanout, 무방향, 일부 방향, 굽은 분기의4가지 layout을 기존 도구로 작성하고 실제 COM RGB를 사용한다. 정답은 source PPT, 추론은 RGB만 입력한다. 동일 layout의 크기/객체순서 변형은 독립 표본이 아니다. 이번 통제는 calibration/eval 분할된 일반화 증명이 아닌 회귀·원인 검증이다.
3. 기존43 안전성 fresh 재실행. 유용한 기존 객체/텍스트/연결 손실 또는 새 사진 캡션/잘못된 방향·관계가 있으면 채택하지 않는다.
4. 복잡7 fresh 실행 및 actual COM 비교. reasoning-full의 source 분기6개가 올바른 owner/방향으로 native 출력되는지 확인한다.6개만 회복되어도 remaining fanin5개와 점선 손실은 미해결로 남긴다.
5. 원본 CogBot과7개 전체의 개선을 추정하지 않는다. 원래 R15 통합 목표와 생산 승인 기준은 그대로 유지한다. 실제 편집 probe는 sourcePPT와 다른 출력 복사본에 수행한다.

정밀도 회귀 시 결과/원인을 보존하고 이 arm을 고정 제품에 넣지 않는다. 출력 증가가 없더라도 cutoff를 사후 완화하지 않는다.
