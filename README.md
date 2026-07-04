# ImageToEditablePPT

이 저장소는 현재 **v3 아키텍처 재구성 중**이다. 목표는 논문용 구조적 다이어그램을 generic reconstruction이 아니라 **family-constrained parsing + editable primitive scene**으로 정규화하는 것이다.

현재 기준 문서는 [plan.md](plan.md)다. 큰 구조 판단, 현재 단계, 다음 단계, legacy 보존 정책은 모두 이 문서를 source of truth로 본다.

## 현재 상태

- **이미지 → 편집 가능한 .pptx 루프가 동작한다** (Phase 10).
  - ML provider(검출기 + family 분류기 + connector segmenter + OOD 게이트) 또는 휴리스틱 경로로 구조를 복원하고, OCR로 텍스트를 복원해 native PowerPoint primitive로 emit한다.
- old v2 runtime과 old CLI 동작은 의도적으로 제거되었다.
- 휴리스틱 경로의 지원 family는 아직 좁다(`orthogonal_flow`). ML 경로는 7 family를 다룬다.
- benchmark / eval / GT sidecar / workbench 자산은 보존되어 있다. old validation runtime은 복구하지 않았다.

## 현재 진입점

이미지 → 편집 가능한 .pptx:

```bash
python -m pip install -e ".[ml,ocr]"
py -3.12 tools/convert_to_pptx.py figure.png                 # -> figure.pptx
py -3.12 tools/convert_to_pptx.py figs/ -o out/              # 배치 변환
py -3.12 tools/convert_to_pptx.py figure.png --no-ml         # 휴리스틱 경로
```

- canonical 체크포인트는 기본적으로 `workbench-ml/run-*/checkpoints/last.ckpt`에서 찾는다 (`--models-dir` 또는 `IEP_MODELS_DIR`로 변경).
- OOD 게이트가 비다이어그램(차트/스크린샷/사진)을 거절하면 빈 pptx와 함께 `[EMPTY]`를 알린다 (`--no-gate`로 강제 변환).
- OCR 백엔드(rapidocr)가 없으면 텍스트만 비운 채 구조는 그대로 변환된다.

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
