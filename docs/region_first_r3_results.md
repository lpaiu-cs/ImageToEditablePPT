# R3-T: 원본 경로 15/15, 기존 PPT 출력은 여전히 부족

2026-09-08. 캠페인 중간 동결. 선 추적 결과를 먼저 기록하고 바로 emitter-only 단계로 이어간다.
계획 95accb6, 실행 ac7e584 (clean), 입력 SHA는 별도 R3 manifest에 고정했다.

| 조건 | 올바른 방향 관계 /15 | 오답 또는 unresolved 관계 |
|---|---:|---:|
| 기존 선택 결과 | 9 | 4 |
| 엄격한 node masking + trace | 12 | 3 |
| 공유 경계 face를 투명하게 취급 + trace | **15** | **0** |
| R0 수동 박스 + 같은 trace | 12 | 0 |

선택 조건의 객체 23개 일치와 추가 객체 3개는 바꾸지 않았다. 투명한 gap owner 두 개는
endpoint/occlusion에서만 제외했고 PPT 객체로는 남겼다. 따라서 객체 검출 개선이라고 세지 않는다.
기존 맞은 BLIP/HEVC/Reasoning 각 3개 관계를 유지하면서 Attention 4개, PERCEIVE 2개를 회복했다.

![Attention source 경로](../artifacts/region-first-r3/run1/mixed-attention--transparent_gap_trace-paths.png)
![PERCEIVE source 경로](../artifacts/region-first-r3/run1/cogbot-perceive--transparent_gap_trace-paths.png)

위 두 그림을 직접 열어 실제 선을 따라갔는지 확인했다. 모폴로지 복구 길이는 사전 고정된
작은 범위이고, 장거리 endpoint 사이를 임의 직선으로 잇지 않았다. 그래도 이 결과는 이미
반복 사용한 여섯 개발 표본이다. 분기/교차로 세 owner 이상이 붙는 component는 모호해서 생략하며,
유색 선·긴 가림·불정확한 bbox 등에 대한 일반 성능은 확인하지 않았다.

수동 박스 Attention은 red→attention 하나만 얻었다. 나머지는 두 owner contact를 확보하지
못했다. 수동 경계는 픽셀 정답이 아니라 근사이고 mask/tolerance에 민감하므로 strict upper
bound로 취급하면 안 된다. 이 라운드에서 박스를 고치거나 tolerance를 조정하지 않았다.

24개 PPTX를 PowerPoint 16에서 렌더하고 여섯 비교 그림을 직접 확인했다.
PERCEIVE의 꺾인 source path는 기존 writer에서 대각선 chord가 되고, Attention은 여러
화살표가 중앙에 겹친다. **15/15 관계를 맞혔다고 시각적/편집성 승인을 줄 수 없다.**

![native output 한계](../artifacts/region-first-r3/review-v2/cogbot-perceive-trace.png)

남은 shape/label/owner binding 및 source/scene/PPTX/PNG/mask SHA를 감사했다.
합성 trace 테스트 5개 통과(빈 입력, 선/화살표, 꺾인 경로, 3-owner 모호성, container crossing).
최종 회귀 수는 캠페인 종료 보고에 기록한다. R0/R1/R2/Phase15/16 및 production은 변경하지 않았다.

다음은 이 라운드의 transparent_gap_trace scene 여섯 개를 SHA 고정해 native path emission을
시험한다. 인식/경로를 다시 계산하지 않는다. [계획](region_first_r3_plan.md),
[입력](../benchmarks/region_first_r3_inputs_v1.json), [evidence](../benchmarks/region_first_r3_evidence_v1.json).
