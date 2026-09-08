# R14 외부 흐름·내부 생략 입력 대조11건

## 고정 계약

연결형 사진·아이콘 카드는 내부 그림과 글자를 출력하지 않고 외부 폐테두리와 승인된 연결만 남기는 사용자 승인 정책을 검사한다. 단독·단방향·양쪽 incoming·양쪽 outgoing·같은 접점의 반대 복제·texture 실패 카드 연쇄·무방향 선은 해당 카드가 기권해야 한다. 음성 판정은 카드에 적용하며 정상 Read/Check seed까지 지워야 한다는 뜻이 아니다.

생성기는 `tools/r14_flow_frame_controls.py`이며 기존 `r10_classifier_pilot`의 deck/rect/label을 재사용했다. 사진은 기존 번들 china/flower만 사용하고 출처 README를 보존했다. 회색 꽃은 같은 자산의 파생이고 단순 인물 아이콘은 프로그램으로 생성한 raster 대조다. seed는 연한 파랑 native 사각형과 Read/Check label, 카드에는 Photo 또는 Input caption이 있다.

| 구분 | 장면 |
|---|---|
| 외부 테두리 허용 목표4 | china-flow, flower-flow, gray-flow, icon-flow |
| 카드 기권 목표7 | standalone, one-way, both-in, both-out, same-port, failed-chain, no-arrows |

모든 역할·bbox·방향·물리 좌표·내부 생략 기대값은 PPT 생성 및 COM 렌더 전에 preregister에 기록했다. train/eval 분할은 없으며 모두 노출된 개발 대조다. source PPT 객체 metadata와 정답 역할은 evaluator 전용이고 추론에는 RGB만 전달한다. 같은 접점 복제는 두 PPT connector가 같은 선분을 반대로 겹쳐 그리는 경우다. card 연쇄는 Read→사진1→사진2→Check로, 구제한 테두리를 다음 seed로 삼지 않는 조건을 검사한다.

**정책 목표와 관측 gate를 구분한다.** 실제 폐윤곽/OCR/화살촉/texture 승인 여부는 아직 실행하지 않았으며 각각 측정해야 한다. 특히 단색 인물 아이콘이 texture veto되는지는 가정하지 않는다. 내부 아이콘을 native 구조로 오인하거나 일반 경로에서 caption을 출력하면 별도 실패로 기록하며 fixture/threshold를 결과에 맞춰 바꾸지 않는다.

## 입력 준비와 증거

- artifact: `artifacts/r14-flow-frame-controls-v1`
- preregister SHA256: `6de8eaad5ff660c832d46b5e0f6d73ad60131eebe6efdcbbb8779f73fde4bc0f`
- source COM manifest SHA256: `79533a1bbaa891ff62657e65920758e4a801dabf930bb325499637a1a607fccc`
- RGB manifest SHA256: `56a8e3bea91e6e7c6b46b9fe47a6bdca8c272f2c704d549f95ecfa46c168949e`

PPT11개 source XML의 picture/connector/arrowhead 개수를 사전 metadata와 대조하는 assertion을 통과했다. source-receipts.json에 실제 객체 ID/name, 방향 좌표, PPT 해시를 보존했다. 기존 POWERPNT 프로세스가 없음을 확인한 뒤 실제 COM으로800×450 렌더했다. PPT/PNG receipt 해시를 모두 검증하고 RGB로 무손실 정규화하여 decoded pixel 동일성을 확인했다. 원본과 파생 파일을 덮어쓰지 않았다.

contact-sheet.png에서11장 전체를 직접 확인했다. 정상 흐름4개, 양쪽 화살표 방향, 같은 접점 양방향 중복, 카드2개 연쇄, 방향 없는 선이 시각적으로 구분된다. COM은 source 렌더 완료 직후 root에 반환했다. 이 기록은 **입력 준비 증거**이며 R14 추론 성공이나 최종 출력 증거가 아니다. 새 holdout·다운로드·훈련은 수행하지 않았다.
