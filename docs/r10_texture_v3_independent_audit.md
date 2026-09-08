# Texture v3 / owner badge 회귀 감사

root 코드를 수정하지 않고 새 source를 snapshot으로 고정했다.

- texture SHA: `81926fafc9cd0c78a3faa289a2f1c9ac2f9cc1049eea3d82e240a459052dea3b`
- owner SHA: `4ff32d8be0a415a12de1d6ab29b81f1763bf8a14a66cf1994453b6714e8ccf00`
- proposal SHA: `7a57db108ddedbcf44052a13ff08e27d5c84c0d0431717ebfe07df1e7fd6d7d1`
- artifacts: `artifacts/r10-texture-v3-results`, `artifacts/r10-owner-region-badge-v1-results`

기존 사진 caption fixture에 실제 OCR를 다시 실행해 `PHOTOID`가 승인됨을 확인했다. 해당 accepted word를 제외해도 texture fraction .848475로 veto가 유지된다. 사진 자식은 원본 검사에 남는다. `caption-real-ocr.json`에 실제 audit을 저장했다.

기존 단색/회색 gradient/2D RGB gradient/Arial·Times text10개는 모두 fraction0으로 non-veto다. 추가로 1000×600 캔버스, Arial32/48px, AA4 downsample의 밀집 회색조 텍스트 두 개도 fraction0이다. 원본 PNG SHA와 결과는 `dense-gray-results.json`에 기록했다. 이 추가 두 개는 사전 잠금 suite의 통과율에 합치지 않는 탐색 진단이다.

**정확한 회색조는 quantize8 후 최대32색이므로 기존48색 gate도 만족할 수 없다.** 따라서 회색조 글자의 non-veto를 새 covariance 조건의 개선 증거라고 하지 않는다. 회색조 사진의 사각지대도 계속 남는다. 실제 큰 유색 AA 글자 과잉 veto 해결은 이번 검사로 입증하지 않았다.

새 small chromatic badge exclusion을 포함한 owner snapshot에 기존24 fixture를 재실행했다. 부모 제목24개의 제외율은 모두0이다. 기존 결과와 동일하게 thin scale1 둘은 자식 누출이 남고, open scale2 둘은 누출과 pink 채움이 남는다. 나머지20개는 자식 영역 제외와 부모색이 정상이다. **기존 suite에서 회귀를 관측하지 않았다는 결과**이며 새 badge 전용 양성 효능을 검증한 것은 아니다.

기존 결과를 보존했고 입력 RGB 불변성을 확인했다. threshold 변경, native PPT 평가, semantic 승인 주장은 없다.
