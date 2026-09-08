# Nested-owner 별도 arm 독립20 RGB 회귀

root `e698700db531bf24812d4eb07ae818d0a6b962f1`의 파일 snapshot을 고정하고, 기존 RGB20개의 ID와 SHA가 이전 통합검사와 정확히 같음을 확인했다. 기존 CLI는 변경하지 않고 probe의 trace/boundary-union/owned-text/portrait-boxes/texture-guard 설정에 `--nested-owners`만 추가했다. classifier는 사용하지 않았다.

- artifacts: `artifacts/r10-nested-owner-integration-v1`
- source/input lock SHA: `80962e73cf4739a2af03f1866271ffccbb960171b2929edcef8c6b70e8fed529`
- probe SHA: `6ad382bd7bebf7214436b1f1ecf2f7e0acbec515531a30989ac761e6623e53e4`
- COM render manifest SHA: `73db95d1f96ade39c61a095bcfc02d219d2b23e878f3acc4f9e34bf3bb109025`

20개 모두 exit0이며 출력 picture0이다. 실행마다 source SHA를 재검증했고, COM20개의 PPT/PNG receipt도 모두 일치했다. COM 완료 즉시 root에 사용권을 반환했다. GPU는 미사용이다. 사진8개는 이전처럼 box/label/edge0이며 회색사진의 의미 판별을 입증한 결과는 아니다.

| 입력 | box/label owner | 이전 edge | nested edge |
|---|---:|---:|---:|
| native6 | 24/24 | 0 | 12 |
| raster diagram6 | 18/18 | 0 | 8 |
| 사진8 | 0/0 | 0 | 0 |

box 수는 바뀌지 않았다. native6은 각각2edge, raster6은 순서대로2/0/2/0/2/2edge다. 예상 총24개 중20개가 복원되고 Build 미검출 두 raster의4edge가 여전히 누락된다. 이 suite에는 parent로 직접 들어오는 외부 링크가 없어서 그 기권 경계를 실제로 시험하지 않았다.

## 해결 확인

eval-base1-diagram_picture의 parent label은 `Processoverview\nCheck`에서 `Processoverview`로 바뀌었다. child Check는 그대로 남고 실제 COM에서 중복이 없어졌다. 이 사례는4box/4label/2edge다. 파일은 `rgb/eval-base1-diagram_picture.png`, `renders/eval-base1-diagram_picture.png`, `runs/eval-base1-diagram_picture/native/result.json`이다. snapshot의 union contour exclusion과 border-only trace arm으로 앞서 확인한 두 문제의 해당 사례가 해결됐다.

## 남은 실패

train-base1-diagram_picture는 Read/Check/parent3개만 있고 parent label=`Processoverview\nBuild`다. 실제 COM에서도 부모 제목 아래 Build가 남는다. ownership pool에는 실제 Build contour가 없고 nested trace는 parent를 border-only로 전환했지만 미검출 Build를 새로 만들지 않는다. calibration-base1-diagram_picture도 Build가 없고 parent는 무라벨 기권해2box/2label/0edge다.

원본 RGB에서 Build의 dark hole을 독립 재측정했다:

| threshold | bbox xyxy | 크기 | contour occupancy |
|---|---|---|---:|
|130|[313,169,403,229]|90×60|.971574|
|170|[313,169,402,228]|89×59|.971624|

최대 좌표차는1px지만 bbox IoU는 `.9724074074`로 현재 `.98` match 조건을 만족하지 않는다. 결과는 `build-dark-hole-audit.json`에 저장했다. 이는 **기존 v1 탈락 원인 증거**이며 새1px 충분조건의 안전성·정당성을 검증한 것이 아니다. 새 조건을 실행하거나 threshold를 튜닝하지 않았다.

모든 이전 실패/분류기 결과는 보존했다. 두 full COM 실패/복구 이미지를 확인했으며, 이 결과는 이미 공개된 개발 회귀다. 일반화 또는 production 승인으로 확대하지 않는다.
