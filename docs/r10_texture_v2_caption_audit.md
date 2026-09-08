# Texture v2 실제 OCR caption 재검사

root 새 소스를 별도 snapshot으로 고정하고 기존 `photo_icon-s1-aa4.png`에 실제 RapidOCR를 다시 실행했다. 원본 RGB와 v1 결과는 변경하지 않았다.

- texture SHA: `19f720480043b0dbdf9f5ad7c95fd2ea19e1facdf58b0bb03c76fadce7e68a7e`
- proposal SHA: `7a57db108ddedbcf44052a13ff08e27d5c84c0d0431717ebfe07df1e7fd6d7d1`
- owner SHA: `7a375d4f54f8503de66b569fb1e60beea584427e43956f17b88a742938a96caa`
- RGB SHA: `1f5852a7e633cf7fe6c7ae98e4e4d94855c7357c4936fda2c467980b03d71d6f`
- artifact: `artifacts/r10-texture-v2-caption-results/results.json` 및 세 source snapshot

후보 bbox `[91,126,299,269]`에서 실제 OCR는 `PHOTOID`를 승인했다. 그 accepted word audit을 새 guard에 전달했다.

| 검사 | textured fraction | observed pixels | 판정 |
|---|---:|---:|---|
| 단어 제외 없음 | .831461 | 27602 | veto |
| 실제 accepted 단어만 제외 | .896338 | 24821 | veto |

단어 제외 없는 값은 기존 v1 관측과 같다. 단어 제외 후에도 사진 자식의 textured tile은 남고, 캡션 쪽 측정 면적이 줄면서 fraction은 증가한다. 따라서 **이 실제 OCR caption 반례의 veto는 유지된다.** 자식 전체를 지워 caption frame를 통과시키던 이전 content gate 실패가 이 사례에서 재발하지 않았다.

원본 RGB 불변성을 확인했다. root 코드와 threshold는 변경하지 않았다. 이 bounded 실행은 caption 한 개에 한정되며, 큰 AA 텍스트의 과잉 veto가 해결됐는지 또는 전체 실이미지 결과가 개선됐는지는 검증하지 않았다.
