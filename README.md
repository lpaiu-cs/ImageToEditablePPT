# ImageToEditablePPT

## 프로젝트 종료 — 2026-09-09

**사용자 결정으로 연구·개발을 종료한다. 목표 달성이나 범용 프로덕션 승격을 의미하지 않는다.**

원래 목표는 이미지의 구조적 다이어그램을 편집 가능한 PowerPoint로 바꿔 사용자의 재작도·수정 시간을 줄이는 것이었다.
native 도형 출력, 제한적 ROI 부분 복원, PPT→스크린샷 정답쌍과 개별 객체 학습에서는 성과가 있었지만,
복잡한 실제 도식의 육안 품질은 충분히 일반화되지 않았다.

마감의 핵심 사유는 **범용 멀티모달 AI에 PPT 편집 도구/MCP를 제공하는 단순한 대안 대비,
전용 시스템의 품질·비용·실제 사용자 수정 시간에서 추가 가치를 입증하지 못했다**는 것이다.
그 기준선과 사용자 편익을 확인하지 않은 채 전용 파이프라인을 계속 확장할 투자 근거가 부족하다고 판단했다.
AI + PPT MCP의 우위를 실험으로 증명한 것은 아니며, 해당 대안과의 정식 비교는 수행하지 않았다.
기술적 불가능성의 증명이 아니라 추가 가치가 입증되지 않은 연구의 종료 결정이다.

### 최종 상태와 보존 위치

- [최종 연구 정리·코드·보고서](https://github.com/lpaiu-cs/ImageToEditablePPT/tree/codex/source-evidence-r9)는 `codex/source-evidence-r9`에 보존한다.
- [별도 데이터 작업 이력](https://github.com/lpaiu-cs/ImageToEditablePPT/tree/codex/ml-image-only-pilot)은 `codex/ml-image-only-pilot`에 보존한다.
- R19의 합성 eval은 TP316/FP5/FN2였으나, 원본 주요 17노드 사후 진단은 TP1/FP8/FN16으로 육안 기준 미달이었다. 두 집단을 섞어 일반화 성능이라고 부르지 않는다.
- R20–R21의 문맥·해상도 진단도 실제 사용 가능한 복원으로 이어지지 않았다. 최신 완료 실험은 [R21 결과](https://github.com/lpaiu-cs/ImageToEditablePPT/blob/codex/source-evidence-r9/docs/r21_resolution_probe_results.md)다.
- R22는 설계·코드·native 외형 쌍 384개 생성과 감사까지만 완료됐다. **GPU 학습·모델 평가는 미실행 상태로 취소했으며 성능 결과가 없다.**
- 사람의 실제 수정 시간 절감과 범용 AI 대안 대비 우위는 검증하지 못했다. 기존 실패·동결 판정은 보존한다.
- 대용량 데이터·checkpoint·생성 PPT/PNG·가상환경은 기존 Git 제외 정책에 따라 로컬에 남는다. 코드·문서 푸시는 이 산출물의 원격 백업이 아니다.

`main`에는 종료 안내만 반영하며 연구 코드를 제품 릴리스로 병합하지 않는다.
아래 사용법과 과거 문서의 “진행 중”, “다음 단계”는 역사 기록이며 추가 실행 지시가 아니다.

<details>
<summary>종료 이전 main 브랜치 기록 (현행 개발 계획 아님)</summary>

이 저장소는 현재 **v3 아키텍처 재구성 중**이다. 목표는 논문용 구조적 다이어그램을 generic reconstruction이 아니라 **family-constrained parsing + editable primitive scene**으로 정규화하는 것이다.

현재 기준 문서는 [plan.md](plan.md)다. 큰 구조 판단, 현재 단계, 다음 단계, legacy 보존 정책은 모두 이 문서를 source of truth로 본다.

## 현재 상태

- broad PPT export는 아직 복구하지 않았다.
- old v2 runtime과 old CLI 동작은 의도적으로 제거되었다.
- 현재 실제로 동작하는 경로는 **v3 debug/inspection path**다.
- 지원 family는 아직 좁다.
  - 현재 활성 family: `orthogonal_flow`
- benchmark / eval / GT sidecar / workbench 자산은 보존되어 있다.
- 다만 old validation runtime은 복구하지 않았다.
- 대신 debug path에서 읽는 최소 `eval_runtime` adapter와 emit diff inspection bootstrap은 추가되었다.

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

- broad PPT emit
- old validation runtime 복구
- 여러 family 동시 확장
- full connector routing/optimization

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

</details>
