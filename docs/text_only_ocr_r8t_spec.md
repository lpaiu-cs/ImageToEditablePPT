# R8-T: text-only OCR 단일 변경 대조

## 사전 결정

R8-P의 15장 고정 source_scene과 RGB를 그대로 사용한다. source_scene은 이미지 단독
예측 및 기존 추적/OCR 산출물이며 정답이 아니다. 원본 PPT·annotation·offline target은
이번 변환에서 사용하지 않는다. bbox/역할/도형/연결/방향/기존 일반 node 문자열은 고정한다.
이번 변경은 `label_anchor`의 OCR 입력 crop 하나뿐이다. native attachment 지원 변경과
합치지 않는다. 기존 writer의 text-only 연결 기권과 4px fitting 기준을 유지한다.

고정 OCR 설정:

- 예측 bbox를 floor/ceil로 감싼 뒤 원본 픽셀에서 각 방향 2px 확장하고 이미지 범위로 자른다.
  텍스트뿐인 객체에 닫힌 상자용 내부 3px 축소를 적용하지 않는다.
- 실제 crop의 대표 RGB 중앙값으로 16px 외곽을 채우고 bicubic 3배 확대한 입력을 만든다.
  이 패딩은 OCR 전처리일 뿐 PPT 출력이나 도형 채움에 사용하지 않는다.
- 기존 OCR confidence .90 및 두 scale(변환 crop의 1배/1.5배) 일치 규칙을 그대로 쓴다.
  원본 기준으로 3배/4.5배다. 사전 문자열/GT/언어적 교정/실패별 재시도는 사용하지 않는다.
- crop 한 변 2px 미만 또는 40,000px 초과는 기권한다.

전체 15장을 다시 쓰되 OCR 변경 대상은 기존 예측 text-only 객체 28개다. 일반 node는
기존 인식 결과를 복사하므로 이번 단계의 결과를 새 end-to-end 추론으로 부르지 않는다.
각 worker는 source RGB와 자기 출력 경로에 복사된 예측 scene만 읽도록 Python open
allowlist를 설치한다. GT 평가와 실제 PPT 렌더는 별도 단계다.

판정은 일치 node의 문자 정답/오답/공백, 불일치 객체의 문자열 및 중복, 실제 PPT에서
보이는 라벨·연결 상태로 한다. 채택 여부는 결과 후 별도 보고하며 입력이나 규칙을
사후 바꿔 이 실행을 구제하지 않는다. legacy 검출/validation 노출 한계는 R8-P와 같다.
