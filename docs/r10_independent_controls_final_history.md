# R10 독립 대조 이력

독립 도구만 작성했으며 공유 source_rays는 root에서 수정했다. 과거 기대값과 실패를 소급 변경하지 않았다. 모든 실행은 source 파일 복사 SHA와 최종 RGB/기대 manifest 잠금을 남긴다.

- `9a69fac`: Pillow RGB 990개(690 unique), 순서 반전 1,980판정. 최초 source `ec68322a...`에서 contact126/double24 음성 채택. 고유 RGB는 각각21/4개. 정상 기권42판정은 별도다.
- `7c888b0`, `83e124e`: raw stroke/owner 삭제 통합 대조. v2 336입력(246 unique RGB+bbox), 672판정. source `a48e61d...`에서 제3 owner 삭제로 raw 기권→채택18사례, glyph6사례. owner 내부 반대촉은 마스킹 전 bbox 외부 조사에서도 누락됐다.
- source `017a6611...`: raw 보존 및 정수 pixel-center 경계 계약에서 formal642/672. 정상·외부촉192/192 보존, 접촉/숨은촉 모두 기권. 남은30은 실제 mask효과 없는12와 깊이1px 이하 경계18. 현재 픽셀 손실 또는 방향 오류로 집계하지 않는다.
- `6c45baa`, `e669cec`, `bab814b`: 분리 CC 대조. 최종 RGB8CC를 추론 전 검증. v3 660RGB 중501개 유효, 순서 포함1,002판정. 나머지159RGB는 붙음 등으로 분리 전제가 무효이며 보존했다.
- source `f57bae3f...`에서 short_opposite414판정 채택. 명목 extension<=8인 유효462 중354도 채택되어 거리 제한 밖 사례로 설명되지 않았다. 양성 촉 검증 기준을 그대로 경쟁 촉 veto에 쓰면 짧은 촉을 놓쳤다.
- root 보고 최종 source `20d049de...`, commit `7853641`: 분리 대조 유효1,002판정의 모든 음성이 기권, clean4/nearby4 기존 기권만 유지. 이 마지막 실행은 root 보고이며 worker 독립 재실행으로 표기하지 않는다.

산출물은 `artifacts/r10-source-independent-*`, `artifacts/r10-source-mask-*`, `artifacts/r10-separated-*`에 있다. 전체15 성능·OCR·COM 결과는 root 트랙의 별도 기록이다. 이 문서는 제품 승인이나 보지 않은 데이터 일반화 근거가 아니다.
