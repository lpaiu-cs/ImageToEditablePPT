# R10: 실제 새 추론 B/H/G 결과와 복잡 도식 전이

## 결론

동일한 합성 검증15개에서 RGB 새 모델 추론부터 native PPT까지 실행한 결과, 실제 native 연결은 **53정답 / 0오답 / 14누락**, 노드 라벨은 **87정답 / 0오답 / 4공백**이었다. 이전 O/C/S/T 실행의 native 44정답/2오답/23누락보다 개선됐다. 그러나 이 결과만으로 프로덕션에 도달했다고 결론내리지 않았다. 원본 `input.png`와 별도 복잡6개에서는 앞단 모델이 큰 가짜 owner와 중복 라벨을 만들어 실패했다. 따라서 실제 폐윤곽을 직접 제안하는 P 경로를 구현하고 검증을 계속했다.

## 실제 실행 경계

- 실행 Git: `aaf42a18510a6daf64a8c6535e70036117f23de0`
- 실행 자료: `artifacts/region-image-only-r10/fresh-bhg`
- checkpoint SHA256: `e6a6926ef4e65e11288d61d3b12723b19322ee0d44e6e94b9075cba11a1a6f58`
- 모델 새 forward 154개 후보 → 선택105개 → 최종91개 node와11개 container.
- 이미지 RGB와 checkpoint가 추론 입력이다. GT는 별도 evaluator가 PPT 생성 후 읽는다. Python 읽기 감사이지 OS sandbox는 아니다.
- 실제 PowerPoint로15개를 렌더링했다. cached B/G/H 진단과15개 PNG가 byte-identical임을 확인했고, 한글 비교시트3개 전체를 직접 확인했다.
- 이는 이미 공유된 synthetic validation 진단이다. 독립 holdout 또는 사람의 편집시간 절약 검증은 아니다.
- 레거시 checkpoint의 학습 코드 SHA/원래 클래스명 기록이 불완전하다. 새 forward 실행 증거가 과거 학습 provenance의 빈칸을 채우지는 않는다.

## 결과

| 항목 | 정답 | 오답 | 누락/공백 |
|---|---:|---:|---:|
| node 역할 | 91 | 0 | 0 |
| node 정확한 kind 계약 | 80 | 11 | 11 |
| container | 11 | 0 | 0 |
| 추적 후보 연결 | 56 | 3 | 11 |
| 실제 PPT native 연결 | 53 | 0 | 14 |
| node 라벨 | 87 | 0 | 4 |

kind 계약의11건은 원본 원형 노드를 G가 ellipse로 복원했지만 레거시 GT가 box로 기록한 차이다. 표의 동결 수치는 바꾸지 않았으며, 실제 원형 복원을 시각 오류11개로 부르지 않는다. 최종 연결53개의 owner 쌍과 방향은 모두 맞다. 누락14개는 여전히 누락이며 성공 개수로 세지 않는다.

육안으로 표/스택/트리와 원형 노드의 개별 편집 가능한 배치는 개선됐다. 일부 그래프는 관계 누락이 많다. 특히 graph_1302_00029는 올바른 노드는 나왔으나 관계가 거의 비어 있어 완성본으로 부적합하다. 선 두께·장식·구획 스타일의 단순화와 구조 누락은 구별했다. 공백4개는 graph의q0와 트리의dog/V/V이다.

## 독립 반례의 해석

- B는 기존 검증된 두 owner 사이의 실제 선 중심만 수정한다. 새 owner 또는 방향을 만들지 않는다.
- H는 전체 화살촉의 실제 채워진 본체를 검사한다. 초기 compact T 글리프 오인 반례를 수정했다. 독립 v2의936검사 중918formal pass, 정상 화살표14기권, 경계 접촉4formal 위반이 남았다.
- 경계 접촉4건은 진짜 채워진 화살표의 올바른 방향이다. owner 주변2s 제외띠 안의1픽셀 수준 부가 접촉을 관측하지 않는 범위 문제이며, 잘못된 방향4개로 해석하지 않는다. 기존 `any contact abstain` formal 실패는 삭제하지 않았다.
- G 독립602 유효 raster 검사에서514formal pass/정상88기권이었다. 큰 자식 색을 부모 채움으로 승격하는 반례는 수정했고, 해당 negative에서 거짓 채움은0이었다.
- 최종 H가 참조하는 G의 contour 노출 추가는 별도로 잠겨 있다. 서로 다른 source snapshot의 검사 숫자를 같은 실행처럼 합치지 않는다.

## 복잡 도식에서 새로 드러난 원인

동일 B/H/G를 기존 real dev6개에 실제 적용하고 원본과 native 출력6개를 육안 확인했다. 이 실행의 객체 개수는 정답 개수가 아니다. reasoning의 큰 가짜 사각형, nested-panels의 중복 라벨·부모/자식 색 혼합, fusion의 큰 가짜 세로 owner와 나뉜 질문, dark-transformer의 과대 owner가 남았다. 원래 `input.png`도 같은 앞단 검출 문제로 실패했다.

이는 화살촉이나1픽셀 적합도 조정만으로 해결할 수 없는 모델 전이 문제다. 후속 P/P2는 **RGB의 실제 폐윤곽 → 소유 영역 분리 → 신뢰 라벨 → 증거 있는 native 연결**로 앞단 경계를 바꾼 별도 경로다. 모델 경로의 성공을 P 경로에 전가하거나 반대로 동결 모델 결과를 덮어쓰지 않는다.

## 증거 SHA256

| 파일(fresh-bhg 아래) | SHA256 |
|---|---|
| detector/predictions.json | `94df7d23e0ec14eefcb6e9381bc515d8d0ae811e2054ec67272c2db8a75eb36b` |
| detector/execution-lock.json | `66ccf7e954d64a87a0a512cce972c084c0c3fd6fa9f68d544906fa85e1d3dafa` |
| handoff.json | `053763545bf9b46a79d95ea3fd26aee2a7a8d043458701aa15835b22388dff02` |
| native/lock.json | `054b5413f2883067aacaa8e8a25678a17d368058c0fc5b7a04c9676f5f156f95` |
| native/results.json | `20ad6ac3522f6aff03fcd9b0cc2ac1240490f376da1dc05fefe184962c4ec531` |
| native/evaluation-ko.json | `7daf08b062df196eb3521278f00688be0d0e31a6bf9efdadd4b054d3001f6653` |

주 결과와 비교 그림은 `native/evaluation-ko.json`, `native/review-ko`를 사용한다. 앞선 언어 표기 문제가 있던 review는 재사용하지 않고 원본 기록으로 보존했다.
