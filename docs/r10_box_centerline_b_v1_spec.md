# B-v1: 기존 두-owner box 연결의 원본 중앙선 보정

새 관계/방향을 만들지 않는다. `r3_stroke_trace` 및 그 연속성 provenance를 가진 기존 connector의 양쪽 owner가 node box/rounded_box일 때만 검사한다. 동일 pair 중복, 겹친 owner, 누락 owner, 기타 source와 label-anchor는 기권한다. 함수 `refine_box_centerlines(scene,rgb) -> (scene,audit)`는 원래 connector의 path_points만 바꿀 수 있다. ID/owner/방향/port/나머지 scene을 보존한다. C-v2/source rays/native writer를 수정하지 않으며 native4px gate는 별도 유지한다.

## 고정 관측 계약

- uint8 RGB,밝은 배경, s=H/360. 원본 dark ink는 정수휘도(2126R+7152G+722B)<130×10000이다. 복구·팽창·closing된 픽셀은 증거가 아니다.
- 기존 두 끝점 chord의 중앙20~80%,횡단8s 범위로 TLS를 제안한다. seed>=12pixel,장축분산>=4×단축,원본 p95<=2s/max<=3s,span>=12s.
- 축은 두 owner bbox를 모두 지나야 하며 안쪽 교점 간 span>=24s. 새 끝점 이동<=6s,기존 경로의 축 잔차<=6s. 제3 node bbox와의 교차 또는 2s이내 접근은 기권한다.
- owner 경계의 테두리 혼입을 피하는 관측 제외 띠는3s이다. 원본 배열은 변경하지 않고 topology query에만 적용한다. 끝점 인근 제외가 근거 없는 연장으로 이어지지 않도록 실제 지원 끝부터 bbox교점까지 각6s이하로 제한한다. 이 띠 안의 촉/윤곽을 복원했다는 주장은 하지 않는다.
- 제안 축 기준 bbox외부 longitudinal 0..L에서, 두 owner의3s띠 밖 원본8CC를 조사한다. 중앙 seed와 연결된 성분은 정확히 하나여야 한다. 횡단8s 이내의 다른 성분이 있으면 기권한다. 선택 성분 전체를 확인해 corridor 밖 가지를 잘라 숨기지 않는다.
- 중간8s..L-8s 원본 잔차 max<=3s,양끝부 max<=6s. 교차/분기/굽은 획/평행 경쟁이 이 관측을 넘으면 기권한다. 중앙 TLS만으로 승인하지 않는다.
- 정수 raster center 주변 물리1×1pixel-cell의 축 투영 구간 합집합으로, 실제 지원 양끝 사이 지지율>=.95,최대 내부 공백<=2s. 양끝연장은 별도6s로 제한한다.

## 검증과 한계

Pillow 독립 RGB 양성은 box/rounded_box 두 개와 직선,방향 flag 양쪽/없음,회전/scale,기존 경로의 작은 가장자리 흔들림을 포함한다. 음성은 gap,elbow/curve,parallel,crossing/branch,제3owner,owner miss,큰 endpoint변경,중복pair,다른source/label-anchor이다. 최종 래스터가 명목 geometry를 실제로 구현하는지 실패별 확인하며 기대/계약을 소급 변경하지 않는다.

원본에서 서로 구분할 수 없는 윤곽-connector 접촉과3s띠 내부 구조는 초기 범위 한계다. 방향은 기존 flags를 보존하므로 잘못된 방향을 수정하지 않으며,기존 무방향선을 화살표로 바꾸지 않는다. 실제15는 root의 별도 승인된 실행으로 검증한다. 이 module은 GT/annotation/OCR/PPT 파일을 읽지 않는다.
