# R10 통합 반례 이후 수정·직접 렌더 확인

## 괄호가 끊긴 원본 설명

`babdc96`에서 실제 OCR에 관측됐지만 괄호가 닫히지 않은 설명 suffix를 출력하지 않게 했다. 임의로 닫는 글자를 생성하지 않는다. 원본9도형/8라벨/4연결은 유지했고 `Sensory System`, `Generation Stack` 제목만 남았다. 두 설명은 texture 분석에서는 관측된 글자로 계속 제외한다. 실제 COM 렌더를 직접 확인했고 native 객체/입력/PPT/렌더 SHA 감사도 통과했다. 자료는 `artifacts/region-image-only-r10/closed-native-cli-original-v2`와 `closed-native-cli-original-v2-review`다. 일반 구조 누락은 여전히 많다.

## 세로 라벨 별도 실험

원본 reasoning의 RGB를 양방향 회전해 `Input`, `Encoder`, `Text Embedding`을 유일한 방향으로 읽었다. `Mixture-of-Experts`는 전체 행 재인식.98 미달로 기권했다. 원본 PNG와 세로 관측만으로 prototype native text-frame을 만들었다. 첫 실제 렌더에서 텍스트 교체 후 색상이 theme white로 초기화되는 결함을 육안으로 발견했고, 실제 도형 채움에 맞는 명시적 전경색을 지정한 v2 COM 렌더에서 세 라벨의 방향·위치·가시성을 확인했다.

자료는 `portrait-observations-v1`, `portrait-render-v1`(가시성 실패), `portrait-render-v2`다. frozen scene을 사용하는 **표현 prototype**이며 아직 새 RGB 통합 CLI 성공으로 세지 않는다.

사전 고정 glyph 대조군32개: 양성24중 정확 승인14, 기권10; 세로선/교차선/빈칸/한 글자씩 쌓인 문자는8개 모두 기권. 잘못 승인0이나 소규모 글꼴 대조군이지 실제 이미지 일반화 검증은 아니다. 자료 `portrait-controls-v1/manifest.json`, `results.json`. 같은 OCR 모델의 반복 관측을 독립 정답 증명으로 부르지 않는다.

## parent 전체 마스크와 자식 OCR 중복 수정

실패한 실제 COM 입력 두 개에 `--nested-owners`를 적용해 RGB만으로 다시 실행했다. `train-base0-native`와 `eval-base1-diagram_picture` 둘 다 native4도형/4라벨을 유지하면서 내부 연결이0→2개로 복원됐다. 후자의 parent 라벨에 붙었던 `Check`가 없어지고 실제 child 한 곳에만 남았다. 실제 COM 비교 두 장을 직접 봤고 native 객체/connector 양종점/입력과 렌더 SHA 감사도 통과했다. 자료는 `nested-owners-v1` 및 `nested-owners-v1-review`다.

이는 알려진 실패 두 개의 수정 증거다. `Process overview`의 띄어쓰기 손실(`Processoverview`)은 남는다. 모든 중첩 도식·사진을 해결했다거나 일반화 성능이 확보됐다고 결론내리지 않는다. 이어서 독립20개 통합 회귀와 기존 복잡7개를 검사한다.
