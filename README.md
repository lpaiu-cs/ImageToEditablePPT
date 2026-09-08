# ImageToEditablePPT

이 저장소는 현재 **v3 아키텍처 재구성 중**이다. 목표는 논문용 구조적 다이어그램을 generic reconstruction이 아니라 **family-constrained parsing + editable primitive scene**으로 정규화하는 것이다.

## v0.2: 선택 영역을 native PPTX로 변환

실제 사용 진입점에 **명시적 ROI 변환**을 추가했다. 전체 그림에서 구조적 다이어그램
영역을 지정하면 보수적으로 박스·연결선·확신 가능한 텍스트를 추출한다. 별도 모델이나
PowerPoint 설치 없이 변환할 수 있고, 결과는 native shape/connector다. PowerPoint 설치는
실제 렌더 및 편집 검증을 실행할 때만 필요하다. 기존 기본 ML/v3 경로는 변경하지 않았다.

```bash
python -m pip install -e ".[ocr]"
image-to-editable-ppt-convert figure.png -o output/figure.pptx --region 0.1 0.2 0.9 0.8
# 전체 입력이 이미 잘라낸 구조적 다이어그램일 때
image-to-editable-ppt-convert diagram-crop.png -o output/crop.pptx --region 0 0 1 1
# OCR 없이 구조만; OCR 패키지가 없어도 이 경로는 동작한다
image-to-editable-ppt-convert diagram-crop.png -o output/structure.pptx --region 0 0 1 1 --no-ocr
```

`--region`은 원본 이미지 기준 `x0 y0 x1 y1`이며 각각 0~1이다. 같은 ROI가 배치의 모든
입력에 적용되므로 서로 다른 레이아웃은 개별 실행한다. 기존 `tools/convert_to_pptx.py`
래퍼나 `python -m image_to_editable_ppt.ml.convert_to_pptx`에서도 동일하게 사용할 수 있다.

- 결과 옆 `figure.region.json`에 출처 SHA, 선택 영역, 객체/연결선, 생략 사유와 한계를 기록한다.
  PPTX나 진단 파일이 이미 있으면 덮어쓰지 않는다. 재실행은 새 출력 이름을 사용한다.
- 입력 파일 최대 64MiB, 원본 최대 16MP, ROI 최대 4MP·최소 16×16px, 객체 후보 최대 300개다. 초과 시 명시적으로
  거절하며 조용히 입력을 축소하지 않는다. 출력만 긴 변 768 단위로 정규화한다.
  투명 배경은 흰색 위에 합성한다. 안전한 파일 게시는 같은 파일시스템의 hard-link 지원을 필요로 한다.
- 비도식/모호한 요소는 생략한다. 지원할 수 없는 연결 경로는 개별 생략하고 보고서에 남긴다.
- OCR은 같은 줄의 가로 순서를 정렬하고 두 배율 결과가 일치할 때만 내보낸다. 그래도
  공백/단어 오류가 남을 수 있다. 정확한 라벨이 중요한 경우 원본과 대조하거나 `--no-ocr`를 쓴다.
- 일반 이동·크기 변경·재열기에서 연결점 유지가 검증됐지만, 겹침을 자동 정리하지 않으며
  PowerPoint의 명시적 **연결선 다시 연결**은 부착 위치를 바꿀 수 있다.
- `--region`은 ML bundle/게이트를 자동 우회하는 옵션이 아니라 별도 명시적 영역 모드다.
  `--bundle`, `--allow-candidate-bundle`, `--no-gate`와 함께 쓸 수 없다. `--width`/모델 학습
  옵션은 기존 ML/v3 경로용이며 영역 분석 해상도를 바꾸지 않는다.

이는 **프로덕션 코드에 통합된 제한적 기능**이다. 사람의 ROI 지정 조건을 자동 영역 탐지
성능으로 세지 않는다. 기존 ML 모델의 candidate/NO-GO 판정, 독립 holdout 및 사람 편집시간
검증 경계는 유지한다. [연구 및 통합 결과](docs/region_native_production_results.md)를 참고한다.

현재 기준 문서는 [plan.md](plan.md)다. 큰 구조 판단, 현재 단계, 다음 단계, legacy 보존 정책은 모두 이 문서를 source of truth로 본다.

## 현재 상태

- **이미지 → 편집 가능한 .pptx 루프가 동작한다** (Phase 10~14).
  - ML provider(검출기 + family 분류기 + connector 추출기 + OOD 게이트) 또는 휴리스틱 경로로 구조를 복원하고, OCR로 텍스트를 복원해 native PowerPoint primitive로 emit한다.
  - writer/composition은 GT 구조를 사용한 oracle 실험에서 정확한 native object와 도형에 결속된 connector를 만들었다.
  - 고정 직교 흐름도 표본은 node/container/topology/direction F1 1.0, label 8/8, 편집 작업 하한 0까지 회복했고 PowerPoint 렌더도 육안 확인했다.
  - 휴리스틱 경로는 복잡한 실제형 입력에서 거짓 양성을 버리고 확실한 일부만 내보내지만, 아직 전체 구조를 복원하는 제품 품질은 아니다.
  - Phase 14에서 checksum-bound ML bundle과 고정 real benchmark/holdout을 실제로 끝까지 검증했다. 개발셋의 느슨한 개수 기준은 통과했지만 독립 holdout과 PowerPoint 육안 품질은 실사용 기준에 큰 폭으로 미달했다. 현재 모델은 연구용 `candidate`이며 실제 사용자용으로 추천하지 않는다. canonical 모델은 아직 없다.
  - Phase 15에서는 실제 원본/중간 overlay/PowerPoint 렌더를 반복 확인해, source-pixel-confirmed rectangle·ellipse·titled panel과 직접 축 connector만 보수적으로 복원하도록 바꿨다. 공개 diagram 5종과 알려진 비도식 오탐은 크게 개선됐지만 복잡한 `input.png`와 OCR은 여전히 육안 기준 미달이고 새 독립 holdout도 없으므로 candidate/NO-GO 상태는 변하지 않았다.
- old v2 runtime과 old CLI 동작은 의도적으로 제거되었다.
- 휴리스틱 경로의 지원 family는 아직 좁다(`orthogonal_flow`). ML 경로는 7 family를 다룬다.
- benchmark / eval / GT sidecar / workbench 자산은 보존되어 있다. old validation runtime은 복구하지 않았다.

## 현재 진입점

이미지 → 편집 가능한 .pptx:

```bash
python -m pip install -e ".[ml,ocr,test]"
py -3.12 tools/convert_to_pptx.py figure.png                 # -> figure.pptx
py -3.12 tools/convert_to_pptx.py figs/ -o out/              # 배치 변환
py -3.12 tools/convert_to_pptx.py figure.png --no-ml         # 휴리스틱 경로
py -3.12 tools/convert_to_pptx.py figure.png --bundle workbench-ml/model_bundle.candidate.json --allow-candidate-bundle
```

- `--bundle`은 checkpoint와 training/evidence artifact의 SHA-256을 검증한다. `workbench-ml/model_bundle.json`이 있으면 자동으로 사용한다.
- canonical이 아닌 bundle은 기본적으로 거절된다. 품질 미달이 확인된 실험용 candidate는 연구·진단 목적으로만 `--allow-candidate-bundle`을 명시해 실행할 수 있다.
- bundle/model 파일과 외부 benchmark 이미지는 저장소에 포함되지 않으므로 clean checkout만으로 Phase 14 결과를 재현할 수는 없다.
- gate checkpoint가 없으면 자동으로 gate를 끄지 않고 실패한다. 의도적으로 gate 없이 실행할 때만 `--no-gate`를 사용한다.
- OOD 게이트가 비다이어그램(차트/스크린샷/사진)을 거절하거나 결과에 primitive가 없으면 빈 pptx와 함께 `[EMPTY]`를 알린다.
- 학습 게이트를 통과했더라도 connector 대비 구조 객체가 지나치게 희박해 재작도량을 줄이지 못하는 결과는 빈 pptx로 기권한다. `--no-gate`는 이 유용성 관문도 끄는 명시적 진단 경로다.
- OCR 백엔드(rapidocr)가 없으면 텍스트만 비운 채 구조는 그대로 변환된다.
- 일반 OCR에서 놓친 흰색 라벨은 이미 검출된 닫힌 노드 내부에서만 다시 읽는다. 떠 있는 비-title OCR 텍스트는 출력하지 않는다.
- 배치 변환에서 서로 다른 입력이 같은 출력 파일명으로 정규화되면 덮어쓰지 않고 시작 전에 오류로 종료한다.

PPTX의 편집 가능성과 GT 대비 구조 오류를 측정하려면:

```bash
py -3.12 tools/evaluate_pptx_editability.py output.pptx
py -3.12 tools/evaluate_pptx_editability.py output.pptx --annotation figure.json --output editability.json
```

평가기와 기준선은 [docs/phase12_edit_cost_experiment.md](docs/phase12_edit_cost_experiment.md), canonical 승격 실험과 NO-GO 근거는 [docs/phase14_canonical_acceptance_experiment.md](docs/phase14_canonical_acceptance_experiment.md), visual-first 구현의 최종 육안 판정과 동결 경계는 [docs/phase15_visual_first_freeze.md](docs/phase15_visual_first_freeze.md)에 기록되어 있다.

개발용 inspection 경로 (v3 debug/inspection path):

```bash
python -m pip install -e .
python tools/run_v3_debug.py input.png --output-dir artifacts/v3_debug/sample
```

이 경로는 다음 artifact를 저장한다.

- `family_proposals.json`
- `diagram_instances.json`
- `connector_evidence.json`
- `primitive_scene.json`
- `attached_connectors.json`
- `solved_connectors.json`
- `emit_scene.json`
- `manifest.json`
- `eval_stage_artifacts.json`
- `emit_diff.json`
- `overlay_proposals.png`
- `overlay_instances.png`
- `overlay_connector_evidence.png`
- `overlay_ports.png`
- `overlay_primitives.png`
- `overlay_attached_connectors.png`
- `overlay_solved_connectors.png`
- `overlay_emit_scene.png`
- `overlay_emit_diff.png`
- `08_eval/*`
  - input 이미지 옆에 `*.gt.json` sidecar가 있으면 GT-backed eval artifact
  - 없으면 unavailable payload

파이썬에서 직접 v3 convert를 호출할 수도 있다.

```python
from image_to_editable_ppt.v3 import V3Config, convert_image

result = convert_image("input.png", config=V3Config())
print(result.slide_ir.family_proposals)
print(result.slide_ir.diagram_instances)
print(result.slide_ir.connectors)
print(result.slide_ir.primitive_scene)
```

## 현재 범위

현재 파이프라인은 아래 순서까지 구현되어 있다.

1. multiview branch 생성
2. text extraction + soft masking
3. raster/non-diagram split
4. residual structural canvas 생성
5. `orthogonal_flow` family detection
6. node/container parsing
7. connector evidence 수집
8. port 생성
9. evidence attachment
10. solved connector resolve
11. primitive scene mapping
12. image-space emit adapter scene mapping
13. eval adapter manifest/stage artifact 조립
14. emit pre/post diff inspection artifact 저장
15. debug/inspection artifact 저장

아직 하지 않은 것:

- old validation runtime 복구
- 휴리스틱 경로의 여러 family 동시 확장
- full connector routing/optimization
- relation 모델(run-rel8)의 provider 통합
- style token 본격 추출(현재는 대표 단색 샘플링만)

## 설계 원칙 요약

- 확실한 구조만 남기고, 애매한 것은 공백이나 residual로 둔다.
- non-diagram raster는 초기에 분리한다.
- connector는 evidence -> attachment-aware candidate -> solved connector 순서로 늦게 확정한다.
- emit adapter 좌표는 현재 `image-space`를 그대로 유지한다.
- preserve-eval bridge는 `manifest.json` + `08_eval/*` artifact를 읽는 최소 adapter로만 연결한다.
- detector 결과를 바로 emit하지 않고, typed IR과 primitive scene을 거친다.

상위 원칙은 [principle.md](principle.md)에 있다.

## 보존 자산

다음 자산은 보존 중이다.

- benchmark report / diagnostics artifact reader
- GT sidecar와 기존 benchmark summary
- workbench 산출물

하지만 이것이 old runtime이 여전히 동작한다는 뜻은 아니다. 현재는 **artifact reader는 유지, old conversion runtime은 제거** 상태다.

## 역사 문서

- [conversion-spec.md](conversion-spec.md): archived historical draft
- [v2.0 instruction.md](v2.0%20instruction.md): obsolete historical instruction

현재 구현 방향은 위 문서보다 [plan.md](plan.md)가 우선한다.
