# 로컬 PPT/COM semantic classifier 최소 개발 진단

## 결론

**최소 학습은 실행됐으나 반례 해결에 실패했다. 채택하지 않는다.** 학습에 없던 꽃 사진의 무캡션 컬러/회색 crop을 diagram으로 승인했고, 기존 PHOTOID caption 반례도 diagram score .95503으로 승인했다. 모델·threshold를 결과에 맞춰 재조정하지 않았다. 개발 방향 확인이며 holdout/production acceptance가 아니다.

## 사용 자산과 경계

`C:/vs/ImageToEditablePPT/.venv/Lib/site-packages/sklearn/datasets/images/README.txt`가 china/flower를 CC-BY2.0으로 명시하고 원 Flickr 링크를 제공한다. 해당 README를 내부 artifact에 원문 복사했다. china는 danielbuechele/6061409035, flower는 vultilion/6056698931 링크다. 꽃 attribution 문구에는 danielbuechele가 반복되지만 링크 계정은 vultilion이므로 이 불일치도 원문 그대로 보존했다. 본 진단에서는 저자/링크를 모두 기록하고 사진·파생자료를 커밋하지 않는다.

원본 경로는 위 images 폴더의 `china.jpg`, `flower.jpg`다. 자산 SHA는 preregister에 고정했다. 변형은 COM 내 크기 맞춤과 회색화이며 추가 외부 이미지 다운로드가 없다. Matplotlib Hopper는 로컬 sample README/배포 LICENSE에서 사진별 출처를 확인하지 못해 사용하지 않았다. 기존 dataset/holdout 이미지는 사용하지 않았다.

## 사전 고정과 생성

실행 도구 `tools/r10_classifier_pilot.py`의 prepare→COM native render→derive→COM derived render→evaluate 순서다. 원본 역할은 준비 단계에서 고정했다. 총28개의1slide PPT를 동일 PowerPoint COM으로800×450 PNG 렌더했고 두 manifest에서 PPT/PNG 개별 SHA를 재검증했다.

- native diagram6개와 그 동일 구조를 picture로 삽입한6개는 positive.
- train china/eval flower의 color/gray × plain/caption × 반복2개는 negative16개.
- base scene6개는 split별 node 위치를 달리하며 native/raster 파생본을 같은 split에 묶었다. 동일 템플릿 계열이므로 새로운 레이아웃 일반화를 주장하지 않는다.
- 사진 asset은 china=train, flower=eval로 완전히 분리했다. calibration에는 positive4개만 있어 이진 calibration은 불가능하다. threshold .5를 미리 고정하고 조정하지 않았다.
- photo 복제는 동일 split 안에서 같은 RGB다.28개 crop 중 unique20개이며 cross-split crop SHA 중복은0이다. duplicate를 독립 사진으로 세지 않는다.

XML 검사에서 native positive6개는 pic0, raster diagram positive6개는 pic1, negative16개도 pic1이다. 즉 picture 저장 형식을 바로 negative로 쓰지 않았다. 실제 COM 이미지 중 native diagram과 꽃 caption을 육안 확인했다.

초기 v1 준비본은 split별 base 배치가 같음을 **학습 전** 확인해 사용하지 않았다. v1은 보존했고 v2를 새 preregister로 생성했다. 첫 COM 호출은 Windows PowerShell의 Get-FileHash 미해결로 실패했으며 pwsh로 새 폴더에서 성공했다. 실패 산출물을 조용히 대체하지 않았다.

## 입력 및 모델

현재 `closed_rect_proposals.py`를 snapshot으로 동결하고 `propose_union(rgb)`를 실행했다. 각 사전 지정 target 영역에 IoU≥.8인 실제 후보를 evaluator가 대응시켰으며 후보 누락은0/28이다. 이는 모든 생성 후보의 의미 정확도 평가가 아니라 지정 target crop의 classifier-only 평가다.

모델 입력은 후보의 원본 RGB crop를96×64로 resize한 숫자 tensor뿐이다. forward에는 파일명, 역할, XML, split, confidence, bbox 좌표를 넣지 않는다. target/분할 metadata는 학습 mask와 evaluator에만 사용했다. crop 전체 이미지를 통해 캡션 위치 같은 시각적 shortcut을 학습할 수 있는 한계는 남는다. Python/OS 파일 접근 sandbox attestation은 하지 않았다.

작은 CNN(3→8→16채널, 4×4 pool, linear1)을 임의 초기화했다. seed1909, Adam lr.003,120epochs,threshold.5를 사전 고정했다. pretrained 다운로드, 외부API, GPU는 사용하지 않았다. 학습에는 train12개만 썼고 calibration/eval은 gradient에 포함하지 않았다.

## 결과

| 분할 | crop | positive | negative | negative 오승인 | positive 오거부 |
|---|---:|---:|---:|---:|---:|
| train | 12 | 4 | 8 | 0 | 0 |
| calibration | 4 | 4 | 0 | 측정 불가 | 0 |
| eval | 12 | 4 | 8 | 4 | 0 |

eval negative8개는 unique4개다. 그중 무캡션 꽃 color/gray 두 종류가 각각 score .74744/.81749로 오승인됐다. caption color/gray는 .00062/.00103으로 거부됐다. native/raster diagram4개는 모두 승인됐다. 사진 하나의 네 표현이므로 독립 자연사진8개의 성능으로 해석하지 않는다.

기존 `photo_icon-s1-aa4.png`의 실제 OCR PHOTOID caption bbox `[91,126,299,269]`를 고정 모델에 별도로 입력했다. diagram score .9550318로 오승인됐다. 이 사례는 이미 노출된 synthetic 회귀이며 eval 통계와 분리했다. **당초 사진 caption 반례의 해결은 입증되지 않았다.** train loss가 .69746→.00000466으로 내려간 사실은 실사용 일반화 근거가 아니다.

## 보존 근거

내부 미커밋 artifact: `artifacts/r10-classifier-pilot-v2`.

- `preregister.json` SHA: `a3833b946a1ba5a096d10ebf6f935b2f2e0a7b01702c38824c3a8205da2982a9`
- `model.pt` SHA: `248e7a9c79542a21b12f06993e5f54ab087bf15ba33ae9e6ce4d4090651af7b3`
- `candidate_manifest.json` SHA: `a5b312b45ca2dee5830aaafa44ed004041460ed2551f81e9f81510d137139d77`
- `native-renders/powerpoint_render_manifest.json`, `derived-renders/powerpoint_render_manifest.json`: COM version와 모든 PPT/PNG receipt.
- `results.json`: 점수·분모·모델SHA, `verification.json`: XML/중복 검사, `previous-counterexample.json`: 기존 반례 회귀.
- `assets/README-source.txt`: 번들 출처 원문. 자산과 모델은 git에 넣지 않았다.

기존 train annotation renderer, frozen 평가, root runtime을 수정하지 않았다. 결과 후 추가 학습·threshold 선택은 하지 않았다. 다음 단계가 필요하다면 독립 사진 수와 문맥 대조를 늘리는 데이터 설계가 먼저이며, 이 모델을 실변환 경로에 붙일 근거는 없다.
