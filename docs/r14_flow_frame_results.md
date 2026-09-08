# R14 외부 흐름 테두리 실험 결과

## 목표와 판정 범위

사용자 승인 정책은 연결된 사진/아이콘 카드에서 내부 그림·글자를 버리고 관측된 폐테두리와 연결만 남기는 것이다. 정답 annotation은 추론 입력이 아니다. 복잡7개는 원본 RGB에서 fresh 실행했고, 독립 대조군은 별도로 만든 source PPT를 실제 PowerPoint로 렌더한 RGB를 사용했다. 이 개발 집합은 이미 노출되었으며 holdout 일반화나 사람 편집시간 절감을 증명하지 않는다.

## v1: 일부 개선, 캡션 누출로 채택 불가

코드 `8ff3fc9`, root 산출물 `artifacts/region-image-only-r14/flow-v1`, 실제 COM/XML/입력·코드·PPT·렌더 SHA 감사 `flow-v1-review/audit.json`.

| 그림 | 도형 | 라벨 | native 연결 | 관측 |
|---|---:|---:|---:|---|
| original | 8 | 7 | 4 | User Input 빈 카드1개와 Bot 왕복 연결2개 추가 |
| nested-panels | 30 | 30 | 0 | compact 후보4개 추가 |
| reasoning-full | 24 | 23 | 18 | R11 동일 |
| blue-flow | 6 | 6 | 4 | R11 동일 |
| contrastive | 22 | 22 | 1 | R11 동일 |
| dark-transformer | 7 | 5 | 2 | R11 동일 |
| fusion | 4 | 4 | 1 | R11 동일 |

합계101/97/30은 R11의96/93/28보다 많지만 개수는 정답률이 아니다. original·nested 실제 COM을 원본과 직접 비교했다. 원본 User Input 내부는 공백이고 입출력 선은 실제 PPT native owner에 붙는다. 편집 복사본에서 카드를 우12pt/하8pt 이동하고 텍스트를 입력했을 때 두 native 연결이 같은 owner를 유지했다(`frame-edit-v1/edit-probe.json`). 원본 PPT는 변경하지 않았다. 자동 편집성 검증이지 실제 사람의 편집시간 측정은 아니다.

nested의 추가4개 중 Tokenizer, Whisper + Tokenizer, CFLLM-ins-7B는 육안으로 유용한 복원이다. PyPDF는 원본 `PyPDF + Tokenizer`의 앞부분만 남아 완전 라벨 성공이 아니다. 외곽 프레임·여러 연결·텍스트 누락과 LLMAPIs 공백 손실도 남는다. 다른5개의 실제 COM PNG는 R11과 바이트 동일했다.

독립43개는 기존32개 출력이 R11과 같았고, 새 양성4개 중 china/flower2개만 내부 생략에 성공했다. gray는 texture fraction0.1996806으로 통과, icon은0으로 통과하여 기존 경로가 캡션을 남겼다. 이는 생략한 텍스트의 후속 부활이 아니라 대상 선정의 공백이다. 음성7개는 카드 기권했다. 상세는 `r14_flow_frames_v1_independent_audit.md`.

회귀1357 passed / 기존2 xfailed. 보존된 역사 실험 `test_source_centerline.py`는 제외했으며 기존 실패를 성공으로 바꾸지 않았다.

## v2: 내부 단색 검사의 과도한 생략

코드 `b80bc73`, root `flow-v2`, 실제 COM7개와 native 감사 `flow-v2-review/audit.json`. 기존 단색 검사 재사용으로 no-veto 사진도 대상이 되었으나 blue-flow의 정확한 `Pruned Space (Listing 4)` 라벨이 사라졌다. 합계101/96/30. 나머지6개는 v1과 같은 출력이다. 실제 원본/COM을 직접 확인해 **유용한 구조 라벨 손실로 채택 불가**로 판정했다.

`flat-diagnostic-v2/blue-flow/closed-0.png`에서 미설명 픽셀을 적색 표시해 직접 확인했다. 0.1265의 미설명 비율은 내부 사진이 아니라 테두리 밴드였다. 경계에 연결된 성분을 분리한 cached OCR 진단에서는 중앙 미설명 비율0, 원본 User Input은0.2261 그대로다. 이 진단은 fresh 추론 증거와 구분한다.

독립 v2의 최초43 실행은 진단 도구를 root가 수정하여 broad source hash lock이 달라졌고 29개 결과에서 중단됐다. 이를 온전한43회 검증으로 세지 않는다. 원인·부분 산출물을 보존하고 새 lock의 새 폴더에서 새11개를 별도 실행한다. root inference lock 대상 코드·spec은 실행 중 변경되지 않았다.

v2 선행 결과에서 gray 생략은 개선됐으나 icon의 Input은 남았다. 사람 아이콘 몸통이 무라벨 raw 폐박스 후보로 잡혀 parent 전체 제외 조건에 걸렸다. 또한 상호 후보를 frame-only에서 제외해도 기존 ordinary admission에 양쪽 caption이 남을 수 있다는 정책 단위 반례를 독립 검토가 제시했다. RGB 실험에서 입증한 결과와 이 코드 경계 반례를 혼동하지 않는다.

회귀1358 passed / 기존2 xfailed /9 warnings (`regression-v2.xml`). 테스트 통과는 위 육안 회귀를 상쇄하지 않는다. 기본 CLI는 아직 closed-native-v3이며 production 승인하지 않는다.

## v3: 경계 성분 전체 제외의 실패

코드 `cd036c3`, root fresh7개 및 실제 COM7개 `flow-v3`. blue-flow 라벨은 복구되고 root 결과는 v1과 같지만 독립 gray-flow의 Photo 캡션이 다시 남았다. 내부 사진의 편차 성분이 경계에 연결되어 통째로 제외됐기 때문이다(0.5183821→0.0036176). icon은 내부 단독 무라벨·무연결 조각을 생략하면서 빈 frame으로 개선됐다. 독립43개는 모두 fresh 완료했고 source hash guard를 통과했다. v3 또한 채택하지 않는다.

1360 passed / 기존2 xfailed /9 warnings. 내부 linked child와 상호 ordinary 기권은 추가 정책 단위 검토에서 확인했으며 이것을 새로운 RGB 독립 사례의 성공으로 세지 않는다.
