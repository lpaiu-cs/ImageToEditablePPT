# R10 새 RGB 추론 실행 계약

기존 예측/GT를 입력하지 않고 기존 validation RGB15개와 checkpoint만으로 현재 코드의 forward pass를 다시 수행한다. 새 학습, test/holdout 이미지·annotation 열람, checkpoint 후보별 성능 선택은 하지 않는다.

## 사전 live 검증

- 선택 가중치: `C:/vs/ImageToEditablePPT/workbench-ml/run-v13-detector/checkpoints/last.ckpt`, SHA `e6a6926ef4e65e11288d61d3b12723b19322ee0d44e6e94b9075cba11a1a6f58`.
- checkpoint 실제 metadata: num_classes7, LR.0003, epoch14, global_step1680. cls_score는7×1024, bbox_pred는28×1024이다. checkpoint에는 훈련 코드 SHA와 클래스 이름이 없다.
- 기존 run metadata는 mixed448 train/56 val/56 test, seed1303,15epochs,CPU이다. 현재 training loader도 train/val을 분리한다. 현재 mixed manifest SHA `c28737091a654fd8c35017b76318def3aec85edfffe1d070ba7b487629c7e5f9`; 원 PIL/soffice manifest의 기록 SHA도 live 일치했다. 이는 현재 파일과 기록의 일치이며 과거 학습 전체의 실행 attestation은 아니다.
- RGB manifest의 기존15ID는 모두 현재 manifest에서 val이다. 이 확인에는 분할 metadata만 읽었으며 annotation/test 이미지/PPT는 열지 않았다.
- 다른 로컬 detector epoch05/08 및 family/gate checkpoint는 파일 목록만 확인했다. 성능을 보고 새 가중치를 선택하지 않고 기존 v13 last를 사용한다.

## 클래스 계약과 실행

source1,2,3,4,5,6은 각각 box,rounded_box,section,label_anchor,flow_cluster,panel이다. 현재 enum 번호로1,2,4,5,6,7에 명시 대응시킨다. source0은 background이며 현재 ellipse3은 미지원이다. `a00d61c`의 실제 enum을 다시 확인했다. 클래스 의미는 Git 이력에서 추정한 것이며 새 실행으로 훈련 당시 메타데이터를 소급 생성하지 않는다.

`tools/run_fresh_rgb_detector.py`는 현재 worktree import를 검증하고 코드 파일 SHA, Git HEAD, 라이브러리 버전, 가중치 SHA, RGB SHA, class map을 forward 전 잠근다. weights_only=True와 strict state_dict로 현재 Lightning model에 로드한다. CPU8 threads, full RGB, batch1, eval/inference_mode이며 model 생성은 pretrained weights 없이 실행한다.

추론 전에 Python open allowlist를 설치한다. checkpoint·고정 RGB·실행 소스만 읽을 수 있고 dataset/예전 prediction/PPT는 허용하지 않는다. imports/model constructor 이전 파일 접근까지 차단하는 OS sandbox는 아니다. 입력 ID는 보고 키로만 사용하며 model은 RGB tensor만 받는다. 별도 프로세스에서 실행하며 detector cache를 쓰지 않는다.

출력은 새 predictions.json 및 execution-lock/실행/read 기록이다. raw source label과 명시적으로 변환한 현재 label을 함께 보존한다. score/NMS/containment 연구 후처리는 root가 새 예측을 받아 수행한다. 이 도구는 GT 점수나 PPT를 생성하지 않는다. 실행 실패는 새 디렉터리에 보존하며 파일을 덮어쓰지 않는다.
