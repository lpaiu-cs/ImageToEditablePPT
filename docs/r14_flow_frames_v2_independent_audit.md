# R14 v2 독립 감사: 새11건 중 아이콘 내부 생략 실패

새 양성4건 중 china/flower/gray3건은 no-fill·빈 텍스트 테두리가 됐지만, icon-flow에는 Input이 남았다. 음성7건의 카드는 기권했다. **v2 새11건은 완료했으나 전체43건 완료를 주장하지 않는다.** root가 별도 복잡 도식에서 정상 라벨 손실을 확인하여 채택 불가로 보존하고 작업 범위를 새11건으로 줄였다.

## 실행 경계와 중단 기록

root commit은 `b80bc738623be1ac19244b0d1a75366ad26bac9e`다. 첫 `artifacts/r14-flow-fresh-v2` 실행은29건 이후 외부 해시 guard가 중단시켰다. 변경 파일은 추론 경로 밖 `tools/probe_flow_frame_content.py` 하나로, SHA가 `a426de49bd909e53cd1d04cfce456ab78bc78df77080c3e75fdce262d1cb9071`에서 `16158a0894cbb354f5cac723c570de6b1379343013b8e76541875acd96a901cd`로 바뀌었다. 부분 실행을 보존하고 무시하거나 성공으로 재분류하지 않았다.

새 `artifacts/r14-flow-fresh-v2-rerun`은 동일43 records를 새11건 우선 순서로 실행했다. 이전 lock과 변경 파일이 위 진단 파일 하나뿐임을 assert하여 추론 core 동일성을 확인했다. 재실행 lock SHA256은 `f5fcaff789e3bfaf7a4ec071479062d741c9ca7bae4d5cfc1230ee6689a7aaa8`다. 새11건 완료 이후 root의 범위 축소 요청에 따라 audit 프로세스를 종료했다. 종료 조치 중 구32건 일부도 실행됐지만 전체 회귀 완료로 세지 않는다. root source 동결 해제를 통지했다.

추론은 RGB부터 새로 실행했고 이전 OCR/PPT/정답 metadata를 입력하지 않았다. source11은 사전 고정한 R14 controls 그대로이며 fixture·cutoff를 수정하지 않았다.

## 새11건 결과

| 입력 | 관측 |
|---|---|
| china-flow, flower-flow, gray-flow | 각각3도형·2라벨·2연결, 카드 noFill/빈 텍스트 |
| icon-flow |3도형·3라벨·2연결, Input 잔존으로 내부 생략 실패 |
| both-in/out, failed-chain, no-arrows, one-way, same-port | Read/Check2개만 유지, 카드/관련 연결0 |
| standalone | 도형·라벨·연결0 |

11개 최종 PPT XML에서 picture0을 확인했다. 보완3건은 noFill/빈 a:t와 source witness 양 끝 attachment ID를 확인했다. 실제 COM11개를800×450 렌더하고 모든 PPT/PNG receipt SHA를 검증했다. 회색 사진의 빈 테두리와 icon-flow의 Input 잔존을 실제 PNG에서 직접 확인했다.

- COM manifest SHA256: `75e91580f78f7b44c8e223e329eaf6dfd29104b26babd05816cacd64dce914cd`
- `new11-results.json`: 완료11건 native 집계
- `verification.json`: XML/receipt 결과 및 실패1건
- `renders/gray-flow.png`, `renders/icon-flow.png`: 실제 출력

COM은 완료 즉시 반환했다. 기존 R11/새 v1 결과는 그대로 보존한다.

## icon 실패 원인

부모 closed:3은 nontext unexplained_fraction `.28108131638516454`로 내용 생략 대상이다. 그러나 내부 인물 몸통이 closed:2, bbox `[335,234,466,318]`, label=None인 사각형 후보가 되어 모든 내부 후보를 배제하는 parent guard에 걸린다. 따라서 witnesses는 비고 일반 경로의 Input이 남는다. 내부 몸통은 실제 proposed connector의 owner가 아니다. 연결은 closed:1→closed:3 및 closed:3→closed:0뿐이다.

내부 후보를 단순히 '무라벨이므로 비구조'라고 해석하면 실제 무라벨 구조를 삭제할 수 있다. 후속 parent 완화는 실제 연결된 child와 반복 구조의 보존 조건을 따로 검사해야 한다. 이 보고서는 parent guard를 임의로 완화하지 않았다.

## mutual 경계와 판정 제한

root의 scene_pair 정책 fixture에서 두 owner 모두 기존 texture eligible=True이고 nontext 대상이면 frame_witnesses는 빈 집합을 반환한다. 그러나 같은 scene의 admitted_ids는 frame/seed 둘 다 유지한다. 따라서 v2는 '상호 frame-only 보완'을 거절하지만 일반 경로의 양쪽 Caption까지 없애지는 않는다. 이는 정책 단위와 호출 흐름으로 확인한 한계이며 별도 RGB 재현을 완료한 것으로 부르지 않는다. 기존 failed-chain 사진 대조는 texture 실패 카드이므로 이 no-veto mutual 경우를 커버하지 않는다.

root가 확인한 blue-flow 정상 라벨 손실은 별도 root 검증이다. 이 worker의 새11건 결과로 그 회귀를 취소하거나 직접 검증했다고 말하지 않는다. 새11건 자체도 icon 실패가 남아 v2의 완전한 정책 달성을 주장할 수 없다. 사진2자산·합성아이콘1개라는 제한, 실제 사용자 수정시간 미측정은 그대로다.
