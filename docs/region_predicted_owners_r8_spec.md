# R8-P: 고정된 이미지 단독 예측을 native 출력에 연결하는 실험

## 목적과 사전 결정

검출 성적과 사용 가능한 PPT 사이의 손실을 분리한다. 학습 트랙의 최종 v2 handoff를
독립 검증한 뒤 같은 개발용 15장을 사용한다. 추가 학습, GT 객체/라벨/관계 주입,
객체 종류 변경, 좌표 보정, 사후 임계값 탐색은 이번 기준선에 포함하지 않는다.
기존 R8 morphology 결과 및 R6 제품 경로는 변경하지 않는다.

- 입력 파일 SHA: `346c4090c209e13243ed7a4d96723fe09921e037660acf4f3e8dd776c08f45e4`.
- payload SHA: `67fd2464008807d3360ece10d832ba80e1e0fcedf3ab9f906e8dcf9150cafee6`.
- 94개 node, 11개 container를 ID/종류/좌표/신뢰도 그대로 전달한다.
- legacy 클래스 해석은 Git 이력에서 추정한 것이고 과거 추론 실행 코드 SHA는 미확인이다.
  명시적인 연구용 허용 옵션 없이는 실행하지 않는다. 이 실험으로 해당 한계가 해소되지 않는다.
- checkpoint 선정에 노출된 합성 validation이다. 미관측 holdout/논문 일반화 성적으로 부르지 않는다.

## 단계와 경계

1. validator가 원본 예측과 SHA 결합 자료로 handoff를 재도출하여 검증한다.
2. 검증된 sample에서 변환에 필요한 RGB, 크기, 객체 필드만 subprocess에 전달한다.
   파일명/원본 데이터 종류/GT 경로는 변환 입력으로 사용하지 않는다.
3. 고정 예측 객체 → 기존 `trace_scene(transparent_gaps=True)` → 기존 `recover_labels`.
   검출기의 node/container 역할을 geometry selector/identity filter로 다시 결정하지 않는다.
4. 기존 스타일 추정 및 768 기준 좌표 정규화 → 기존 native writer.
5. `label_anchor`는 기존 writer의 연결 부착용 custom geometry가 지원하지 않는다.
   이번 기준선에서는 그 객체에 붙은 연결만 명시적으로 기권한다. 라벨 객체 자체는
   기존의 테두리 없는 editable text box로 유지한다. 연결을 자유 선으로 몰래 대체하지 않는다.
   빈 라벨 textbox도 개수와 육안 관측에서 구분해 보고한다.
6. source_scene에는 추적 결과를 보존하고 emitted_scene에는 실제 출력 객체/연결만 기록한다.
   미지원 종류와 native 경로 적합 실패의 연결 누락을 각각 기록한다.
7. 각 subprocess의 Python 파일 open allowlist를 기록한다. OS sandbox라고 주장하지 않는다.
   GT는 별도 평가 프로세스에서만 읽는다.

## 평가 및 다음 방향의 결정

동일 R8 평가 규칙(IoU .5, 역할/종류 분리, 방향 관계, 일치 node 라벨)과 실제 PowerPoint
렌더를 사용한다. 전체 15장을 원본과 나란히 육안 확인한다. trace 단계 오류와 native
기권을 분리하며, 테스트 통과나 검출 성적만으로 제품 승인하지 않는다.

예측 객체가 좋아도 연결이 나쁘면 화살촉 관측/owner 경계/경로 추적을 우선 진단한다.
추적은 맞고 native에서만 누락되면 지원되는 편집 객체 표현을 별도 실험으로 다룬다.
OCR은 원문 복사가 아닌 이미지 관측 개선만 허용한다. 후속 변경은 별도 설정·산출물로
사전 명세하며 이번 기준선을 덮어쓰지 않는다. 사용자 수정 시간은 아직 측정하지 않는다.
