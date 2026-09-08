# R10-F: 저장된 장면 없이 RGB부터 다시 실행

## 목적

R10의현재44TP/2FP/23FN,87정답label/0오답/4공백은기존검출예측에서후처리를고친결과다. 이미지단독에서유도된예측이지만,검출기를이번코드로다시실행했다는뜻은아니다. 특히legacy checkpoint/classmap/추론codeSHA의불명확성을실험출력PPT로가리지않는다.

## 실행 계약

1. ML작업은현재checkpoint/loader/classmap/training split을검증하고새추론codeSHA·weightSHA를고정한다. 기존15 RGB만으로fresh inference를수행한다. 원GT/이전prediction/label/관계파일은추론입력에서금지한다. 새학습이나Phase16holdout열람은하지않는다.
2. root는RGB와그실행에서나온객체의ID/role/kind/bbox/confidence만받는후처리API를구축한다. 문자열label·edge·annotation·GT는이경계의입력필드로허용하지않는다.
3. RGB OCR→공간중복선택→C-v2→원본S→공간/방향일치T→native writer를동일설정으로실행한다. 모델검출을캐시로대체하지않는다. 호환성검증용예전예측재생은fresh실행과별도이름으로기록한다.
4. 새checkpoint추론과같은실행의검출결과를PPT까지SHA로연결한다. source/emitted scene,IO기록,각stage audit,원본/최종render를보존한다. GT평가는변환이끝난뒤별도프로세스에서만실행한다.
5. 사용자에게재사용가능한실행경로를제공하되기존제품default/배포승인을자동으로바꾸지않는다. 새로실행한검출결과가달라지면그차이를숨기지않고비교한다.

범위: 이미본합성validation15의전체경로검증이다. 모델훈련이력불명확성이남는경우이번추론provenance확보와구별한다. 시각QA와native편집객체검증은수행하되사람수정시간승인으로대체하지않는다.

## 단일 이미지 실행 경로

`tools/convert_source_evidence.py --image <RGB 파일> --checkpoint <7-class checkpoint> --output <새 출력 디렉터리> --acknowledge-legacy-research-model`로 검출부터 native PPT까지 새로 실행한다. 기존 15개 검증 묶음 제한은 기본 검출 명령에 유지하고, 명시적인 `--user-images` 경로만 다른 입력 수를 허용한다. 사용자 이미지 실행은 holdout으로 표시하지 않는다.

원본 RGB를 묵시적으로 합성/색변환하지 않고, 기존 출력 디렉터리를 덮어쓰지 않는다. 기존 모델의 클래스 훈련 이력 미기록·ellipse 미지원은 그대로이며 위 플래그는 사용자가 해당 연구 모델을 선택했다는 뜻이지 제품 승인 표시가 아니다. 출력의 detector/에는 새 forward 실행 증거, native/에는 RGB·단계별 감사·PPT가 남는다. 평가용 주석이나 정답 PPT 경로는 이 명령에 없다.
