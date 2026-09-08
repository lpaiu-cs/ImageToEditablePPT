# R11 v3: 라벨 출력과 texture 글자 관측의 분리

v1/v2는 그대로 보존한다. 새 `all_text_regions`는 출력 라벨·shape/edge 승인 정책을 바꾸지 않는다. texture 관측에 쓰는 mask만 확장한다.

추가 mask는 (a) 기존 원본 spatial OCR3배율에서 동일 문자열/confidence≥.98이고 **기준 arm0와 나머지 각 arm의 bbox IoU≥.8**인 word 관측창, (b) source_rows.bands에서 stable_source_row이고3관측 모두 동일문자/confidence≥.98인 행 관측창이다. arm1↔arm2의 별도 IoU까지 검증하는 계약은 아니다. prefix 뒤의 이러한 OCR 관측창은 texture 분석에서만 제외한다. confidence를 낮추거나 문자 추정/사전/정답 annotation으로 고치지 않는다. 원래 crop의 자식 제외 mask는 OCR 관측 이전에 적용되어 있으며, 자식 사진 전체를 texture에서 제외하지 않는다.

새 목록은 `additional_text_regions`로 전부 기록한다. 기존 출력 prefix·문자 공백·세로 방향·caption의 내용은 바꾸지 않는다. 기존신뢰텍스트영역에 새고신뢰word/행을 더한 mask로 legacy/color 및 spatial 판정을 동일하게 수행한다. palette_guard=True와 함께 별도 arm으로 평가하며 threshold는 그대로다. cached OCR 진단과 RGB부터 fresh native 실행을 구별한다. 실제사진12개 및 복잡7개 회귀 후 채택 여부를 판단한다.

높은 OCR confidence와 반복 일치는 실제 문자의 정확성이나 semantic text 분류를 증명하지 않는다. 예를 들어 원본의 `modele` 관측은 전체 행 인식과 다를 수 있다. 이 추가 관측을 라벨 정답이나 native 텍스트 추가로 승격하지 않는다. mask 추가가 tile 관측 분모도 줄일 수 있는 한계를 포함한다. 이 문구는 구현의 기준-arm 대응 범위를 명확히 한 것으로 실행 cutoff/기존 결과를 변경하지 않는다.
