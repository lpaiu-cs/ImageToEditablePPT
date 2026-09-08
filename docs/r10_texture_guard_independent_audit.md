# Source texture veto 독립 감사

기존 geometry96/owner24와 추가 RGB10을 실행했다. root runtime은 변경하지 않았다. proposal은 고정 snapshot의 `inner_boundaries=True`이며 union geometry 검증이 아니다. 새10개는 fixture가 지정한 실제 사각형 contour로 guard 자체만 검사했다.

- texture SHA: `59e2de1d90fdbc2adf5d9a4a681485eb7794042666bbab5a38b90dab51cd8a94`
- proposal SHA: `7a57db108ddedbcf44052a13ff08e27d5c84c0d0431717ebfe07df1e7fd6d7d1`
- 추가 manifest SHA: `ec49ff15d57a73ad4e67d08e7a567eabc86a5a6b2202416301b65d5ebe42b47d`
- artifacts: `artifacts/r10-texture-v1-fixtures`, `artifacts/r10-texture-v1-results`

모든 RGB SHA/불변성을 확인했다. 이전 결과는 보존했다. 추가 fixture는 단색, 수평 회색 gradient, 부드러운 2D RGB gradient, Arial/Times의 5행 텍스트를 각각 scale1/2로 만들었다. gradient는 그라데이션 노이즈를 구조적 복원 대상과 혼동해 과도하게 veto하지 않는지 보는 양성 진단이다.

## 관측

- 기존 photo_frame 선택7개 모두 veto: textured fraction .985~1.
- photo_icon의 모든 사진 frame 후보 veto. 이전 caption 반례 `photo_icon-s1-aa4`는 실제 OCR를 재실행해 `PHOTOID` 승인을 재확인했지만, 원본 전체 texture fraction .831461로 veto된다. `caption-real-ocr.json`에 보존했다.
- **photo_icon의 상위 부모4개도 veto**: fraction .3889~.505. 사진을 담은 정상 구조적 부모의 부분 복원을 포기하는 보수적 손실이다. caption 차단 성공만 보고해서 이 비용을 감추지 않는다.
- 나머지 owner20 RGB의 선택 후보는 모두 non-veto다.
- 추가 단색/회색·RGB gradient/Arial·Times 텍스트10 RGB는 전부 fraction0, non-veto다. 이 작은 통제군에서 오거부가 없다는 뜻이지 모든 텍스트·gradient가 안전하다는 증명은 아니다.
- 기존 glyph hole16경계도 모두 non-veto다. 따라서 이 결과는 semantic node 승인으로 해석할 수 없다.

사진은 seeded texture를 쓰는 기존 합성 진단이며 실제 사진 분포를 대표하지 않는다. 이번 실행은 guard와 제한된 caption OCR 관측에 한정한다. native PPT, union proposal, 실제 사용자의 수정 시간은 평가하지 않았다. 실패한 content gate를 결합하거나 threshold를 바꾸지 않았다.
