# R10 새 RGB 검출 결과

현재 worktree의 새 프로세스에서 기존 RGB15개와 v13 checkpoint만으로 forward pass를 완료했다. 원시 검출154개이며 GT 점수는 계산하지 않았다. 이전 prediction 파일을 읽거나 cache로 재사용하지 않았다.

- 실행 Git: `b807c8ffaa0dd816f07d90c58cff650af7617797`
- 실행 도구 SHA: `a8f7f0c7aa587b33fe1728eb5647872ef122bb251bb4dd22abb94fb53ebe8066`
- 가중치 SHA: `e6a6926ef4e65e11288d61d3b12723b19322ee0d44e6e94b9075cba11a1a6f58`
- predictions SHA: `2567fd57c142377f93e1c3eb23f3419e780922409951e83a8d634f97c4b0cb66`
- execution-lock SHA: `7e89defda1c871e44f99163b53d54c89757d36122441c860cb59cd4776dc4320`
- handoff payload SHA: `070a53fae1e021bee8b66f7a0f8442f65f4c0dbc4ac5cbd547605b4c8450b2a7`

파일은 `artifacts/r10-fresh-detector-v2/`에 있다. `handoff.json`과 추적된 `benchmarks/r10_fresh_detector_execution.json`은 동일 payload다. 기존 legacy export 스키마의 실행 미확인 문구를 변경해 재사용하지 않고 새 raw handoff 스키마로 구분했다. root는 SHA 확인 후 `predictions.json`의 현재 class-space boxes/labels/scores를 후처리에 입력한다. source_labels도 별도 보존했다.

Python read guard는 checkpoint load부터 전체 추론까지 활성화됐다. 허용된 입력은 15RGB·checkpoint·명시 소스 파일이며 거부0이다. 소스 파일 재읽기는 종료 시 SHA 불변 검증이다. imports/model constructor 전에 수행된 라이브러리 초기화는 이 guard 범위 밖이며 OS sandbox를 주장하지 않는다. CPU8 threads, batch1, eval/inference_mode로 checkpoint load+forward+검증 구간 약2.97초였다.

첫 `r10-fresh-detector-v1` 실행은 Torch serialization의 지연 import가 allowlist에 걸려 checkpoint load 단계에서 실패했다. forward 전 실패와 read log를 보존했다. 허용 범위를 넓히지 않고 해당 라이브러리를 먼저 import한 v2에서 완료했다.

별도 출력 검증에서 15 unique ID,154개 box/score/label/source-label 길이, 유한 값, 이미지 내부 bbox, source→current map의 일치와 모든 guard event 허용을 확인했다. 원시 current label 수는 box39,rounded_box49,label_anchor42,flow_cluster11,panel13이며 section 검출0이다. 이는 threshold 이후 선택 객체 수가 아니다.

실행 provenance는 새로 확인했지만 훈련 checkpoint의 클래스명/훈련 코드 SHA 미기록은 남는다. 클래스 의미는 legacy enum 이력에서 추정했고 ellipse는 미지원이다. 기존15는 노출된 합성 validation이며 새 holdout·논문 전이·제품 승인·사람 수정시간 성과로 해석하지 않는다. downstream O+C+S+T와 native COM 검증은 root가 이 fresh 결과로 별도 수행한다.
