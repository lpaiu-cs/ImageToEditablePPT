# R10 S/T/F 중간 결과: 이미지에서 새 추론까지 연결

## 이번 결과와 아직 해결되지 않은 부분

원본 선 관측 S와 공간/방향 일치 OCR T를 적용해, 기존 A-T 대비 native 연결의 정답은 26→44, 오답은 5→2로 바뀌었다. 라벨은 정답 82→87, 오답 1→0, 공백 8→4다. 새 검출기를 실제로 실행한 뒤 RGB에서 OCR·중복 선택·선 추적을 다시 수행해도 동일한 결과를 얻었다. 이전 장면의 정답 라벨이나 관계를 렌더러에 공급하지 않았다.

하지만 전체 완료가 아니다. 원형 노드의 사각형 복원, 박스형 도식의 연결 누락, 흐릿한 테두리는 육안으로도 분명히 남는다. 이번 기록은 다음 수정의 비교점이지 연구 중단이나 제품 승인 선언이 아니다. G(닫힌 노드 윤곽)와 B(박스 연결 중앙선)에서 실제 수정을 계속한다.

## 별도 평가

| 항목 | 이전 A-T | O+C+S+T 및 fresh detector→native |
|---|---:|---:|
| node TP/FP/FN | 91/3/0 | 91/0/0 |
| container TP/FP/FN | 11/0/0 | 11/0/0 |
| native relation TP/FP/FN | 26/5/41 | 44/2/23 |
| 라벨 정답/오답/공백 | 82/1/8 | 87/0/4 |

새 실행의 raw detector 출력은 154개, 고정 threshold/NMS 후 105개다. O가 중복 node 3개를 제거하고 node 91·container 11을 남겼다. GT 평가는 생성 완료 후 다른 프로세스에서 수행했다. node kind 91 정답은 legacy 주석 계약 기준이며, 원형 RGB를 box로 표기한 과거 계약까지 시각적으로 옳다는 뜻이 아니다.

트리 012/013/014의 native 연결은 각각 6/6, 7/7, 9/9다. 공백 4개는 graph005의 q0, tree012의 dog/V, tree014의 V다. 모호한 OCR을 정답 문자열로 채우거나 신뢰도 문턱을 낮추지 않았다.

## 육안 확인

15개 PPT를 실제 PowerPoint COM으로 1280×720 PNG로 렌더했다. 세 contact sheet 전체와 트리 확대를 직접 보았다. 트리 분기·중복 라벨·화살표 방향은 이전보다 유용한 편집 초안으로 개선됐다. 반면 block_flow001에는 연결이 모두 빠졌고 graph004에는 연결이 없으며 원도 사각형으로 나왔다. 이 결함을 표의 node 정답 수로 덮지 않는다.

cached O+C+S+T와 fresh RGB detector→native의 **15개 PowerPoint PNG가 바이트 단위로 모두 동일**했다. 이는 이 노출된 15개에서 실행 경로 변경 후 결과가 유지됐다는 뜻이며 새 이미지 일반화를 입증하지 않는다.

## S의 독립 음성 대조

원본8CC, 촉 밑변/수렴, 반대편 분리 촉의 불확실성 veto, owner 안으로 들어가는 실제 잉크 접촉 검사를 추가했다. 현재 source_rays SHA는 `20d049deab58641582d3984db0707bb3cd13b60d3ef3f83af10ba8a84e4ea002`다.

- 독립 기본 대조 1980회: 1968 통과, 음성 오승인 0, 양성 기권 12. 크기/회전/AA의 고유 이미지 수와 순서 반복을 구별한다.
- owner mask 대조 672회: 동결 계약상 642 통과. 나머지 30은 실제 mask 효과 없는 12와 원본 경계 0~1px fringe 18이다. 이 30개를 의미 오류 30개로 주장하지 않는다. raw owner 내부는 더 이상 지우지 않는다.
- 분리 촉 v3: 생성 660개 중 최종 raster topology 유효 501개, 양순서 1002회. 음성 오승인 0, 깨끗한 양성 4회와 근처 성분 양성 4회 기권. 유효성 탈락 159개는 삭제하지 않는다.

최초 실패와 수정별 대조 기록은 `r10_independent_controls_final_history.md`에 남았다. 최종 root 재실행을 worker의 독립 재현으로 바꿔 쓰지 않는다. C-v1의 과거 6개 테스트 실패와 C-v2 수정 계약도 그대로 보존한다.

## 재사용 경로와 증거

`tools/convert_source_evidence.py`는 단일 RGB+checkpoint 입력에서 새로운 detector forward→OCR/O/C/S/T→native PPT를 실행한다. tree014 RGB를 실제 명령으로 실행해 node10·label9·connector9의 PPT를 얻었다. 테스트용 호출이나 이전 prediction 재생이 아니다. 실행 산출물은 `artifacts/region-image-only-r10/single-image-cli/`다.

현재 모델은 훈련 class 이름·훈련 codeSHA가 checkpoint에 기록되지 않았다. 명시적인 legacy class adapter와 연구 전용 확인 플래그를 요구한다. 새 forward 실행의 증거 확보가 과거 훈련 출처 문제를 소급 해결하지는 않는다. Python audit hook은 OS sandbox가 아니며, native IO까지 모두 통제했다고 주장하지 않는다.

주요 SHA는 `benchmarks/r10_source_text_fresh.json`에 있다. 현재15는 이미 노출된 synthetic validation이고 Phase16 holdout을 열지 않았다. 사람의 실제 수정 시간 절감/실제 드래그 승인과 제품 배포 승인은 아직 별개다.
