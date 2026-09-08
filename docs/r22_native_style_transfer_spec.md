# R22 native 외형 다양화 대조 설계

2026-09-09. R21 전체 검출의 해상도 증가는 원본 복원을 개선하지 못했다. R19에서 native 합성 eval의 종류 TP316/318과 원본 주요 노드 TP1/17의 큰 간극이 남았다. 다음 가설은 **학습 외형의 좁은 범위가 원본의 굵은 텍스트, 약한 테두리, 음영·그라데이션 등에 대한 일반화를 제한한다**는 것이다. 단일 원인의 증명이 아니라 묶음 외형 다양화의 유효성 검증이다.

## 데이터 계약

R19 source PPT 384개를 직접 읽어 외형 쌍을 만든다. source bbox, preset kind, object role, parent/child 관계, 배치, 어휘는 모두 원본과 같아야 한다. train288/calibration48/eval48 구분을 유지하며 새 데이터라고 독립성을 주장하지 않는다. 기존 eval은 이미 노출된 개발 평가다. CogBot RGB와 수동 장부는 생성·학습 입력으로 쓰지 않는다.

새 source PPT에는 종류와 독립적인 고정 RNG(seed2201, record ID 안정 해시)를 사용해 다음을 섞는다. Arial/Calibri 계열의 굵은 글씨와 기존 글씨, 크기 1.0~1.5배, 밝고 어두운 채움, 기존 단색과 native gradient, 약한 외곽선과 1~4pt 선, 채워진 구조의 작은 native shadow, 배경의 은은한 native gradient. noFill 부모/열린 구조에 임의 채움을 주지 않는다. glyph는 여전히 decoration이며 구조 GT로 바꾸지 않는다. 모든 변화 값을 source 기록에 남긴다. 글자 크기로 경계 일부가 가려질 수 있으나 shape xfrm은 변하지 않는다.

원본 source 쌍과 새 PPT의 XML xfrm/kind/role/객체 수를 감사한다. 실제 PowerPoint COM960×600으로 렌더한 RGB만 학습한다. train 대표 6장을 육안 확인한 뒤 데이터 READY를 고정한다. 모든 source/RGB/manifest SHA를 기록하고 기존 artifact를 덮어쓰지 않는다. 평가 이미지를 보고 외형을 조정하지 않는다.

## 학습 및 평가

R19 모델 구조와 ImageNet backbone 초기화, seed1901, AdamW, batch4, 1800 steps, learning rate .0003→1200 step 이후 .0001을 유지한다. R19의 성공한 600-step control을 재사용한다. R19 train geometry 288개를 같은 RNG로 뽑고, 별도 RNG로 각 샘플의 원본/외형 쌍을 50% 선택한다. 따라서 geometry sampling을 그대로 두고 외형 노출만 바꾼다. 사전 지정한 1800-step final만 사용한다. 100/600/1200/1800 train 대표의 시각 스냅샷을 남기며 데이터/epoch/threshold를 중간 결과에 맞춰 바꾸지 않는다.

동결 R19와 새 모델 양쪽에 동일한 plain/style 쌍을 평가한다. calibration은 plain48+style48에서 .3/.5/.7/.85/.95/.99 중 precision1 및 TP>0을 만족하는 최대 recall(동률 높은 threshold)을 선택한다. 없으면 .95 fallback과 gate=false를 명시한다. calibration 저장 후 eval48+48을 열고 TP/FP/FN, 후보 geometry, 부모/자식, hard-negative FP를 쌍별 보고한다. 원래 R19 결과를 덮지 않는다. 새 calibration 선택의 영향과 학습 효과를 혼동하지 않도록 .95 고정 지표도 함께 저장한다.

마지막으로 원본 CogBot을 RGB-only로 추론하고 native PPT를 실제 COM으로 확인한다. manual17 장부는 예측 이후 진단용이다. 이 한 그림과 노출된 합성 eval 개선만으로 제품 승인하지 않는다. 외형 다양화가 실제로 도움을 주면 새로운 seed/layout의 미개봉 데이터로 별도 독립 검증한다. 효과가 없으면 같은 가설을 끝없이 확대하지 않고 학습된 후보의 실제 경계 근거와 잘못된 종류 판정을 다음 대상으로 좁힌다.

변환 출력은 native editable preset/noFill이며 음영·장식을 출력으로 복사하지 않는다. 이 단계는 닫힌 구조만 연구한다. 연결선/텍스트 통합과 실제 사람의 편집 시간은 여전히 별도의 제품 완료 조건이다.
