# R11 v3: 라벨 출력과 texture 글자 관측의 분리

v1/v2는 그대로 보존한다. 새 `all_text_regions`는 출력 라벨·shape/edge 승인 정책을 바꾸지 않는다. texture 관측에 쓰는 mask만 확장한다.

추가 mask는 (a) 기존 원본 spatial OCR3배율에서 동일 문자열/confidence≥.98/bbox IoU≥.8을 모두 만족한 word, (b) source_rows.bands에서 stable_source_row이고3관측 모두 동일문자/confidence≥.98인 실제 행이다. prefix 뒤라도 실제로 관측된 글자는 사진 texture로 세지 않는다. confidence를 낮추거나 문자 추정/사전/정답 annotation으로 고치지 않는다. 원래 crop의 자식 제외 mask는 OCR 관측 이전에 적용되어 있으며, 자식 사진 전체를 texture에서 제외하지 않는다.

새 목록은 `additional_text_regions`로 전부 기록한다. 기존 출력 prefix·문자 공백·세로 방향·caption의 내용은 바꾸지 않는다. 기존신뢰텍스트영역에 새고신뢰word/행을 더한 mask로 legacy/color 및 spatial 판정을 동일하게 수행한다. palette_guard=True와 함께 별도 arm으로 평가하며 threshold는 그대로다. cached OCR 진단과 RGB부터 fresh native 실행을 구별한다. 실제사진12개 및 복잡7개 회귀 후 채택 여부를 판단한다.
