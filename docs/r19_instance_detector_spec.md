# R19: 온전한 객체 bbox 직접 학습

2026-09-09. 사용자가 후속 가설 점검과5090 GPU 사용을 승인했다. R18 `bc2ca95`의 실패와 제품 기본값은 보존한다. 이번은 닫힌 구조 후보를 직접 학습하는 후속 실험이며 전체 image→editable PPT 목표를 닫힌 도형만으로 축소하지 않는다.

## 가설과 범위

R18은 점유 foreground 조각을 bbox로 묶어 글자·아이콘을 후보로 만들었다. 부모 컨테이너는 후보0/3, 흰 카드는최종0/18이었다. **원본 PPT 개별 객체 bbox로 감독하는 instance detector가 온전한 구조를 포착하는가**를 먼저 검사한다. 종류와 bbox를 함께 학습하되 geometry/종류 성능을 나누어 기록한다. 이는 architecture, 데이터, 초기화가 함께 바뀌는 대체 경로 실험이며 개선 전체를 특정 하나의 요인에 귀속하지 않는다.

기존 코드의 torchvision Faster R-CNN 사용 방식을 재사용한다. 얕은 해상도의 점유/6종crop 모델을 후처리로 계속 보정하지 않는다. 새 runner만 만들고 이전 lock 대상 코드·데이터는 변경하지 않는다. 실패한eval조건을 바꿔 소급 성공시키지 않는다.

## 실행 환경과 모델

기존 `.venv`는PyTorch2.13.0+cpu이므로 보존한다. 별도 `.venv-r19`에Python3.12, torch2.8.0+cu128/torchvision0.23.0+cu128을 고정한다. 공식 [설치 조합](https://pytorch.org/get-started/previous-versions/)을 사용하며 GPU tensor/backward/NMS smoke로 실제5090실행을 확인한다. 타인의 GPU/PowerPoint 프로세스를 종료하지 않는다.

표준 [Faster R-CNN ResNet50 FPN](https://docs.pytorch.org/vision/0.23/models/generated/torchvision.models.detection.fasterrcnn_resnet50_fpn.html)을 사용한다. 학습입력은RGB tensor와학습용boxes/labels, 추론입력은RGB만이다. ImageNet1K_V1 backbone을 공식 torchvision loader에서 받고 SHA를 기록한다. COCO detector weights나 기존 PPT checkpoint는 로드하지 않는다. 기존MobileNet 기반검출기와 같은 라이브러리를 쓰되 작은객체용피처를 포함하는 ResNet FPN을 택한 설계 가설이다.

num_classes7(background+기존6preset), trainable_backbone_layers5, min_size600/max_size960, box_score_thresh.05, box_nms_thresh.5, box_detections_per_img100. 부모/자식은 별도bbox이며 포함만으로 제거하지 않는다. 출력bbox는 원본RGB좌표다. native preset/noFill 출력은 기존 `write_shapes`를 재사용한다. OCR/연결/원본fill/adjustment는 이 실험에서 변경하지 않는다.

## 학습과 조기 육안 검사

1. **양성 대조**: 이미 노출된R18 train의네appearance대표와negative1장, 총5장만으로100steps/batch2/AdamW lr.0003/seed1901. 학습가능성 검사는score.5에서geometry recall≥.9, 종류+geometry recall≥.8. 실패 시 새eval을 열지 않고 구현/학습 한계를 진단한다. 대조checkpoint는 본학습의 초기화에 쓰지 않는다.
2. **본학습**: 새R19 train288장만, seed1901, batch4, AdamW lr.0003/weight_decay.0001,1800steps.1200step이후lr.0001. CPU4threads, GPUfloat32, TF32허용. augmentation없음, GTcrop없음. 모든층학습. final1800만 calibration에 사용하며 최고성능checkpoint를 eval에서 고르지 않는다.
3. train대표6장 그림과loss를step100/600/1200/1800에 저장한다. root가 중간이미지를 육안으로 보고 가설/진행 판단한다. NaN/OOM/잘못된좌표/감독계약오류면 정지하고 별도run으로 수정한다. 낮은훈련성능만으로eval을 열어 조건을 맞추지 않는다.
4. 학습끝train대표의geometry/종류 성능을 기록한다. 모델·명세·코드·manifest·train이미지 SHA와버전/GPU이름/시간/메모리를 실행전후확인한다. 중간loss와heartbeat에step을 기록해 live process를 검증한다.

## 새로운 source와 평가 분리

별도 작업이native1200×750 sourcePPT384장을COM960×600으로 렌더한다. train288/cal48/eval48이다. positive5family(colored_fill_white_bg,white_card_color_bg,outline_white_bg,nested_container,mixed_dense) 각각48/8/8장, hard_negative48/8/8장이다. 일반3~9nodes, dense9~15nodes, 부모1~2개를별도객체로보존한다.6preset종류균형, 흰카드·윤곽·채움, 문단·작은native장식·외부문자·겹치는열린선을포함한다. 부모추가로늘어나는rounded-kind빈도는자식과분리한다.

eval은seed/어휘/배치계열을분리한다. 입력/GT는같은PPT에서오며 sourceXML bbox/preset/noFill/부모자식관계/COMreceipt와중복RGB SHA를감사한다. annotation은정답에만사용한다. CogBot수동장부를생성기에사용하지않는다. 세부생성계약은독립작업의데이터감사에기록하고학습전manifest SHA를동결한다. train대표5family+negative만미리육안으로연다.

calibration에서score {.30,.50,.70,.85,.95,.99}별최종종류+geometry를비교한다. FP0/TP>0 중recall최대, 동률높은threshold를선택한다. 없으면.95진단fallback/calibration gate실패. 저장후에만48eval의픽셀을연다. 연구gate는R18처럼precision1,recall≥.8,positive-family별recall≥.5,negativeFP0,calibration통과다. 부모·자식별 geometry와종류성능을별도보고한다. 클래스무시geometry와종류매칭은기존IoU≥.5일대일matcher를재사용한다.

R18full_valid/multiscale_valid도고정임계값.5/.99로동일신규eval에서별도기준선측정할수있다. 재보정/재학습하지않으며runtime버전차이를보고한다. 평가성공여부와무관하게원래CogBot RGB를추론해실제COM/후보/최종그림을본다. 원본의이미노출된수동17node는사후진단에만사용한다. 원본에서대량누락/오탐이면합성gate통과만으로프로덕션승인하지않는다.

## 종료와 다음 판단

native COM, 육안관측, 정량검증, 회귀검사까지완료해실패/개선을모두기록한다. **이번phase종료가전체목표달성은아니다.** 성공하면검출확실성에맞춰기존RGB-only생산경로와연결·텍스트·채움의통합을검토하고, 실패하면단계별증거를다음가설로삼는다. 인간편집시간검증은자동렌더시간으로대체하지않는다. 기존formalholdout은재사용하지않고추가독립평가는새사전등록후에진행한다.
