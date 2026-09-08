# R11 이미지 단독 편집 초안: 수정 결과와 승인 경계

## 결론

실패 기록에서 끝내지 않고 실제 RGB 입력→native PPT→실제 PowerPoint 렌더→독립 반례 검사를 반복했다. 중첩 내부 연결 소실, 자식 글자의 부모 중복,1픽셀 경계를 면적비로 탈락시키던 문제, 세로 라벨 방향과 가시성, 안정적인 캡션을 붙인 사진의 오출력을 수정했다. 고정 단일 이미지 CLI는 `closed-native-v3`다. 정답 annotation/PPT/이전 검출 결과를 추론 입력으로 쓰지 않는다.

**알려진 반례의 수정과 유용한 부분 초안은 검증했지만, 무조건적인 프로덕션 승인은 아니다.** 복잡한 fork/점선/메모리 구조 누락, OCR 띄어쓰기 손실, 아직 부족한 사진·아이콘 분포, 실제 사용자 수정시간 측정이 남는다. `production_approved`는 false를 유지한다.

## 실제 사진과 PPT 정답쌍에서 확인한 것

- 실제 PPT→COM RGB32개를 독립 작업에서 fresh 실행했다. 이전20개와 caption12개는 고정 입력 SHA를 그대로 사용했다. runtime에는 RGB만 전달했다.
- 양성12개는44native도형/44nonblank owner/24native연결을 유지했다. 각 source의 Read–Build/Build–Check 두 연결이 실제 XML owner ID와 일치한다. nonblank44를 정확 문자열44로 부르지 않는다. 일부 parent 생략과 `Processoverview` 띄어쓰기 손실이 남는다.
- 음성사진20개는 shape/edge/picture0이며, 실제 COM PNG의 모든 pixel이255임을 확인했다. v2에서 발생한 caption9개 오출력은 차단됐다.
- 사진 원본은 china/flower2개다. 색상·caption 파생20개를 독립 사진20개나 일반화 성공률로 세지 않는다. 학습하지 않았고 기존 holdout을 열지 않았다.
- 소형 분류기 학습 실패는 그대로 보존하며 이 경로에 넣지 않았다. 기존 실제 PPT train336개에 picture 객체0개였던 데이터 편향도 별도로 기록했다.
- 독립 보고서: `r11_spatial_fresh_independent_audit.md`. worker artifact는 `C:/Users/lpaiu/.codex/worktrees/9cae/ImageToEditablePPT/artifacts/r11-spatial-fresh-v3`다.

## 복잡7개: 실제 native와 육안 확인

실행 core Git은 `a5f17cd`이며, 원본과 OCR/폰트·실행 코드 SHA는 각 lock에 있다. 산출물 `artifacts/region-image-only-r11/spatial-fresh-v3`; 실제 COM 비교와 감사 `spatial-fresh-v3-review`.

| 그림 | native 도형 | nonblank 라벨 | native 연결 | 최신 관측 |
|---|---:|---:|---:|---|
| reasoning-full |24|23|18|세로 Input/Encoder/Text Embedding이 올바른 방향으로 보인다. Mixture-of-Experts 글자와 분기6개/점선 일부는 누락.|
| blue-flow |6|6|4|주요 박스/직교 흐름은 남지만 우측 상단의 라벨 없는 박스와 연결1개가 추가 생략됨.|
| nested-panels |26|26|0|부모 제목/자식 분리 및 PDF 중복 제거 유지. 일부 모델/외곽 누락·LLMAPIs 띄어쓰기 손실 유지.|
| contrastive |22|22|1|실제 토큰/encoder/decoder 일부 유지. 전체 관계는 부족.|
| dark-transformer |7|5|2|실제 스택/임베딩과 일부 연결 유지. Add&Norm/skip 누락.|
| fusion |4|4|1|질문·POS·NER·RoBERTa 최소 초안. 중심 fusion/대부분 관계 누락.|
| original |7|7|2|원본의 큰 가짜 owner/중첩 라벨/열린 괄호 문제를 없앴다. 녹색 ACT와 SocialManager 및 연결2개는 추가 생략되어 원본 전체를 대체할 수준은 아님.|

합계96도형/93라벨/28연결/삽입이미지0이다. 이것은 출력 개수이며 정답률이 아니다. 이전 v2는99/94/31이었다. **정상 owner3개와 연결3개의 추가 생략**을 사진 오출력 차단의 비용으로 공개한다. 확실성 우선·부분 변환 허용 원칙에 따라 이 보수적 구성을 선택한다. 누락을 정답 복원으로 재분류하지 않는다.

blue/original 두 새 비교를 직접 육안으로 확인했다. 나머지5개의 실제 COM PNG는 직전 v2의 실제 COM PNG와 byte-identical이며, 그 화면들은 앞선 직접 육안 검사에서 확인했다. 모든7개 native XML 도형 bbox/텍스트/connector 양종점 및 입력→PPT→COM SHA 검사를 통과했다. 전체 hash는 review/audit.json에 있다.

## 구현의 핵심 구분

1. source proposal에는 실제 폐윤곽만 사용한다.1픽셀 허용은 원본 좌표 오차이며 bbox를 정답에 맞추는 최적화가 아니다.
2. parent 내부선을 보존하기 위해 tracing 중에만 경계 마스크 역할을 바꾼다. 최종 shape의 의미 역할·bbox는 바꾸지 않는다.
3. texture의 공간 변화와 두 주색 집중을 함께 관측한다. 신뢰할 수 있는 실제 후행 OCR word는 texture mask로만 사용하고, 완결된 출력 라벨 prefix에는 임의 추가하지 않는다.
4. 세로 글자는 원본 crop 양방향을 관측해 유일하게 승인된 방향만 쓰고 native text-frame을 회전한다. 도형 자체를 회전하거나 래스터로 대체하지 않는다.
5. 고립된 무라벨 경계는 남기지 않으며, texture의 no-veto를 일반 semantic 승인이라고 부르지 않는다.

## 아직 필요한 승인 근거

현재 자료로 확인하지 않은 사진/아이콘 유형의 안전성과 실제 사용자 수정시간은 미검증이다. 자동 COM에서 도형·텍스트를 바꾸고 연결 부착이 유지되는 것은 확인했지만, 이를 사람의 작업시간 감소로 대신하지 않는다. 기존 Phase16 operation calibration도 별도 실제 인간 측정 경계이며 그 동결 결과를 소급 변경하지 않았다.

따라서 이 산출물은 **검토 후 사용할 편집 가능한 부분 초안**이다. 원본 전체 복원, 새 holdout 통과, 실제 생산성 실측, production 완료라는 표현은 사용하지 않는다. 실제 사람이 PowerPoint에서 이 초안을 보완하는 시간과 처음부터 재작도하는 시간을 같은 작업 범위로 비교해야 사용자 시간 절약을 확정할 수 있다.
