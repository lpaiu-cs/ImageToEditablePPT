# Content gate 독립 감사

기존 geometry96 및 owner24 RGB를 변경 없이 실행했다. proposal/owner/gate를 별도 snapshot으로 고정했다. runtime 수정은 없다.

- artifacts: `artifacts/r10-content-gate-v1-results`
- proposal SHA: `4ba8791d63026cbf6d79f50b01c9661b2cb1f961c0a56feaf63606925d868b58`
- owner SHA: `64df060f5a3c93198fb877a35f6f7d9f47c1fcb503d7e547349bf1b5d7b07766`
- gate SHA: `f4e922f9b132f4d227f055ae1cbe8ff9803b5125c1e8afb1459ee30ebaeac068`

runner는 모든 후보에서 빈 OCR audit과 합성 annotation 단어를 accepted로 가정한 audit을 각각 적용한다. 후자는 **실제 OCR 성능 결과가 아니며** geometry/owner에는 annotation을 주입하지 않는다. 별도로 실제 RapidOCR 양성 두 개와 발견된 사진 caption 반례 한 개를 실행했다. 기존 GT/holdout은 읽지 않았다.

## 확인된 제한 효과

- 기존 `photo_frame`의 선택된 7개 후보는 모두 content reject다.
- glyph_hole의 16개 경계는 flat eligible이다. 그러나 라벨·연결이 없으면 admission에서 남지 않는 계약이다. 함수 단위 admission 통제에서 라벨 없는 고립/blank-blank 연결은 탈락, eligible labelled-blank 연결은 유지, ineligible labelled-blank 연결은 blank를 유지하지 않았다. 실제 source tracing/native emitter는 미검증이다.
- 일반 rectangle7, colored rectangle7, adjacent14 후보는 flat eligible이다. 무라벨 고립이면 최종 admission이 제거하는 의도된 보수적 손실이다.
- thin scale1 둘과 open scale2 둘의 누출 부모는 content reject여서 해당 fixture의 오염된 부모 승인을 차단한다.
- 실제 OCR `two_children-s1-aa4`, `small_child-s1-aa4`의 부모는 `PARENTHEADER`만 승인했고 자식 단어 혼입은 없다. content fraction0으로 eligible이다. 원본 `PARENT HEADER`의 공백은 손실되어 문자열 완전 복원이라고 하지 않는다.

## 실제 OCR로 확인한 사진 caption 프레임 반례

`photo_icon-s1-aa4.png`에서 사진 frame 후보 bbox는 `[91,126,299,269]`다. owner exclusion은 texture의 raw child `[94,154,296,266]`를 제외한다. 남은 분홍 caption 영역에 대해 실제 OCR의 세 scale이 모두 `PHOTOID`를 승인한다(confidence .99709/.99627/.99303). content gate는 미설명 비율0, 관측2898px, median `[240,170,180]`, eligible=True를 반환한다.

따라서 이 후보는 **eligible + 실제 승인 라벨**로 admission에 남는 조건을 만족한다. 사진 frame의 의미적 부적격성이 제거된 것은 아니다. 문제는 사진 texture가 자식으로 제외된 뒤 남은 caption 영역만 flat 여부를 검사한다는 점이다. 이는 합성 정답 OCR을 강제 입력한 결과가 아니다. 상세 실제 관측은 `photo-caption-real-ocr.json`에 보존했다. 전체 파이프라인/PPT 최종 출력까지 실행한 증거는 아니다.

같은 photo_icon scale2/AA4도 합성 OCR 조건에서는 caption frame가 eligible이다. 이 두 번째 사례는 실제 OCR을 실행하지 않았으므로 조건부 관측으로만 남긴다. 실제 사진 대신 seeded texture를 쓴 fixture의 범위도 유지한다.

이 gate는 일부 노이즈/무라벨 고립 경계를 줄이지만 일반 semantic 판별을 증명하지 않는다. 기존 결과와 실패를 덮어쓰지 않았다. PPT 및 실제 사용자의 편집 시간은 평가하지 않았다.
