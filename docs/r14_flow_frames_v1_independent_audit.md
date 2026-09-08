# R14 v1 독립 fresh43 감사: 내부 생략 목표2건 실패

새 source 대조11건에서 컬러 사진2건은 no-fill·빈 라벨 테두리로 보완됐고, 기권 목표7건은 카드가 생략됐다. **회색 사진과 단순 아이콘2건은 내부 캡션이 남아 정책 목표에 실패했다.** 회색 사진은 단색 채움도 남았다. 보완 테두리의 텍스트가 후처리에서 되살아난 결함이 아니라, 기존 texture gate를 통과한 카드에는 보완 정책이 적용되지 않는 범위의 한계다.

## 고정 실행

- root commit: `8ff3fc9efa9af0053a1d87c1797a1415b9a331c2`
- artifact: `artifacts/r14-flow-fresh-v1`
- lock SHA256: `813a61b4c32dbd23a4d479f629dcc06151abd565be02cfcf164e11a97947e6ba`
- 기존 R11 source32 records와 새 `r14-flow-frame-controls-v1/rgb-manifest.json`의11 records를 사용했다. 새 입력 사전 계약은 `docs/r14_flow_frame_controls.md`에 있다.
- 기존 spatial probe 설정에 `--compact-boxes --flow-frames`를 추가했고 raw-branches는 껐다. 모든43건은 RGB부터 OCR·추론을 새로 실행하여 exit0이다. 정답 source PPT/역할/객체 metadata는 추론에 전달하지 않았다.

매 건 source/RGB 해시를 확인했고 source snapshot과 native lock/JSON/PPT를 보존했다. 코드 읽기에서 라벨 제거와 no-fill, 후속 accepted 텍스트 비우기, emit 후 witness 존재 확인을 대조했다. 제품 코드·cutoff를 수정하지 않았다.

## 관측 결과

| 새 대조 | 결과 |
|---|---|
| china-flow | frame closed:2, texture fraction .5247621371, eligible=false 유지, noFill/빈 텍스트/두 연결 |
| flower-flow | frame closed:2, fraction .2693356992, eligible=false 유지, noFill/빈 텍스트/두 연결 |
| gray-flow | fraction .1996806175, eligible=true, frame 보완0; 일반 경로에서 Photo 및 짙은 단색 채움 출력 |
| icon-flow | fraction0, eligible=true, frame 보완0; 일반 경로에서 Input 출력 |
| both-in/out, one-way, same-port, failed-chain, no-arrows | 카드·관련 연결 기권, 정상 Read/Check seed만 유지 |
| standalone | 완전 빈 출력 |

정책 양성 목표4건 중2건을 충족하고2건은 실패했다. 음성 카드 목표7건은 기권했다. 사진은 기존 china/flower2자산의 파생이며 아이콘은 단순 합성 인물1개다. 이11건을 일반화 성능이나 독립 사진11장으로 해석하지 않는다. 특히 아이콘의 texture veto는 준비 단계부터 가정하지 않았으며, 관측 결과에 맞춰 fixture를 바꾸지 않았다.

기존32건의 emitted_scene 전체는 R11과32/32 동일하다. 기존 양성12건의44box/44label/24edge, 단독 사진20건의 빈 출력이 유지된다. 이 회귀 유지가 새 목표2건의 실패를 상쇄하지 않는다.

## 실제 native/COM 검증

전체43 PPT XML을 읽었다. 보완된 두 카드의 p:sp는 noFill이며 텍스트가 없고 picture0이다. source witness 방향에 따라 실제 stCxn/endCxn ID가 seed→frame 및 frame→seed에 부착됨을 확인했다. 원래 content eligible=false는 그대로다. gray-flow/icon-flow의 caption은 일반 owner에 존재하며 flow_frame_audit.retained는 비어 있다.

root의 COM 반환 이후 기존 POWERPNT guard를 통과해43개 최종 PPT를800×450으로 실제 렌더했다. PPT/PNG receipt SHA가 모두 일치한다. 기존 단독 사진20개는 모든 RGB 픽셀이255다. 새11개 실제 렌더를 contact sheet로 직접 확인했고 회색 사진의 짙은 채움·Photo와 아이콘의 Input을 확인했다. COM은 즉시 반환했다.

- COM manifest SHA256: `e8b8b63acc20397ece9019e43e9428663818dd888e7ba801577d4b8957a52b74`
- `verification.json`, `verify.py`: XML·이전 결과 동등성·receipt 검증 기록
- `new11-contact-sheet.png`: 새 대조 실제 출력
- 실패 경로: `runs/gray-flow/native/result.json`, `runs/icon-flow/native/result.json` 및 같은 폴더 PPT

## 독립 검토의 범위

v1의 texture-veto owner만 보완한다는 코드 계약에서는 no-veto 회색/아이콘이 대상 밖이다. 따라서 이를 '보완 카드의 텍스트 부활'로 보고하면 잘못된 원인 수정이 된다. 그러나 사용자 승인 정책의 내부 생략 목표에는 분명히 실패한다. v1 결과는 보존하고 후속 정책 확장은 별도 arm으로 검증해야 한다.

후속 대상 집합을 non-flat owner까지 넓힐 경우 seed와 대상의 교집합에 주의해야 한다. 기존 texture통과+label 집합을 고정해도 회색·아이콘 카드가 원래 seed 조건을 만족하므로 서로를 승인할 수 있다. 대상 두 카드 연쇄를 단순히 '구제된 frame을 새 seed로 쓰지 않는다'만으로 막을 수 있는지 별도 확인해야 한다. 이 부분은 v2 설계 위험이며 v1에서 관측된 새 실패로 세지 않는다.
