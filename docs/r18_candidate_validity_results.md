# R18 결과: 거부는 개선됐지만 온전한 구조 후보가 부족하다

2026-09-09. 실행 코드/명세 기준 `afcdc4d`, 사전등록 `e908829`. R17 동결 `bdaee50`과 제품 기본값은 유지한다.

## 판정

**설계한 네 조건의 학습·평가·실제 PowerPoint 렌더·육안 확인을 완료했다. 네 연구 gate 모두 실패이며 프로덕션 승격하지 않는다.**

유효성 거부는 합성 평가의 오탐을 크게 줄였다. 그러나 타일 추가로 확보한 후보가 최종 복원으로 이어지지 않았으며, 원래 복잡 CogBot 도식에서는 거부 후 아무것도 남지 않았다. 빈 결과의 FP0을 복원 성공으로 보고하지 않는다. 이는 1픽셀 허용오차 문제가 아니라 **온전한 객체의 대량 누락**이다.

## 실행과 평가 경계

- 독립 생성한 실제 source PPT72개를 COM640×400으로 렌더했다. train40장, calibration16장, eval16장이다. 닫힌 구조 GT는 각각200/75/75개이며 eval은 일반 노드72개와 부모 컨테이너3개다.
- train/cal은3×2 배치, eval은2×3 배치와 별도 어휘·seed다. 단순 무작위 장면 분리뿐 아니라 배치·종횡비 이동도 포함한다. 네 appearance family를 균등 배정했다. 데이터 정의·native XML·렌더 감사는 [데이터 감사](r18_structure_data_audit.md)에 있다.
- R16 점유 검출기와 R17 6종 분류기 및 종류 confidence .95는 고정했다. 기존 객체 CNN을 재사용하고 이진 유효성 head만 교체해 별도 모델을 학습했다. 제품 변환 파이프라인에는 연결하지 않았다.
- 학습 후보는 positive122개, negative1,060개였다. maxIoU≥.7/≤.2 사이 후보는 무시했다. 고정450steps 뒤 학습 positive/negative recall 모두1.0으로 실행 gate를 통과했다. 이는 학습 자료에서의 구분이지 일반화 성능이 아니다.
- 유효성 임계값은 종류를 무시한 calibration geometry로 full=.50, multiscale=.99를 선택했다. 각각 TP41/FP0/FN34, TP38/FP0/FN37이다. 두 선택을 저장한 후에만 eval을 열었다. 평가 후 임계값을 바꾸거나 arm을 버리지 않았다.
- GT bbox/preset/역할은 train label과 evaluator에만 사용했다. 별도 RGB-only predict 경로에서 eval-000의 네 arm 후보·출력이 평가 결과와 정확히 같았다. CogBot 예측에는 이미지와 고정 모델만 전달했으며 수동17노드 장부는 예측 후 진단에서만 읽었다.
- 이전 Phase16 formal holdout과 R16/R17 동결 결과는 건드리지 않았다. 이번 eval도 이제 노출된 동결 증거이며 후속 튜닝 뒤 독립 평가로 다시 주장할 수 없다.

## 새 합성 평가 결과

최종 TP는 종류 일치 및 bbox IoU≥.5 일대일 매칭이다. FP/FN은 잘못된 종류에도 동시에 발생할 수 있다.

| 조건 | TP | FP | FN | 정밀도 | 재현율 | negative FP |
|---|---:|---:|---:|---:|---:|---:|
| full_raw | 35 | 82 | 40 | 29.9% | 46.7% | 39 |
| full_valid | 33 | 1 | 42 | 97.1% | 44.0% | 0 |
| multiscale_raw | 37 | 464 | 38 | 7.4% | 49.3% | 196 |
| multiscale_valid | 31 | 0 | 44 | 100.0% | 41.3% | 0 |

거부 효과와 비용을 같이 읽어야 한다. full은 FP82→1 대신 TP35→33, multiscale은 FP464→0 대신 TP37→31이다. 연구 gate는 정밀도1, 재현율≥.8, 구조 family별 재현율≥.5, negative FP0, calibration 통과다. 모든 arm이 재현율 기준에 미달한다. 별도 인간 편집 시간 개선도 측정하지 않았다.

### 누락이 생기는 단계

아래 TP는 마지막 열을 제외하고 **종류를 무시한 geometry**다. 원래 후보는 full165개, multiscale570개다.

| 조건 | 모든 후보 TP / 추가 후보 FP | 유효성 통과 TP / FP | 종류 confidence 통과 후 geometry TP | 최종 종류+geometry TP |
|---|---:|---:|---:|---:|
| full_raw | 45 / 120 | 45 / 120 | 37 | 35 |
| full_valid | 45 / 120 | 42 / 0 | 34 | 33 |
| multiscale_raw | 56 / 514 | 56 / 514 | 42 | 37 |
| multiscale_valid | 56 / 514 | 40 / 0 | 31 | 31 |

타일은 후보 재현율을60.0%→74.7%로 올리지만, 추가 후보 FP도120→514로 늘린다. 이 후보 집합과 현재 매칭 기준에서는 종류·거부가 완벽해도 재현율 상한이74.7%라서 연구 목표80%에 못 미친다. 이는 모든 후속 후보 모델의 상한을 뜻하지 않는다.

full_valid의 유효성 geometry FP0과 최종 FP1은 모순이 아니다. 위치가 맞는 ellipse를 diamond로 분류한 사례(eval-002)가 남았다. 따라서 닫힌 구조인지 판정하는 문제와 어떤 도형인지 판정하는 문제는 별개다. 종류 confidence도 추가 누락을 만든다.

### appearance와 부모 객체를 분리한 결과

| family | GT | 후보 TP full → multi | 최종 TP full_raw → full_valid | 최종 TP multi_raw → multi_valid |
|---|---:|---:|---:|---:|
| 유색 채움 / 흰 배경 | 18 | 18 → 18 | 15 → 15 | 15 → 14 |
| 흰 카드 / 색 배경 | 18 | 1 → 8 | 0 → 0 | 1 → 0 |
| noFill 윤곽 / 흰 배경 | 18 | 8 → 12 | 4 → 2 | 5 → 1 |
| 중첩 컨테이너 포함 | 21 | 18 → 18 | 16 → 16 | 16 → 16 |

중첩 family의18개 후보 TP는 모두 자식 노드다. **부모 컨테이너3개는 full/multi 모두 후보0/3, 최종0/3이다.** 자식이 잘 잡힌다는 수치로 부모 복원을 주장하면 안 된다. 일반 노드만 보면 후보45/72→56/72, valid 최종 종류+geometry33/72→31/72다.

6종별 최종 TP/FN은 다음과 같다. rounded rectangle의 GT15에는 부모3개가 포함된다. 모든 최종 FP는 diamond 분류에서 발생했다.

| 종류 | full_raw | full_valid | multi_raw | multi_valid |
|---|---:|---:|---:|---:|
| rectangle | 3/9 | 3/9 | 3/9 | 3/9 |
| rounded rectangle | 4/11 | 4/11 | 4/11 | 4/11 |
| ellipse | 6/6 | 6/6 | 6/6 | 6/6 |
| diamond | 8/4 | 6/6 | 9/3 | 6/6 |
| parallelogram | 8/4 | 8/4 | 9/3 | 7/5 |
| cylinder | 6/6 | 6/6 | 6/6 | 5/7 |

## 실제 PowerPoint 육안 확인

eval16장×4조건=64PPT를 실제 COM으로 렌더했다. native 도형683개, source/result/receipt SHA를 검사했다. **16개 비교판 전부를 직접 열었다.**

- 유색 장면(eval-000/004/008)은 비교적 온전한 단순 도형이 남지만 각 장면에서 적어도 하나의 노드가 빠졌다. multi_valid는000에서 cylinder도 더 잃었다.
- 흰 카드 장면(001/005/009)은 raw에서 거대한 마름모·작은 글자 조각이 나타나며, valid에서는 완전히 빈 슬라이드다. 색 배경이 사라지는 것은 범위상 허용되지만 흰 구조 노드까지 없어지는 것은 유용한 부분 복원이 아니다.
- 윤곽 장면(002/006/010)은 글자/배너를 도형으로 오인하고 실제 노드를 놓친다. full_valid의002에는 ellipse 위치에 diamond가 남는다. multi_valid는002에서 parallelogram 하나만 남고006/010은 비어 있다.
- 중첩 장면(003/007/011)은 자식 일부가 남지만 바깥 rounded container는 모두 사라졌다. 007은 자식6개가 맞아도 부모와 구획 관계는 복원되지 않았다.
- negative4장은 raw에서 문단/열린 선/장식을 작은 마름모로 잘못 출력한다. valid4장은 빈 결과다. 이는 이번 **닫힌 객체** 과제에서의 정상 거부이며, 도식의 열린 선이나 구조 라벨을 영구적으로 무의미하다고 판정한 것이 아니다.

비교판은 `artifacts/region-image-only-r18/com-v1/r18-*-eval-*.png`다. 연구 출력은 의도적으로 noFill native preset이고 OCR·연결·원본 fill을 구현하지 않았다. 색·텍스트가 없다는 점은 범위 제한으로 별도 기록하지만, 실제 노드 누락까지 범위 제한으로 면제하지 않는다. 개별 native auto-shape임은 XML로 확인했으며 사람이 실제로 수정하는 작업 시간은 아직 검증하지 않았다.

## 복잡 원본: 거부 후 완전 공백

formal 결과 동결 뒤 원래 CogBot RGB2760×1504를 그대로 입력했다. 네 PPT를 COM1380×752로 렌더하고 원본 비교판 및 full34개/multi132개 후보 crop을 직접 보았다.

| 조건 | 후보 수 | 수동17노드 기준 후보 geometry TP | 최종 native 객체 수 | 육안 판정 |
|---|---:|---:|---:|---|
| full_raw | 34 | 2 | 24 | 모두 잘못된 diamond |
| full_valid | 34 | 2 | 0 | 전부 거부, 복원 없음 |
| multiscale_raw | 132 | 3 | 99 | 모두 잘못된 diamond |
| multiscale_valid | 132 | 3 | 0 | 전부 거부, 복원 없음 |

valid에서는 종류 confidence를 적용하기 전부터 유효성 통과 후보가0개다. raw 최종 결과의 종류 무시 geometry TP는 각각1/2지만 실제 원본 노드의 종류는 diamond가 아니므로 이를 올바른 복원으로 셀 수 없다. 수동 장부는 이미 노출된 개발 자료이며 독립 GT가 아니다.

후보 crop에서 실제 테두리 전체보다 글자·아이콘·서로 다른 객체를 포함한 큰 조각이 잡히는 것을 확인했다. 타일은 글자 단위 조각을 더 많이 만든다. 원본의 배경·흰 카드·겹치는 컨테이너·촘촘한 연결/문단은 합성 단순 도형과 다르다. **분류기 뒤에 거부 모델만 추가해서는 이미 사라진 객체를 되살릴 수 없다.**

원본 비교: [실제 COM 비교판](../artifacts/region-image-only-r18/audit-v1/original-comparison.png). 후보: [full](../artifacts/region-image-only-r18/audit-v1/full-candidate-crops.png), [multiscale](../artifacts/region-image-only-r18/audit-v1/multiscale-candidate-crops.png).

## 원인과 후속 우선순위

1. **확인된 병목은 후보 객체성이다.** 유색 채움에는 강하고 흰 카드·윤곽·부모에는 약하다. 다음에는 이 appearance들을 포함한 source PPT 객체 supervision으로 온전한 bbox/경계를 직접 학습하는 후보 단계를 먼저 검증해야 한다. union occupancy만으로 부모/자식을 한 덩어리로 축약하지 않는다.
2. **해상도만 높이는 방향은 현재 충분하지 않다.** 후보 TP11개 증가에 추가 FP394개가 붙었다. 현재4타일과 .99 거부를 기본값으로 채택하지 않는다. 타일 개수/임계값을 이 eval에 맞춰 추가 탐색하지 않는다.
3. **종류 일반화도 별도 실패다.** 위치가 맞아도 기존6종 분류기가 새 appearance를 diamond로 오인하거나 confidence로 버린다. 다음에는 후보 개선과 종류 모델 변경을 분리해 어떤 단계가 이득을 냈는지 확인해야 한다.
4. **새 학습 전에 표적을 정한다.** 흰 카드/윤곽/부모별 후보 재현율과 비용을 우선 지표로 두고, 이 R18 자료는 개발 진단으로만 재사용한다. 새 독립 source seed/배치의 미개봉 평가와 사전등록이 필요하다. OCR·fill·연결을 먼저 얹는 것으로 닫힌 객체 누락을 가리지 않는다.

위는 후속 설계 입력이지 이번에 검증한 새 모델의 성공 주장이 아니다. 현재 자료는 장면family당eval3개뿐이고 native 장식/영문 텍스트 중심이다. 배너 사각형을 decoration으로 둔 역할 계약도 합성 생성기의 규약이지 모든 논문 도식의 보편 규칙이 아니다. 실제 사진·로고·한국어·조밀한 배치 전반의 일반화는 확보하지 않았다.

## 검증과 재현

R16/R17/R18 관련 테스트8개 통과. 제외 없는 전체 회귀는 **1407 passed / 6 failed / 2 xfailed**다. 실패는 기존 `test_source_centerline.py::test_clean_source_lines`의 .75 horizontal/vertical 각 reverse 두 경우와1.5 reverse-diagonal 두 경우다. R17 기록과 같은6개이며 해당 구현/허용오차는 바꾸지 않았다. 전체 녹색이라고 보고하지 않는다.

평가 lock의 코드/명세/입력/checkpoint SHA를 실행 뒤 다시 확인했다. 별도RGB-only 동일성,64개 평가PPT와4개 원본PPT의 실제 COM receipt, native shape, 비교판 SHA를 검사했다. COM 슬롯을 반환했다. ponytail 원칙에 따라 기존 crop/CNN/PPT/COM/평가 helper를 재사용했으며 새 의존성이나 제품 설정은 추가하지 않았다.

재현 도구는 `tools/r18_candidate_validity.py`의 prepare→train→evaluate→predict, `tools/r18_visual_audit.py`의 prepare→COM renderer→review, `tools/r18_result_audit.py`다. 모든 실행은 새 출력 디렉터리를 사용한다. 최종 감사 도구는 이미 생성된 `eval-v1`, `com-v1`, `original-v1`, `original-com-v1`, `rgb-only-v1`을 읽고 SHA/동일성 assert 후 감사 결과를 저장한다.

데이터 manifest는 `C:/Users/lpaiu/.codex/worktrees/9cae/ImageToEditablePPT/artifacts/r18-structure-data-v1/dataset_manifest.json`, SHA256은 `75a52efe4165de6c3a6605eb040eacbb348709c410110f099d980cc5e47d60ec`다. 원본 데이터가 별도 작업의 artifact에 있으므로 그 경로를 보존해야 재현 가능하다. 대용량 artifact는 Git 추적 대상이 아니며 문서 커밋만으로 모델/렌더가 원격에 보관되는 것은 아니다.

아래 증거는 `C:/vs/ImageToEditablePPT/artifacts/region-image-only-r18/` 아래에 있다.

| 증거 | SHA256 |
|---|---|
| prepared-v1/prepared.json | a98af201a4c05fd88dd0786d1e707731af36d78e8409a327198ad6a29e1abd94 |
| training-v1/training.json | 37d04d3457e90a5279053680d88ba8586f7eb8b5cfe028dc9a3c954ca106f9b1 |
| training-v1/validity.pt | b33985754ffe0a15bc9546c1c75df0f8fa5187d273d441ba22b9a418054ef998 |
| eval-v1/results.json | c5b279d560fa105cde0768634934a338ef2c7f59cabc1aa82d5299cfa9335b1c |
| eval-v1/calibration.json | e74a57df31f31b51bfab64170300d9465d4a3777e08b33802c944f03b5446480 |
| eval-v1/lock.json | d1e4c7c547793f327ad4b8b3c2f53f28d266029927fcef3e37e2a73d8527f61d |
| com-v1/audit.json | 8e32cc7bd917fc5d5030d15c4073fd90a148f2c51279db56cd9917a6e5712a3f |
| audit-v1/audit.json | e34964011016b9160db36c3f53f091c80c8063146d4f6e6cf2410cc75b0954eb |
| original-v1/result.json | 100e3e0ad96b725d96bdf04b728bf1bd3d4b1b29388fc60a2a1fc12d688aa0b7 |
| rgb-only-v1/result.json | 1eb9044690724b0a71e14b7a9587ed243fca80a26a89634e401f44162cc70eb0 |
| regression-v1.xml | 8cd176550ee845f2913098c328a98f3e392e021a5f0951e60efb54f0fac37f11 |
