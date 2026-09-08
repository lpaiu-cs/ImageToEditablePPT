# R22 native 외형 쌍 데이터 감사

2026-09-09. 동결 R19 source PPT 384개에서 외형만 바꾼 쌍을 생성했다. 기존 R19 파일은 수정하지 않았다. 실제 PowerPoint COM 960×600 렌더와 RGB 변환을 완료했고 데이터 READY로 고정한다. 모델 학습·추론은 이 작업에 포함하지 않는다.

## 경로와 계약

- 생성기: `tools/r22_native_style_data.py`
- 데이터: `artifacts/r22-native-style-data-v1/dataset_manifest.json`
- 원본: `artifacts/r19-instance-source-data-v1/dataset_manifest.json`
- 상세 변경: 각 record의 `style_changes`; 원본 연결은 `original_id`, 원본 PPT/RGB 경로와 SHA로 보존한다.

train288/calibration48/eval48 및 여섯 family별 train48/calibration8/eval8을 유지한다. `objects`와 `elements` 전체를 원본과 동일하게 보존했다. 따라서 이 두 필드 안의 외형 값은 원본 값이며 **실제 새 외형은 `style_changes`가 덮어쓰는 값**이다. kind/bbox/role/parent 관계/객체 ID·순서/배치/어휘는 동일하다. 배경과 장식은 구조 GT로 승격하지 않는다. 기존에 노출된 R19 geometry의 쌍이므로 독립 평가가 아니다.

seed2201과 원본 record ID의 SHA256 첫 8바이트로 record별 RNG를 만든다. 종류를 조건으로 외형을 선택하지 않는다. 기존 폰트/Arial/Calibri, 원본 크기 1.0~1.5배, 굵기, 단색·native gradient, 0.25/0.5/1/2/3/4pt 외곽선, 채워진 구조의 작은 native shadow를 적용했다. noFill 구조에는 채움·그림자를 추가하지 않았다. 배경은 원본 색 근처의 native gradient를 일부 적용했다.

## 실행 검증

생성 단계와 finalize에서 384쌍의 XML xfrm/preset/객체 ID/이름/텍스트가 동일함을 assertion으로 확인했다. 원본 noFill 보존 검사, 원본 manifest/PPT/RGB SHA 재검사, 모든 objects/elements 및 split/stage/family/layout/node/container 수 동일 검사도 통과했다.

실제 저장된 PPT를 재개방한 `check_style.py` 검사는 폰트 7,260 runs, 선 6,377개, shape gradient 1,282개, 배경 gradient 236개, shadow 748개의 기록값 일치를 확인했다. 채움 선택은 기존 유지 1,248 / 새 단색 1,296 / gradient 1,282개다. 검사 스크립트와 결과는 해당 artifact의 `check_style.py`, `style-audit.json`에 보관했다.

train 대표 6개를 먼저 COM 렌더해 직접 확인한 뒤 전체 384개를 렌더했다. 확대 텍스트의 일부 경계 넘침, 약한 테두리, 그라데이션과 그림자가 보이며 native 도형의 위치·종류는 유지된다. 평가 그림은 육안 확인하지 않았다. `train-pair-<family>.png` 여섯 비교판도 생성했다. 모든 RGB가 960×600이고 픽셀 보존 변환 및 384개 SHA 중복 없음 검사를 통과했다.

처음 전체 렌더는 Windows PowerShell에서 `Get-FileHash`를 찾지 못해 첫 PNG 뒤 중단됐다. 해당 출력은 `renders-failed-windows-powershell`에 보존하고 pwsh로 새 `renders`에 전체 재실행했다. 완료 후 POWERPNT 프로세스 0개를 확인하고 COM 사용권을 반환했다.

## 동결 SHA256

| 대상 | SHA256 |
|---|---|
| 원본 R19 manifest | `23b9dabaa5d584d31552b15116e9887b309b844fef86c710bad78dee77471cb2` |
| R22 dataset manifest | `f11be0d5c8f1573fd3a7d293a5fa4a4a1c6c5dfbcb7298b96b2280e788914c9b` |
| 생성기 | `394ea8e76f43ba85dd2162aa9e7e657151cb686a7813842f3e18e58aa29a5cb6` |
| preregister | `0dd7682cb7c9ce6e6a00bdf2890c237f95a52d896da24cc528d86bc33740e22e` |
| COM receipt | `0ded41a3872c1d882a0c4c3a6ad078cae5845ad88b7eefe033885dad4267e5dc` |
| source records | `bedf5e2c2ffed87d2f5a0a4749d0e770fb6b383a737cb4f30d4ff7dae3d82ee6` |
| 실제 스타일 검사 스크립트 | `693cf603d320dba28b9a1662c51baa22c689845a09d627626426620ea02033b6` |

## 재실행

새 출력 디렉터리를 지정해 `build --source <R19 manifest> --out <새 경로>`를 실행하고, `render_pptx_via_powerpoint.ps1 -InputPath <새 경로>/pptx -OutputDirectory <새 경로>/renders -Width 960`으로 렌더한다. 이어서 `finalize --out <새 경로>`, `qa --out <새 경로>`를 실행한다. 기존 출력 디렉터리는 덮어쓰지 않는다.

외형 묶음의 효과를 확인하는 데이터이며 개별 효과의 인과 분리는 불가능하다. 글자 크기로 가려짐과 넘침이 달라져도 텍스트 상자의 xfrm은 유지된다. 최종 변환 출력에 장식을 복사한다는 뜻이 아니며, 사람의 실제 편집 시간이나 제품 승인을 검증하지 않는다.
