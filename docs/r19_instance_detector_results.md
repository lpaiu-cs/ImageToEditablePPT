# R19 결과: 합성 객체 검출 개선, 실제 도식 종류 판정 실패

2026-09-09. 실행설계 `b32facf`, 데이터 `b0c33b5`, 학습량대조추가 `82c516d`. R18 실패와 제품 기본값을 보존했다. **전체 목표는 아직 미달이며 후속 연구를 계속한다.**

## 결론

개별 객체 bbox를 직접 학습한 R19는 새 합성 평가에서 **TP316/FP5/FN2**, 정밀도98.44%/재현율99.37%를 기록했다. 같은 자료에서 동결 R18 full_valid는TP55/FP0/FN263이었다. 흰 카드·윤곽·부모 컨테이너를 실제로 복원하는 개선을 COM 그림에서 확인했다.

하지만 원래 CogBot RGB에서는 **최종9개 중 종류와위치가 맞는 주요노드는1개**뿐이다. 합성 calibration도FP0을만족하지못했고eval에추가컨테이너오탐이남았다. 따라서 연구gate와실제사용기준모두실패, 프로덕션승격없음이다. 이를“GPU로문제를해결했다”거나“99%복원제품”으로부르지않는다.

## 환경과 학습량 가설

기존CPU환경을변경하지않고 `.venv-r19`를만들었다. Python3.12.9,torch2.8.0+cu128,torchvision0.23.0+cu128,RTX5090(12,0)에서실제CUDA행렬역전파와NMS를확인했다. 공식 [PyTorch설치조합](https://pytorch.org/get-started/previous-versions/)과 [torchvision Faster R-CNN](https://docs.pytorch.org/vision/0.23/models/generated/torchvision.models.detection.fasterrcnn_resnet50_fpn.html)을사용했다. ImageNet ResNet50 backbone만가져오고COCO검출기가중치는쓰지않았다. FrozenBatchNorm구조는학습/오프라인재로드에서동일하다.

- 최초R18train대표5장100step대조는TP0/FP0/FN25. 낮은점수후보는존재했으나.5기준출력이없었다. 이실패는 `control-v1`에보존했다.
- 새eval을열기전에 [학습량추가대조](r19_control_budget_amendment.md)를고정했다. 같은자료·seed·초기화·lr·batch로새600step을학습했고300step은TP25/FP2,600step은TP25/FP0/FN0으로통과했다. score기준은낮추지않았다. 두번의실행은GPU비결정성으로100step손실이정확히일치하지않으며bitwise재현을주장하지않는다.
- 이대조가중치를본학습에재사용하지않고새로초기화했다. train288장,batch4,1800step,사전lr일정그대로완료했다. 약168.3초,PyTorch peak GPU allocation4,079,060,992bytes였다. 프로세스전체VRAM이나인간편집시간측정은아니다.
- 학습대표6장의600/1200/1800step은각각TP48/FP5,TP48/FP3,TP48/FP2. 중간그림에서실제객체를모두포착하는반면큰부모후보가중복되는것을직접보았다. 정해둔1800최종checkpoint만calibration에썼다.

## 데이터와 평가 경계

독립작업이실제PPT384개→COM960×600을생성했다. [데이터감사](r19_instance_source_data_audit.md)에seed/어휘/배치/역할/스타일/parent계약이있다. train288/cal48/eval48. evalGT318개=일반노드294+부모24다. 부모와자식을unionmask로합치지않았다. sourceXML/COM/RGB SHA와고유384RGB를검사했고root는train대표6개만미리보았다.

calibrationGT282개에서 {.3,.5,.7,.85,.95,.99}의TP는모두282,FP는14/10/5/3/2/1이었다. FP0선택지가없으므로사전정의한.95진단fallback/calibration실패로고정하고나서eval을열었다. 기준을느슨하게고쳐통과시키지않았다.

| 같은 R19 eval | TP | FP | FN | 정밀도 | 재현율 | negative FP |
|---|---:|---:|---:|---:|---:|---:|
| R19 instance | 316 | 5 | 2 | 98.44% | 99.37% | 0 |
| R18 full_valid 고정.5 | 55 | 0 | 263 | 100% | 17.30% | 0 |
| R18 multiscale_valid 고정.99 | 47 | 1 | 271 | 97.92% | 14.78% | 0 |

R18은원래CPU환경, R19는새CUDA환경을사용했다. R18가중치/종류confidence.95/유효성임계값은재학습·재보정하지않았다. 모델/데이터/초기화/해상도가함께달라진경로대체비교이므로전체개선을단일요인으로귀속하지않는다.

| R19 family | TP | FP | FN |
|---|---:|---:|---:|
| colored_fill_white_bg | 48 | 0 | 0 |
| white_card_color_bg | 42 | 0 | 0 |
| outline_white_bg | 48 | 0 | 0 |
| nested_container | 64 | 2 | 2 |
| mixed_dense | 114 | 3 | 0 |
| hard_negative | 0 | 0 | 0 |

R19의낮은.05score후보는318개GT를전부포착했지만추가후보93개도있었다. 최종geometryTP와종류TP는모두316이다. **전역일대일매칭후GT역할별로분리**하면일반노드292/294,부모24/24이다. R18full/multi의최종부모TP는모두0/24다. 역할별로별도재매칭하여하나의예측을두TP로세지않았다.

## 실제 COM과 육안

48장×3조건=144PPT/native객체424개를실제COM960×600으로렌더하고모든receipt/원본PPT/PNG SHA를검사했다. 비교판48개를저장했다. root는유색/흰카드/윤곽/negative대표와오류가있는6장,총10개비교판을직접열었다.

흰카드와윤곽대표는R18두경로가완전공백인데R19는8개도형을모두남겼다. 중첩의부모도남는다. 다만nested-eval-000/004와mixed-eval-001/005/007에**원본에없는내부컨테이너**가추가된다. 이는1픽셀테두리오차가아니라새객체오탐이다. nested-eval-001은가느다란자식2개가빠졌다. 출력은native preset/noFill이며OCR/연결/원본채움은아직이경로에통합하지않았다.

## 복잡 원본의 실패를 단계별로 분해

원본RGB2760×1504에동일checkpoint/.95를적용해실제COM1380×752로렌더했다. 별도external guard가코드·모델·입력SHA를추론전후비교했다. RGB-only별도예측은R19흰카드eval-000의모든후보와최종객체가formal결과와정확히일치했다.

노출된수동17node장부를**예측뒤에만**읽어진단했다. 장부기본노드는육안rounded rectangle,명시된두DB는cylinder로해석했다. 이는독립GT가아니며도식전체객체를빠짐없이열거한것도아니다.

| 원본 단계 | 후보/출력 수 | 종류무시 TP/FP/FN | 종류포함 TP/FP/FN |
|---|---:|---|---|
| 저장된post-NMS 후보(score≥.05) | 94 | 14 / 80 / 3 | 8 / 86 / 9 |
| 최종score≥.95 | 9 | 5 / 4 / 12 | 1 / 8 / 16 |

노드별로같은geometry를지지하는후보를살펴보면candidate없음3개,맞는종류후보없음6개,맞는종류후보는있으나score거부7개,맞게유지1개다. local지원분류와전역매칭수를구분해저장했다. 저장자료는post-NMS이므로NMS이전손실은이증거로판정할수없다.

**실제그림은여전히불만족스럽다.** 중앙Bot Orchestrator만합당한rounded node로남고,흰카드/텍스트영역이diamond·ellipse·cylinder로잘못출력됐다. matched ROI그림은GT가아닌예측bbox로잘랐다. 실제테두리가보이는Sensory/Identity/Social등에서도분류가틀렸으며일부crop은옆문맥이나잘린경계를포함한다. 후보생성만의문제에서**ROI종류와신뢰도의도메인차이**가다음핵심병목으로드러났다.

[원본 실제 COM](../artifacts/region-image-only-r19/original-audit-v1/original-comparison.png) · [매칭된 예측 ROI](../artifacts/region-image-only-r19/original-audit-v1/matched-predicted-rois.png).

## 다음 가설과 현재 한계

먼저동결된같은예측bbox를고정하고종류판정의입력해상도/문맥/내부잉크의존성을분리한다. “크게학습했더니합성이좋다”에서멈추지않는다. 후보가없는3개문제와이미있는후보13개의종류/거부문제를섞지않는다. 경계정보추가나local분류재학습은이분해의증거를보고다음사전등록으로진행한다.

R19는native합성/영문/text-open-line/nativeglyph중심이다. CogBot의그라데이션·그림자·아이콘·복잡한국소문맥은train분포와다르다. 새로운실제이미지일반화,전체구조통합,인간수정시간감소는아직입증하지못했다. 품질목표는달성되지않았으므로전체연구목표는활성상태로유지한다.

기존helper를재사용하고학습용가상환경을분리했다. 새검출/기존primitive관련9tests는CPU/GPU환경에서통과했다. 제외없는기존환경전체회귀는**1408passed/6failed/2xfailed**다. 실패6개는R18과동일한source_centerline사례이며해당코드/허용오차를수정하지않았다. 독립읽기전용코드감사에서FrozenBN/GT전달/좌표/controlgate/cal-before-eval를확인했고predict전후SHA누락은외부guard로보완했다.

## 동결 증거

데이터manifest는 `C:/Users/lpaiu/.codex/worktrees/9cae/ImageToEditablePPT/artifacts/r19-instance-source-data-v1/dataset_manifest.json`,SHA `23b9dabaa5d584d31552b15116e9887b309b844fef86c710bad78dee77471cb2`다. 아래는 `C:/vs/ImageToEditablePPT/artifacts/region-image-only-r19/` 기준이다. 대용량artifact는로컬에있으며Git문서커밋만으로원격보관된것은아니다.

| 파일 | SHA256 |
|---|---|
| control-v1/training.json | 223641a5ac4c2d4a513ec9520aec33cee16d2ce30b046507aac0269665286783 |
| control-v2/training.json | 7770d7bef8e5587f99318f8d9e242253c4b593853b3f65cd7d7ad828c1310293 |
| training-v1/final.pt | 3c74f33ca5e98fdb9cc8ff585b71ff69e802dffa53529e4db580b351efcb8120 |
| training-v1/lock.json | e819ee684480aad4ef722f00f441ec63efcc4ab8b1949ca322624ca30d9a8663 |
| eval-v1/results.json | 9504ac606549e78aec61d316b09fcb3a5e1f93e61597e634917626a319b90edb |
| eval-v1/calibration.json | 84b1fd73292fd247cc114cef15e5253ee76376ef41929fc480b4856383e37343 |
| com-v1/audit.json | 8feab8bad4bb28f1a9f20f801928b64d70aeaba880fecd47bea87ceb6918d723 |
| original-audit-v1/diagnostic.json | 7b058df858f1caf7f02430239418cc902305a01b3cbd3702f4def3ec7f5b2677 |
