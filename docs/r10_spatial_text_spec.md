# R10-T: 공간 위치를 구분하는 OCR 텍스트 복원

## 문제와 범위

O+C+S는 실제 15개에서 중복 글자와 트리 연결을 개선했지만 label은82정답/1오답/8공백 그대로다. 작은 label-anchor 주변의 선을 OCR이 별도 저신뢰 snippet으로 잡으면 기존 `ordered_text`가 crop 전체를 기권한다. 공백4개와 `CP.` 오류를 정답으로 채우지 않고, 원본에서 단어 위치와 주변 선 위치를 구분한다. BOX 안의 graph 라벨 공백4개도 동일한 이미지 관측으로 조사한다.

## 실험 계약

- 기존 node ID, bbox, kind, 연결을 변경하지 않고 label만 바꾸는 별도 arm이다. 입력은 원본 RGB와 기존 예측 bbox뿐이다. annotation/정답 PPT/정답 문자열은 추론에서 금지한다.
- bbox+2pixel RGB crop, median border16, bicubic3/4.5의 고정 두 배율에서 detection+recognition을 새로 수행한다.
- 두 배율에서 bbox 내부에 위치한 단일 단어가 confidence>=.95, 같은 문자열, spatial envelope IoU>=.8이어야 한다. 회전된 단어/여러 단어/경쟁하는 공간 관측은 이 초기 경로에서 기권한다.
- 단어 polygon이 owner bbox 안에 대부분(>=.90) 들어가고 center가 안에 있어야 한다. 다른 owner 안의 단어를 가져오지 않는다. confidence만으로 owner 밖의 문자열을 사용하지 않는다.
- 추가 snippet은 단어와 겹치거나 owner 안에서 별도 글자일 가능성이 있으면 기권한다. 원본에서 관측된 긴 선임을 확인한 경우에만 제외한다. 근거 없는 글자 제거/철자 교정/사전 보정은 금지한다.
- 통과하면 해당 단어만 label에 반영한다. 불일치/기권이면 기존 label은 보존하고 audit에 남긴다. 이 보존은 기존 label이 정답임을 의미하지 않는다.
- S의 연결 변경과 섞어 성공을 세지 않는다. 기존 arm을 그대로 보존하고 T를 켠 별도 실제15 출력→native render→별도 GT 평가→전체 육안 확인으로 label 변화와 관계 불변을 함께 검증한다.

기본 단위 대조는 위치 밖, 복수 단어, 저신뢰 경쟁, 배율/문자 불일치, 회전, 원본 선 snippet을 포함한다. 실제 OCR clean/가까운 동일 단어/작은 라벨 및 선이 있는 RGB 대조를 추가한다. 이미 본 합성15 개선과 새로운 일반화/사람 편집시간 승인은 구분한다.
