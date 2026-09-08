# R11 공간 텍스처 첫 진단: 채택 보류

현재 CLI의 실제 사진 caption12개 중9개 오출력을 독립 작업이 확인했다. 처음3개 china color는 거부됐지만 china gray3/flower color3/flower gray3는 모두 native 박스+라벨1개를 남겼다. 일반 사진 안전성은 충족하지 않는다.

사전 고정한 R11 공간 roughness 첫 arm을 RGB-derived OCR 캐시와 원본 RGB로 진단했다. **이는 texture만의 재관측이며 fresh native 실행이 아니다.** caption의기존9오출력은 모두 거부될 것으로 나왔으나, 정상 복잡7개 기존99owner 중20개도 거부됐다. 분포는 blue2/dark2/nested8/original6/reasoning2다. 이 과잉 기권 때문에 CLI에 넣지 않았다.

자료: `artifacts/region-image-only-r11/spatial-caption-diagnostic-v1/results.json`, `spatial-complex-diagnostic-v1/results.json`. 사진의 공간변화만 보지 않고 글자/선 안티앨리어싱까지 많은 회색 level로 세는 문제가 남는다. 이 첫 arm의 cutoff는 수정하지 않는다. 다음 별도 arm에서는 실제 픽셀의 두 주색 집중도가 높은 잉크/배경 tile을 공간 dense 판정에서 분리하는 관측 모델을 사전 고정한다.
