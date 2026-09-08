# 부모 영역 분리 독립 RGB fixture

`tools/r10_owner_region_controls.py`는 6 종류 × scale 1/2 × AA 1/4 = 24 RGB와 evaluator 전용 annotation을 생성한다. 기존 P formal 16 fail과 artifact는 변경하지 않았다. runtime 코드를 수정하지 않았다.

## 고정 artifact

- fixture: `artifacts/r10-owner-region-v1-fixtures`
- geometry/색상 진단: `artifacts/r10-owner-region-v1-results/results.json`
- manifest SHA: `4958464ced7d1afc65317ace31b572a4f0d215ffc0268a7e066633a3b2f2051e`
- fixture lock SHA: `f6ee377a0c0b8a92ff11ffd598675527c6a7130dc35e48849185094056d4bc8d`
- builder/runner SHA: `2c56af525366b8f9687d805bde79ed20a9389cc9c51ae40558c32dfa4b3b2203`
- 관측한 root snapshot SHA: `935a85f2f5d2a924d1511194203d641e4800f7023f61706be5cbbe99729bd93d`

생성 후 manifest SHA를 고정하고 snapshot의 `propose(rgb)`에 RGB만 전달했다. 기존 데이터셋 GT/holdout은 읽지 않았다. 생성 annotation은 평가용이며 제안기 입력이 아니다. 모든 입력 SHA/RGB 불변성을 검증했다. 폰트는 Arial이며 font SHA도 lock에 기록했다.

## 구성과 실행 결과

모든 parent는 연두색 `[220,240,220]`이며 제목은 `PARENT HEADER`다. 캔버스 내 부모 면적은 13.3%로 P 25% 상한 안에 있다.

| 종류 | 목적 | snapshot geometry 관측 |
|---|---|---|
| two_children | 부모 제목 + `ALPHA ONLY`, `BETA ONLY`가 든 분홍 자식 두 개 | 네 RGB 모두 parent+children 3개 |
| square_child | `SQUARE` 자식은 종횡비 1이라 후보에서 탈락 | 네 RGB 모두 parent만 선택 |
| thin_child | `THIN CHILD`는 높이 및 종횡비 필터에서 탈락 | 네 RGB 모두 parent만 선택 |
| small_child | `ID` 자식은 너비 필터에서 탈락 | 네 RGB 모두 parent만 선택 |
| photo_icon | texture 사진 유사 패널의 `PHOTO ID`, 원형 아이콘 패널의 `ICON ID` 혼합 | 사진 frame은 선택, icon 패널은 종횡비 탈락; 전체 선택 2/2/2/3개 |
| open_child | 검은 테두리 일부만 끊은 유색 자식 `OPEN CHILD` | scale1은 자식 선택, scale2는 자식 미선택; 의미 범위 진단 |

`two_children` 네 RGB 모두 부모 내부 전체의 채널별 median은 자식색 `[240,170,180]`으로 오염된다. annotation 자식 영역과 4px 여백을 제외하면 정확한 부모색 `[220,240,220]`이다. `photo_icon` 네 RGB도 전체 median이 혼합색이며 annotation 제외 후 부모색으로 돌아온다. 이 계산은 새 runtime의 색 추정 PASS가 아니라 fixture가 색 오염을 유발함을 확인하는 진단이다.

square/thin/small의 총 12 RGB에서 자식은 실제로 selected 후보에 없다. 따라서 선택된 노드만 부모 OCR/색 제외에 쓰는 방식의 사각지대를 시험할 수 있다. 전체 raw contour를 사용한 exclusion 구현이 이들을 올바르게 처리하는지는 후속 runtime 관측이 필요하다.

`open_child`는 검은 outline에 틈이 있지만 자식 fill과 parent fill의 경계가 남는다. **실제 Canny 폐윤곽이 없다는 negative가 아니다.** 이를 사각형 환각 증거로 사용하지 않는다. `photo_icon`은 외부 사진이 아닌 seeded texture와 원형 아이콘을 합성한 의미 경계 진단이다. 폐프레임 존재 자체와 다이어그램 노드/라벨의 적격성을 구분해야 한다. scale2/AA4의 추가 후보도 여기서는 자동 FP 판정하지 않았다.

## 후속 관측 계약

manifest의 `words[].bbox`는 최종 RGB 좌표의 실제 렌더링 text bbox이며 `owner`는 parent/child0/child1이다. parent의 라벨에 자식 단어가 섞이면 안 된다. 자식이 노드 후보에서 탈락해도 자식 단어를 parent 라벨로 재귀속하지 않는다. 불확실한 텍스트의 생략은 허용한다. 별도 source-position text를 보존한다면 원본 위치/소유 영역을 유지하고 parent 제목으로 합치지 않는지 확인한다. 사진/아이콘 내부 텍스트는 부모 구조 라벨로 인정하지 않는다.

현 runner는 geometry 및 annotation 기반 색 비교 도구다. OCR, 새 owner mask 함수, 별도 text 배치, PPT 저장/렌더는 호출하지 않는다. 결과에는 해당 기능에 대한 PASS/FAIL이 없다. root가 신규 API를 고정한 뒤 같은 RGB를 변경 없이 입력해 비교할 수 있다.

재생성은 `build --out <새 디렉터리>`를, source snapshot 실행은 `run --fixtures <fixture 디렉터리> --source <closed_rect_proposals.py> --out <새 결과 디렉터리>`를 사용한다. 기존 출력 디렉터리를 덮어쓰지 않는다.
