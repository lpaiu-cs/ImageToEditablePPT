# R12 원본 분기 보완 결과와 기본 경로 미채택

## 결론

선 합치기 morphology가 가까운 분기를 하나의 다중-owner 성분으로 만들어 기권하게 하는 원인은 확인했다. 그러나 독립 반례 수정까지 거친 v2의 실제 개선은 알려진 reasoning 그림에서 **방향 없는 선1개**뿐이다. 신규 경로를 기본 CLI에 채택하지 않고 연구 arm으로 남긴다. 기본은 R11 `closed-native-v3`이며 production 승인은 false다.

## 실험과 반례

- 기존 R11 reasoning은 native24도형/23라벨/18연결이었다.
- R12 v1(`8d14c24`)의 fresh 결과는24/23/20이었다. 실제 PowerPoint에서 Text Embedding→Decoder2/3 위치의 두 선을 직접 확인했다. 원본 화살촉을 확정하지 못했으므로 native LINE이며 방향 복원 성공으로 세지 않는다.
- 독립 gray120 교차선 반례에서 LINE1개를 잘못 승인했다. 앞단의 local-contrast dark<110 mask가 곁선을 지우고 뒤의 B-v1/H는 dark<130 관측을 사용하던 증거 불일치가 원인이다. v1 결과를 삭제하거나 성공으로 재분류하지 않았다.
- v2(`b400dc3`)는 새 raw 경로만 B/H와 동일한 원본 integer luminance<130으로 바꿨다. 같은 반례 RGB SHA로 added0/기권을 확인했다. default legacy mask와 B/H의 수치 기준은 바꾸지 않았다.
- v2 reasoning은24/23/19다. 실제 COM 화면에서 Decoder3로 이어지는 선1개를 직접 확인했다. 나머지 분기와 화살촉 미복원은 그대로이며, 이 정도 증가를 근본적 일반화 향상으로 부르지 않는다.

## 검증 경계

복잡7개는 두 버전 모두 RGB부터 실행했다. v2는96도형/93라벨/29native연결/삽입이미지0이다. reasoning 이외6개 COM PNG는 R11과 byte-identical이다. 두 버전의 모든7개 native bbox/라벨/양종점·입력/PPT/COM SHA 감사를 통과했다. 감사는 출력의 일관성과 native 연결을 검증하며 정답률을 만들지 않는다.

독립 source PPT/COM32개도 v1/v2 각각 fresh로 실행했다. 모두 exit0, R11과 emitted_scene 전체가32/32 동일하다. 양성12개44도형/44nonblank/24연결, 사진20개 shape/edge/picture0이다. 새로운 분기 양성이 없는 회귀 집합이므로 이것만으로 분기 복원의 효용을 증명하지 않는다. 사진20개는 여전히 원본2개에서 파생됐다. 독립 감사 문서 `r12_raw_branches_independent_audit.md`, `r12_raw_branches_v2_independent_audit.md` 참조.

v1 회귀1338 passed/기존2 xfailed, v2는1339 passed/기존2 xfailed다. 기존 C-v1 파일의 별도 동결 제외는 유지한다. v2에는 평행선·끊김·곡선·교차·gray120교차·제3 owner·중복/기본 경로 불변을 포함한9개 직접 회귀가 있다. cutoff 밖 저대비 곁선, 일반 접합 의미, 사람의 수정시간은 미검증이다.

## 산출물

- root: `artifacts/region-image-only-r12/raw-branches-v1`, `raw-branches-v2`
- 완전 COM 감사: `raw-branches-v1-review-complete/audit.json`, `raw-branches-v2-review/audit.json`
- 회귀: `regression.xml`, `regression-v2.xml`
- worker: `C:/Users/lpaiu/.codex/worktrees/9cae/ImageToEditablePPT/artifacts/r12-raw-branches-v1`, `r12-raw-branches-v2`

렌더 중 PowerPoint 종료 지연으로 guard가 작업을 중단한 시도는 남겼다. 사용자 PowerPoint를 종료하거나 guard를 우회하지 않았다. 완료된 파일은 SHA로 검사하고 누락된 파일만 새 렌더했다. 부분 감사 디렉터리 `raw-branches-v1-review`는 실패 기록이며 완전 감사와 구별한다.
