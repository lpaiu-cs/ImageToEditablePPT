# Closed-native 실제 경로 독립 통합 감사

분류기 실패와 분리해 root CLI를 직접 실행했다. classifier를 호출하지 않았다. 기존28 COM PNG의 byte SHA 중복을 제거한20개 목록을 실행 전에 고정했다. source 파일 snapshot과 SHA를 고정하고 root에 수정 중지를 요청했다. 검사 중에는 매 입력 실행 전후 source SHA를 확인했다.

- audit lock: `artifacts/r10-closed-native-integration-v2/lock.json`
- lock SHA: `55322be560736d1f3e272cd1c28164a15d4dacaf31d6f90c47bc7482e57f3f93`
- root commit 및 모든 실행 파일 SHA/dirty status는 lock에 보존했다.
- 실행: `convert_closed_native.py --image <RGB> --output <새 폴더>`.
- 고정 설정: trace/boundary_union/owned_text/portrait_boxes/texture_guard=True. content classifier 미사용.

첫 v1은 일부 COM PNG가 palette P여서 CLI의 RGB/RGBA 계약에서 거부됐다. 불투명 P→RGB 변환을 별도 파일에 저장하고 decoded RGB pixel 동일성을 검증한 v2를 실행했다. 원본 SHA/모드/변환 SHA가 lock에 있다. 크기 변경·crop·내용 수정은 하지 않았다. v1 실패는 보존했다.

## 저장 PPT XML과 실제 COM 결과

20개 모두 CLI exit0, 출력 picture0이다. 출력 PPT를 다시 동일 COM으로 렌더했다. render manifest20개 모두 PPT/PNG SHA가 현재 파일과 일치했다(manifest SHA `8372d83e62277f1f23333979331d9991a20e7542298395dc66db84274571a9d3`). native shape/edge XML 개수와 runtime 보고 개수도 일치한다. 양성 contact sheet와 중복 실패 원본/출력 full image를 확인했다.

| 입력 | 독립 RGB 수 | 출력 box | nonblank label owner | native edge |
|---|---:|---:|---:|---:|
| native diagram | 6 | 24 | 24 | 0 |
| diagram-as-picture | 6 | 18 | 18 | 0 |
| color/gray photo 및 caption | 8 | 0 | 0 | 0 |

각 diagram 원본에는 parent1+child3+link2가 있다. native diagram의 box/label은 유지됐으나 모든12개 양성에서 link2개씩이 누락됐다. raster diagram의 출력 box 수는 순서대로3/3/3/2/3/4이며, 보존과 라벨 정확성은 별도다. nonblank18은 정확 라벨18이라는 뜻이 아니다.

## 실패 원인

**1. 부모 전체 mask가 내부 연결선을 지운다.** 모든 양성 trace audit에서 `transparent_owners=[]`, `components=[]`다. parent를 NODE로 처리해 전체 bbox를 mask한다. train-base0-native의 첫 link ROI `[291,188,312,193]`에는 raw stroke63px가 있으나 parent `[181,101,560,320]` mask 후0이다. 이는 원본 선이 없는 문제가 아니다. `trace-parent-mask-audit.json` 및 frozen `region/tracing.py`의 node 전체 mask 경로로 확인했다. 연결 조건이나 threshold를 수정하지 않았다.

**2. 실제 자식 Check가 부모 제목에도 중복된다.** eval-base1-diagram_picture에서 child `[424,216,513,276]`는 union 후보로 선택되지만 parent ownership의 children에는 Read/Build만 있다. frozen `closed_regions`는 Canny만 사용하므로 이 후보의 영역이 부모에서 제외되지 않았다. source scene과 PPT XML 모두 child=`Check`, parent=`Processoverview\nCheck`이며 실제 COM에서도 부모 제목 아래 Check가 보인다. 원본 parent 제목은 `Process overview`뿐이다.

**3. 미검출 자식 텍스트의 부모 전이도 남는다.** train-base1-diagram_picture는 Build 후보 자체가 없고 parent label=`Processoverview\nBuild`가 된다. calibration-base1-diagram_picture도 Build 후보가 없으며 부모 OCR는 기권해 Read/Check 두 개만 출력한다. 제목 공백 손실도 별도로 남는다.

**4. 사진 빈 출력은 일반 의미 판별의 성공이 아니다.** 회색 사진/캡션은 texture fraction0으로 eligible이지만 라벨 부재/OCR 양경로 기권 때문에 admission에서 제거된다. 특히 gray caption은 `Photo reference`/`Photoreference` 불일치와 source-row 불확실성으로 기권한다. 다른 안정적인 caption을 붙여도 안전하다는 근거는 없다. 이번8개 실제 RGB에서 native 오출력이0이라는 좁은 관측만 주장한다.

## 파일과 완료 범위

`artifacts/r10-closed-native-integration-v2` 아래 `results.json`, `source-snapshot`, `runs/<id>/native/{lock,result}.json`, 각 PPT, `renders/powerpoint_render_manifest.json`, `render-verification.json`, `positive-contact.png`를 보존했다. 입력 역할/파일명은 evaluator manifest에만 있으며 root CLI는 RGB 파일만 받았다. Python OS 읽기 sandbox attestation은 아니다.

원래 분류기의 실패를 이 runtime의 사진 빈 출력으로 대체하지 않는다. 반대로 이번 nested 합성 장면의 누락을 root의 다른7개 결과와 혼합하지 않는다. 새로운 학습·튜닝·기존 holdout 개봉은 없었다. COM20개 렌더 완료 즉시 root에 COM/GPU 및 source 동결 해제를 통지했다. GPU는 사용하지 않았다.
