# Pixel-agreement 독립 geometry / COM 통합 회귀

새 root 소스를 snapshot으로 고정하고 기존96 RGB×4모드×flag전후=8실행과 동일20 RGB 통합을 수행했다. 기존 결과·formal 기대값은 변경하지 않았다. root 코드·threshold를 수정하거나 classifier를 사용하지 않았다.

- proposal SHA: `e2b1ec2fc6417a428d5f90347afab31df59dcf01321622567f3cccf5cfd0fa28`
- geometry artifact: `artifacts/r10-pixel-geometry-{default,inner,dark,union}-{0,1}`
- 통합 artifact: `artifacts/r10-pixel-integration-v1`
- 통합 source/input lock SHA: `2325154b0a99d0fca9c2e874222d42bd66444ce08a3479465e178c92f9c86818`

## Geometry96

각 모드에서 flag 전후의 선택 bbox와 area는96개 전부 동일했다. 각 실행의 diagnostic24개는 formal pass/fail에 포함하지 않는다.

| 모드 | 기존 pass/fail | pixel pass/fail |
|---|---|---|
| default |56/16|56/16|
| inner |65/7|65/7|
| dark |64/8|64/8|
| union |68/4|68/4|

open/ellipse/diamond/shadow는 각각8개 모두 abstain이다. nested not_single 위반은 그대로 보존하며 실제 내부 경계 선택을 오합병으로 재명명하지 않는다. photo/glyph/table의 의미 진단 범위도 유지한다. 이 suite에서는 새 match 조건이 추가 후보를 만들지 않았으므로, 모든1px 근접 경계의 안전성을 증명하는 검사는 아니다.

## 동일20 RGB의 실제 통합

기존 nested 설정에 `--pixel-agreement`만 추가했다. 실행20개 모두 exit0이며 사진8개는 계속 box/label/edge0이다. native6은 각각4box4label2edge, raster6은 box수가3/4/3/3/3/4이며 각각2edge다. 총44box/44nonblank owner/24edge다. 전 단계는42box/42nonblank/20edge였다.

모든12개 positive의 emitted edge owner 쌍은 정확히 Read–Build 및 Build–Check다. 불필요한 parent edge는 없다. label owner 수를 문자열 정확도와 혼동하지 않는다: `Process overview`의 공백 손실은 여전히 남는다.

train-base1-diagram_picture는 새 Build child가 복원되고 parent label이 `Processoverview\nBuild`에서 `Processoverview`로 바뀌었다. 실제 COM에서4box/4label/2edge와 중복 제거를 확인했다. calibration-base1-diagram_picture도 Build가 복원되어3child/2edge가 남지만 parent는 계속 기권한다. 전체 raster6 중4개는 parent 제목/외곽이 생략된다. 즉 완전 복원이 아니라 해당 missing-child 회귀의 해결이다.

COM20개 출력의 PPT/PNG receipt를 모두 현재 hash와 검증했다. render manifest SHA는 `a8a886e598e8b053eff785777c2a8100dbc53ed2d83e1d038febdbdba132d1d0`다. `verification.json`에 전체 edge owner 쌍과 receipt 결과를 기록했다. 대표 Build 복구 두 출력은 `renders/train-base1-diagram_picture.png`, `renders/calibration-base1-diagram_picture.png`다.

기존 gray photo의 무출력을 일반 사진 판별 성공으로 확대하지 않는다. parent 외부 endpoint 링크는 이 suite에 없으므로 해당 기권 경계도 미검증이다. 사용자 편집 시간이나 미관측 데이터 성능을 평가하지 않았다. 새 튜닝 없이 결과를 보존했다. COM/GPU 사용권은 렌더 완료 즉시 root에 반환했으며 GPU는 사용하지 않았다.
