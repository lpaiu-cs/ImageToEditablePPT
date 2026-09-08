# Source-row OCR 독립 진단

root runtime을 변경하지 않고 `source_text_rows.py`를 snapshot으로 고정했다. fixture를 생성·SHA 고정한 후 실제 RapidOCR로 실행했다. 기존 GT/holdout은 읽지 않았다. `.98` default를 유지하고 `.90/.95`는 저장된 세 관측에 대한 사후 진단으로만 계산했다. threshold 변경 승인이 아니다.

- source SHA: `7af9b631cef4ac1d0de9c9f9084cbf604825bbf81f7d0e6e9ca2aa06dae687c2`
- fixture manifest SHA: `7f1af9699c715fb47f2e419457e6fbe02262f939e97a05284a1412cced72f3c5`
- fixture lock SHA: `ed2aa2ee6038eacd0027de64802de463c67178aea9594304e1dbc7fe88362e9f`
- builder/runner SHA: `32e9292ec6e9e17089767a308d6bd043ca1a5aebc3e6f73107d697a2270be119`
- artifacts: `artifacts/r10-source-rows-v1-fixtures`, `artifacts/r10-source-rows-v1-results`

Arial/Times New Roman/Consolas, 20px 원본/12px 작은 글자/blur1.1/끝 글자 일부 제거의 네 조건이다. 문자열은 `Section 3.4`, `Model of Code`, `x=1+2`, `0O1Il`, `Compact and Green`이다. 총 72 entry는 완전한 양성45, 선·사각형 비텍스트12, 잘린 글자 진단15로 나눈다. 비텍스트 entry는 폰트 축에서 중복 RGB를 포함하므로 12개의 서로 다른 음성이라고 하지 않는다. owner mask는 fixture의 지정 영역이며 proposal/owner 검출을 함께 평가한 것이 아니다.

| 최저 confidence 진단 | 완전 양성 승인 /45 | 정확 문자열 | 공백만 손실 | 문자 오류 | 비텍스트 승인 /12 | 잘림 진단 승인 /15 |
|---|---:|---:|---:|---:|---:|---:|
| .98 기본 | 7 | 4 | 3 | 0 | 0 | 1 |
| .95 | 22 | 17 | 4 | 1 | 0 | 6 |
| .90 | 27 | 22 | 4 | 1 | 0 | 9 |

완전 양성의 세 관측이 일치한 경우, 최저 confidence 분포는 다음과 같다. 서로 다른 오류 종류가 confidence만으로 깔끔히 분리되지 않는다.

| 분류 | 수 | 최소 | 중앙값 | 최대 |
|---|---:|---:|---:|---:|
| 정확 문자열 | 22 | .91735 | .96264 | .99367 |
| 공백만 손실 | 4 | .96662 | .99516 | .99670 |
| 문자 오류 | 4 | .79675 | .88665 | .95724 |

확인된 동일 오답은 `consola-t2-normal`: 원문 `x=1+2`를 세 관측 모두 `X=1+2`로 출력한다(.962875/.957241/.962396). `.95` 진단에서 승인되며 수식의 대소문자 차이를 무시해서는 안 된다. `0O1Il` 혼동도 세 관측이 같을 수 있으나 이 fixture에서는 .90 아래여서 차단된다.

`.98`의 완전 양성 승인 오류 세 건은 Arial blur의 `Section3.4`, `ModelofCode`와 Times blur의 `Section3.4`다. 모두 공백 손실이다. 이를 정확 문자열로 정규화해서 세지 않았다. 이 fixture에서는 승인된 Section 숫자가 바뀐 사례는 없다.

`arial-t4-clipped`는 `Compact and Greer`를 세 관측 모두 출력하고 최저 .9803927로 기본 gate를 통과한다. 마지막 글자의 오른쪽을 지운 이미지이므로 원래 전체 문자열을 엄격한 정답으로 강제하지 않는다. 다만 높은 confidence와 세 관측 일치가 불완전 글자의 보수적 생략을 보장하지 않는 진단이다.

비텍스트 blur는 세 관측 모두 `一口`를 내기도 하지만 confidence .52~.57로 모든 진단 threshold에서 차단된다. 따라서 세 관측 동일 문자열만으로 텍스트 존재 자체를 증명할 수 없다.

모든 RGB 불변성을 확인했고, 저장된 관측으로 재구성한 .98 prefix는 실제 함수 출력과 일치했다. 이 감사는 독립 합성 줄 이미지의 분포이며 실사용 OCR 오류율이나 confidence calibration을 대표하지 않는다. threshold를 낮추거나 문자열을 정답에 맞춰 보정하지 않았다.
