# 사진 caption12 실제 CLI 독립 감사: 9/12 오출력

고정된 closed-native-v2 CLI는 사진 캡션 12건 중 9건을 각각 native box 1개와 label 1개로 잘못 출력했다. 회색 사진뿐 아니라 컬러 꽃 사진도 통과했다. 사진을 비워야 한다는 프로젝트 기준에 실패했으며, 이전 사진 8건의 빈 출력으로 일반적인 사진 차단을 주장할 수 없다.

## 고정 계약과 실행

- root commit: `89a30d0e99530213c9e7b24fd6fcb0f6c57ee729`
- 입력: `artifacts/r10-photo-caption-v1`; 준비 기록은 `docs/r10_photo_caption_controls.md`.
- preregister SHA256: `c6a3307e32d7ac5a1fff2d72fa5ba818520bb1c6f4185708658520413d076a1b`
- RGB manifest SHA256: `789f5162cf32be342ab868a1edd5f25166f735fbd44c7e87436764391ead0cda`
- 실행 및 source snapshot: `artifacts/r10-caption-cli-v1`
- 실행 lock SHA256: `debec3a2bc4f6d2f8738feb7587158ad6e3a706acea745c24473f37922a4bed9`

기존 integration runner의 lock records를 입력 12건으로 구성하고 기본 CLI를 실행했다. runtime에는 최종 RGB만 전달했다. 사진 역할, 원본 PPT, 캡션 정답은 evaluator 전용이다. 모든 CLI가 exit 0이며 출력 PPT 12개를 실제 PowerPoint COM으로 렌더했다. `results.json`에 명령, XML 개수, 출력 SHA가 있고 각 `runs/<id>/native/lock.json`에 runtime/OCR 모델 해시가 있다. 학습·threshold 조정·root 코드 수정은 하지 않았다.

## 결과

각 행은 Input / Photo / Encoder 캡션 순서다. textured_fraction은 실제 content_audit 값이며, 해당 guard의 veto 경계는 0.20이다.

| 사진 변형 | textured_fraction | box / label 총수 | 판정 |
|---|---|---|---|
| china color | .201129 / .202834 / .203091 | 0 / 0 | 3건 공백 |
| china gray | 0 / 0 / 0 | 3 / 3 | 3건 오출력 |
| flower color | .177085 / .177828 / .178773 | 3 / 3 | 3건 오출력 |
| flower gray | 0 / 0 / 0 | 3 / 3 | 3건 오출력 |

출력 전체는 box 9, label 9, edge 0, picture 0이다. picture 0은 안전성 성공이 아니다. 사진이 커다란 단색 native 사각형으로 바뀌었다. 실제 렌더에서 flower-color-input은 흰색 Input 캡션이 놓인 짙은 청록색 사각형으로 확인됐다.

## 대표 반례와 원인 경계

`flower-color-input`의 source bbox는 `[180,100,561,321]`, fill은 `[7,73,65]`, label은 `Input`이다. spatial OCR은 confidence `0.9909783363342285`, reason `only_spatial_ocr_approved`로 캡션을 승인했다. content_audit는 fraction `0.17708474242778263`, `eligible=true`, `no_dense_texture_veto`다. 신뢰 가능한 글자가 있다는 사실이 사진 프레임의 구조적 적합성을 증명하지 못한다.

`china-gray-input`도 실제 Input OCR confidence `0.9905119181`로 승인되며 texture fraction 0으로 통과했다. 기존 v3의 색상 covariance rank 조건은 RGB 세 채널이 같은 회색 영상에서 공간적 질감 유무를 판정할 수 없다. 컬러 꽃 사진에서도 최종 texture veto가 불충분함을 확인했지만, 이 집계만으로 모든 미검출 tile의 개별 원인을 확정하지는 않는다. 새로운 공간 질감 진단은 별도 계약과 산출물로 평가해야 하며 이번 실패를 덮어쓰거나 이 12건에 맞춰 threshold를 조정하지 않는다.

대표 반례 경로 (모두 이 worker checkout 기준):

- RGB: `artifacts/r10-photo-caption-v1/rgb/flower-color-input.png`
- 결과 및 content_audit: `artifacts/r10-caption-cli-v1/runs/flower-color-input/native/result.json`
- PPT: `artifacts/r10-caption-cli-v1/runs/flower-color-input/native/result.pptx`
- 실제 COM 출력: `artifacts/r10-caption-cli-v1/renders/flower-color-input.png`

## 검증과 제한

`verification.json`의 12건 PPT/PNG receipt 해시는 모두 일치한다. 출력 COM manifest SHA256은 `8619ea77a19fb83a3238a969b688cfe3d6c8d00c1b491edf36536e3ebaa3516a`다. COM은 렌더 완료 후 반환했으며 GPU는 사용하지 않았다. source snapshot과 기존 실패 산출물을 보존했다.

원본 사진은 china/flower 2개뿐이다. 12개는 색상·캡션 변형이며 독립적인 사진 12개나 모집단 성능 추정이 아니다. 이번 검사는 안정적인 캡션이 있을 때 기존 abstention이 사라지는 명확한 반례를 제공한다.
