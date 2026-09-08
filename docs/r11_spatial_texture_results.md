# R11 공간 텍스처 첫 진단: 채택 보류

현재 CLI의 실제 사진 caption12개 중9개 오출력을 독립 작업이 확인했다. 처음3개 china color는 거부됐지만 china gray3/flower color3/flower gray3는 모두 native 박스+라벨1개를 남겼다. 일반 사진 안전성은 충족하지 않는다.

사전 고정한 R11 공간 roughness 첫 arm을 RGB-derived OCR 캐시와 원본 RGB로 진단했다. **이는 texture만의 재관측이며 fresh native 실행이 아니다.** caption의기존9오출력은 모두 거부될 것으로 나왔으나, 정상 복잡7개 기존99owner 중20개도 거부됐다. 분포는 blue2/dark2/nested8/original6/reasoning2다. 이 과잉 기권 때문에 CLI에 넣지 않았다.

자료: `artifacts/region-image-only-r11/spatial-caption-diagnostic-v1/results.json`, `spatial-complex-diagnostic-v1/results.json`. 사진의 공간변화만 보지 않고 글자/선 안티앨리어싱까지 많은 회색 level로 세는 문제가 남는다. 이 첫 arm의 cutoff는 수정하지 않는다. 다음 별도 arm에서는 실제 픽셀의 두 주색 집중도가 높은 잉크/배경 tile을 공간 dense 판정에서 분리하는 관측 모델을 사전 고정한다.

## 별도 palette-guard v2 진단

두 주색 집중 관측을 추가한 별도 arm에서도 사진9오출력은 모두 거부된다. 정상 owner 과잉 기권은20→5로 줄었으나 blue-flow 우측 상단1개와 원본 Boundary Enforcement/녹색 ACT/SocialManager/Generation4개가 남는다. 자료는 같은 경로의 `spatial-caption-diagnostic-v2`, `spatial-complex-diagnostic-v2`다. 첫 arm을 수정해 성공으로 재분류하지 않았고, v2 역시 아직 CLI에 넣지 않았다.

남은 원인 중 하나는 '출력 가능한 완결된 라벨 prefix'만 texture mask에 쓰면서, 그 뒤에 존재하는 고신뢰 관측 글자까지 설명되지 않은 사진 내용으로 세는 결합이다. 다음 별도 관측에서는 출력 라벨 정책을 그대로 둔 채, 원본3배율에서 문자열·좌표·confidence가 모두 일치한 후행 OCR word/행을 texture 분석용으로만 분리할 계획이다. 불확실한 문자를 출력하거나 사진 자식 전체를 지우는 변경은 하지 않는다.
