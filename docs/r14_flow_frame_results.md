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

## v4 최종 개발 검증과 연구 preset 채택

실험 코드 `a22bc16`. 경계 성분 전체 대신 기존 동일 테두리 허용 폭 max(2,3s) 내 픽셀만 제외했다. 새로운 모델·외부 의존성 없이 기존 단색 검사와 native 지원 검사를 재사용했다. 이 거리 상한을 넘는 두꺼운 테두리의 라벨 보호는 보장하지 않는다. 단위 fixture의 테두리12px를6px로 변경했고 경계에 이어진 중앙 그림을 추가했다. 이전12px 조건까지 그대로 통과했다는 뜻이 아니며, 실패 버전/실제 회귀를 보존했다.

- 복잡7개 fresh 및 실제 COM7개 완료, `flow-v4-review/audit.json`의 source/코드/PPT/XML/렌더 결합 감사 통과. 7개 COM PNG는 v1과 바이트 동일하다. 합계101도형/97라벨/30native 연결이며 원본8/7/4, nested30/30/0이다.
- root는 최종 original/nested/blue 실제 COM을 원본과 직접 비교했다. 원본 빈 카드와 두 선의 관측 근거, nested의 추가 박스 및 PyPDF 불완전 라벨, blue의 정상 라벨 복구를 확인했다. 기존에 누락되던 다수 연결·텍스트가 해결됐다고 주장하지 않는다.
- 최종 원본 PPT `flow-v4/original/result.pptx` SHA `b39946233cf435df0270f28a26f590fa778d9ff33f911425446613139d81294a`. 실제 COM SHA `28059bc5120db127013f5a60166e106fba50a7c675dad837538510617a32eea1`.
- 최종 편집 복사본 `frame-edit-v4/edit-probe.json`: 빈 카드에 글자 입력 및 우12pt/하8pt 이동 후 두 실제 연결의 owner 유지와 좌표 변경을 확인했고 원본 SHA는 보존했다.
- 독립 fresh43개와 실제 COM43개 모두 완료했다. 기존32개 emitted_scene은 R11과 완전히 동일하며 단독 사진20개는 실제 렌더 전 픽셀 흰색이다. 새 양성4개는 모두 frame noFill/빈 text/picture0/입출력 native attachment를 만족했다. 음성7개에서는 카드가 생략됐다(주변 정상 Read/Check는 남을 수 있음).
- root도 gray/icon 최종 COM을 직접 확인했다. 두 PNG는 같은 빈 frame+Read/Check 구조로 SHA `fadbfe48aec1359d8e58c9a47d43aa4405ff71a03d89511e7909e9e20fe872cf`가 같다. 독립43 결과는 `r14_flow_frames_v4_independent_audit.md`, 산출물은 독립 worktree의 `artifacts/r14-flow-fresh-v4`에 있다.
- 회귀1360 passed / 기존2 xfailed /9 warnings (`regression-v4.xml`). 역사 실험 제외 범위는 위와 같다.

이 검증 범위에서 R14 실험 v4를 고정 연구용 CLI `closed-native-v4`로 채택했다(`d4d48ef`). `handoff.json`은 빈 frame ID와 `production_approved:false`를 명시한다. 기존 CLI 이름은 유지하고 설정만 고정 버전으로 올렸다. 사용 방법은 `closed_native_research_usage.md`.

### 최종 CLI 자체 확인

채택 후 CLI/flow 관련17개 테스트를 다시 통과했다. 최종 명령으로 원본·gray-flow·standalone3개를 fresh 실행했고 실제 COM3개와 native/XML/receipt 감사를 마쳤다(`cli-v4-review/audit.json`). 결과는 각각8도형/7라벨/4연결, 3/2/2, 0/0/0이다. 마지막 음성은 `no_confident_structure`이고 실제 PNG 전 픽셀이 흰색이다. 세 실행의 runtime 코드 SHA는 최종 파일과 일치한다.

사용자에게 제공할 최종 파일은 `artifacts/region-image-only-r14/cli-v4/original/native/result.pptx`이며 SHA `f8ec7c648e9b922948e084a4177c33a60bef7111ef81b69c29228e2e71b7719b`다. 실제 COM은 실험 v4 원본과 바이트 동일했다. 전체 회귀1360개는 최종 inference 코드에서, CLI 채택 뒤17개와 fresh3+COM3는 최종 wrapper에서 검증한 별도 증거다.

## 남은 문제와 다음 검증 경계

확인된 개발 반례의 캡션 누출/정상 라벨 회귀는 해결됐다. 그러나 사진 원본은2개, icon은1개이고 grayscale은 새 독립 사진이 아니라 파생물이다. 일반 사진·아이콘 의미 분류, 두꺼운/연한/질감 테두리, 모든 무라벨 내부 구조 보호는 입증하지 못했다. PyPDF 등 prefix-only OCR, 누락된 라벨·다중 분기/점선 연결은 별도 과제다.

따라서 **부분 편집 초안 개선은 채택하되 전체 변환 성공이나 production 완료로 승인하지 않는다.** 다음 일반화 검증은 노출된 개발 그림의 cutoff 조정이 아니라, 새로운 독립 이미지에서 계약을 동결하고 실제 PPT/원본을 비교해야 한다. Phase16 동결 holdout과 실제 사람 편집시간 보정은 변경하거나 자동 테스트로 대체하지 않았다.
