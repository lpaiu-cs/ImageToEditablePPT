# ImageToEditablePPT

이 저장소는 현재 **v3 아키텍처 재구성 중**이다. 목표는 논문용 구조적 다이어그램을 generic reconstruction이 아니라 **family-constrained parsing + editable primitive scene**으로 정규화하는 것이다.

현재 기준 문서는 [plan.md](/Users/lpaiu/vs/ImageToEditablePPT/plan.md)다. 큰 구조 판단, 현재 단계, 다음 단계, legacy 보존 정책은 모두 이 문서를 source of truth로 본다.

## 현재 상태

- broad PPT export는 아직 복구하지 않았다.
- old v2 runtime과 old CLI 동작은 의도적으로 제거되었다.
- 현재 실제로 동작하는 경로는 **v3 debug/inspection path**다.
- 지원 family는 아직 좁다.
  - 현재 활성 family: `orthogonal_flow`
- benchmark / eval / GT sidecar / workbench 자산은 보존되어 있다.
- 다만 old validation runtime은 복구하지 않았고, eval adapter도 아직 구현하지 않았다.

## 현재 진입점

개발용 inspection 경로:

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
- overlay PNG들

파이썬에서 직접 v3 convert를 호출할 수도 있다.

```python
from image_to_editable_ppt.v3 import V3Config, convert_image

result = convert_image("input.png", config=V3Config())
print(result.slide_ir.family_proposals)
print(result.slide_ir.diagram_instances)
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
10. primitive scene mapping
11. debug/inspection artifact 저장

아직 하지 않은 것:

- broad PPT emit
- eval adapter
- old validation runtime 복구
- 여러 family 동시 확장
- full connector routing/optimization

## 설계 원칙 요약

- 확실한 구조만 남기고, 애매한 것은 공백이나 residual로 둔다.
- non-diagram raster는 초기에 분리한다.
- connector는 evidence -> attachment-aware candidate -> solved connector 순서로 늦게 확정한다.
- detector 결과를 바로 emit하지 않고, typed IR과 primitive scene을 거친다.

상위 원칙은 [principle.md](/Users/lpaiu/vs/ImageToEditablePPT/principle.md)에 있다.

## 보존 자산

다음 자산은 보존 중이다.

- benchmark report / diagnostics artifact reader
- GT sidecar와 기존 benchmark summary
- workbench 산출물

하지만 이것이 old runtime이 여전히 동작한다는 뜻은 아니다. 현재는 **artifact reader는 유지, old conversion runtime은 제거** 상태다.

## 역사 문서

- [conversion-spec.md](/Users/lpaiu/vs/ImageToEditablePPT/conversion-spec.md): archived historical draft
- [v2.0 instruction.md](/Users/lpaiu/vs/ImageToEditablePPT/v2.0%20instruction.md): obsolete historical instruction

현재 구현 방향은 위 문서보다 [plan.md](/Users/lpaiu/vs/ImageToEditablePPT/plan.md)가 우선한다.
