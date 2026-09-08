# P2 부모 mask / fill 독립 실행

기존 24 RGB를 변경 없이 `closed_regions`와 `owner_region`에 입력했다. 새 fixture를 추가하거나 root runtime을 수정하지 않았다. 생성 annotation은 부모 후보 연결과 결과 평가에만 쓰이며 runtime에는 RGB 및 runtime 자체 contour만 전달했다. 실제 OCR은 실행하지 않았다.

- 결과와 source snapshot: `artifacts/r10-owner-region-p2-v1-results`
- owner SHA: `63f22cf457c702aecd3316328edcb52f1dc818d292873261837b0e034043e0e5`
- proposal SHA: `6d848db35788bb2e7af7d91dab64eae4e94ee21786abdb4642be13fdfb206bf9`
- fixture lock SHA: `f6ee377a0c0b8a92ff11ffd598675527c6a7130dc35e48849185094056d4bc8d`
- runner SHA: `f57660b416b8d5f1faacd90066092c02b98987ec2bb35d53f05fb97c569a6df5`

24개 모두 부모 후보가 있고 입력 RGB가 불변이었다. 부모 제목 bbox의 제외 비율은 전부 0이었다.

| 종류 | RGB 수 | 자식 text bbox 제외율 | 자식 내부 부모 소유율 | 부모 fill |
|---|---:|---:|---:|---|
| two_children / square_child / small_child / photo_icon | 16 | 모두 100% | 모두 0% | 모두 정확 |
| thin_child | 4 | 모두 0% | 모두 100% | 모두 정확: 자식 면적이 작음 |
| open_child scale1 | 2 | 100% | 0% | 정확 |
| open_child scale2 | 2 | 0% | 100% | 자식 pink로 오염 |

`thin_child-s2-aa1`과 `thin_child-s2-aa4`는 **실제 raw closed hole이 있어도 exclusion 크기 gate에서 누락되는 반례**다. 둘 다 외부 hole bbox `[199,299,901,337]`, 높이38, occupancy 약 .972로 관측됐다. 당시 최소 높이는 `12*1200/360=40`이다. AA4에는 높이33의 안쪽 hole도 있다. 이들은 node proposal이 될 필요 없이 부모 영역에서 분리되어야 하는 자식이다.

`thin_child` scale1 두 개에서는 자식 전체와 대응되는 raw closed hole을 찾지 못했다. 따라서 네 개 전부를 크기 gate 탓으로 단정하지 않는다. scale1은 contour 추출 범위의 한계이고, scale2 두 개는 확인된 gate 반례다. 상세 수치는 `thin-raw-contour-audit.json`에 보존했다.

`open_child`는 outline에 틈이 있어도 유색 fill의 경계가 남는 추가 진단이다. scale2의 두 누출/색 오염은 관측 사실이나, 모든 열린 구조를 복원해야 한다는 요구나 구조 환각 판정으로 확대하지 않는다.

이 결과는 mask와 fill에 한정한다. 자식 text bbox가 제외되지 않으면 후속 OCR 필터가 그 영역을 차단할 근거가 없다는 뜻이지만, 실제 OCR이 그 텍스트를 인식·승인했다는 증거는 아니다. source-position text 및 PPT 배치는 미검증이다. 기존 P formal16fail은 그대로 보존했다.
