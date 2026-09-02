# Phase 16 baseline reproduction and visual audit

작성일: 2026-09-02

상태: **Phase 16.0 diagnostic baseline frozen; not a Phase 16 candidate result**

정본 manifest: `benchmarks/phase16_baseline_v1.json`

## 1. 재현 경계

- 코드: Phase 15 Git `3ae7caf2c6160bd84e4bc851212b22c536cb3348`
- candidate bundle SHA-256: `d9d232c44eed893e7c63baa30059f1728da9946077467d2d2e6a664f740023ac`
- 실행 코드: 현재 worktree가 아니라 위 commit의 detached worktree
- 렌더러: Microsoft PowerPoint desktop `16.0`, 폭 `1200px`
- 공식 표본: Phase 16 dev 40개 + holdout 24개

저장소 `input.png`를 다시 만든 PPTX는 Phase 15 동결 PPTX와 canonical editable semantics가 일치했다. 두 PPTX를 PowerPoint에서 다시 렌더한 PNG도 SHA-256 `b046a1751513a236d3d5e08dd664c00f1d3ace40cc0876086922eaaeac5bf5eb`로 픽셀 단위 일치했다. 따라서 아래 차이는 baseline 재생성 drift가 아니라 새 표본에서 드러난 기존 방법의 성능이다.

## 2. 공식 baseline 수치

| split | kind | sample | blank | nonblank | native object | semantic connector |
|---|---|---:|---:|---:|---:|---:|
| dev | diagram | 20 | 9 | 11 | 139 | 36 |
| dev | non-diagram | 20 | 19 | 1 | 14 | 3 |
| holdout | diagram | 12 | 5 | 7 | 95 | 29 |
| holdout | non-diagram | 12 | 12 | 0 | 0 | 0 |

다이어그램 32개 중 14개가 완전히 blank다. nonblank라는 사실도 성공을 뜻하지 않는다. 아래 육안 검토에서 여러 결과가 핵심 relation과 hierarchy를 잃었다.

## 3. 전 표본 PowerPoint 렌더 육안 검토

64개 모두 source와 Phase 15 PowerPoint 렌더를 같은 크기로 나란히 놓은 16개 접촉시트에서 직접 확인했다.

관찰된 성공 경계:

- `phase16-dev-p006`, `p011`, `p015`, `p050`, `p059`, `p124`와 holdout의 일부 단순 흐름은 핵심 박스의 상당 부분을 editable object로 남겼다.
- 이 경우에도 dotted/branch/elbow relation, decision shape, container hierarchy, 작은 label은 자주 사라졌다.
- 따라서 가장 좋은 결과도 완성 복원이 아니라 제한적인 수정 출발점이다.

주요 실패:

- **과도한 기권**: 명확한 rectangular diagram인 dev `p020`, `p043`, `p058`, `p067`, `p073`, `p086`, `p089`, `p092`, `p119`와 holdout `p016`, `p076`, `p121`, `p131`, `p135`가 blank다.
- **topology 소실**: `p008`, `p042`, `p056`, `p083`, `p109`, `p123`은 box 일부를 남겨도 branching, endpoint, route 또는 핵심 후속 node를 잃어 relation 재작도가 많이 남는다.
- **오도하는 구조**: dev `p034`는 실제 group 경계를 따르지 않는 큰 rounded region과 잘못 단순화한 connector를 만들어 삭제·재작도가 필요하다.
- **비다이어그램 거짓 양성**: dev `p063`은 mixed pathology figure의 image tile을 네 개의 구조 box로 만들고 전체 14개 native object를 emit했다. 프로젝트의 보수적 공백 원칙을 위반한다.
- **label 손상**: OCR은 `D LM`, 잘린 단어, 잘못 합쳐진 문자열을 만들고, 복잡 표본에서는 정확한 label 대부분을 비운다.

## 4. 해석

Phase 15는 간단하고 대비가 높은 직렬 orthogonal flow의 보수적 부분복원에는 쓸 수 있다. 그러나 새 분포에서는 다음 두 실패가 동시에 존재한다.

1. 정당한 nested/connector-dense diagram을 대량으로 blank 처리하는 recall failure
2. raster tile 또는 잘못된 대형 region을 구조로 내보내는 precision failure

즉, 단일 global geometry threshold와 connector-density abstention을 더 조정하는 것으로는 두 방향을 함께 해결하기 어렵다. 이 결과는 Phase 16 MEG의 필요성을 지지하지만 그 성공을 증명하지는 않는다.

## 5. 실험 보존 규칙

- 이 검토는 baseline 진단이며 confirmatory A/B 점수가 아니다.
- Phase 16 candidate 결과는 아직 생성하지 않았다.
- holdout candidate output을 보기 전 dev gate와 setting을 동결해야 한다.
- 실제 사람의 PowerPoint operation calibration이 완료되어 experiment lock이 `frozen`이 되기 전에는 MEG tuning을 시작하지 않는다.
