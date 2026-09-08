# 차기 학습 target 계약: 역할과 렌더 도형의 분리

## 읽기 전용 감사 결론

기존 validation의 `graph_1302_00029`와 `graph_1302_00063`을 확인했다.
두 원본 PPT의 노드 **11개 전부 `a:prstGeom="ellipse"`**인데 annotation kind는
**11개 전부 `box`**다. 기존 corrected baseline의 선택 예측도 각각 box 5/6개다.
현행 kind+IoU 평가에서는 TP11/FP0/FN0으로 기록되지만, 이는 실제 렌더 도형 종류의
정확도를 입증하지 않는다.

| 원본 | PPT ellipse | annotation box | 불일치 | 기존 노드 TP/FP/FN |
|---|---:|---:|---:|---|
| graph_1302_00029 | 5 | 5 | 5 | 5/0/0 |
| graph_1302_00063 | 6 | 6 | 6 | 6/0/0 |

annotation ID와 source PPT `cNvPr.name`이 일대일로 대응하는 것을 이용해 실제 노드를
짝지었다. PPT slide 크기는 6096000×3429000 EMU, PNG는 640×360이다.
slide→pixel 변환 후 annotation/PPT bbox의 최대 차이는 약 **0.0001271px**다.
11개 모두 rotation/flip이 없다. 따라서 이 두 사례에서는 좌표 정답이 어긋난 것이 아니라
도형 종류가 annotation과 별개의 style 경로에 남아 있는 것이 문제다.

측정한 shape ID·preset·bbox·label·파일 SHA는
`benchmarks/rendered_geometry_target_audit_v1.json`에 기록했다.
원본 PPT SHA:

- 00029: `4f4126121205398c7c8cadb4d7fabbbd3f1a8d76b4f952244a9c2d8204686685`
- 00063: `54843426353167f7ede2bf746c4012843dba7029a27a7bf6ad490a13ca51afb2`

이 검토는 source PPT/annotation과 **이미 저장된** 예측/점수를 읽었다.
추론 입력에 GT를 넣지 않았고 학습·재추론·COM 실행을 하지 않았다.
두 그림은 이미 본 validation 사례다. 미관측 평가 집합으로 재명명하지 않는다.

## 코드에서 확인한 target 손실

현재 `ml/synthesize.py`의 graph 생성 경로:

1. `:1172`가 `SyntheticNodeStyle.shape`를 ellipse/round/rect 중 선택한다.
2. `:1199`의 `AnnotationNode.kind`는 항상 `NodeKind.BOX`다.
3. `:1607-1610`의 `_resolve_shape`는 명시적 style.shape를 우선한다.
4. `:1724` 이후 PPT writer는 shape_name=ellipse이면 `MSO_SHAPE.OVAL`을 만든다.
5. `ml/dataset.py:132-138`은 annotation의 kind를 label로 바꾸며 실제 PPT preset을 읽지 않는다.

즉, 현재 학습 경로는 graph의 원형 node 이미지를 box label로 감독할 수 있다.
단순히 enum에 ellipse 항목을 추가해도 생성 target 자체가 box이면 해결되지 않는다.
이번 감사만으로 모든 graph 또는 다른 family의 오표기 비율을 추정하지 않는다.

## 기존 결과의 보존

기존 데이터·manifest·annotation·checkpoint·enum·제품 loader를 고치지 않는다.
R5 승인과 R6/R7/Phase16 동결 판정, v1 점수와 v2 handoff는 그대로 보존한다.
현행 TP11은 **기존 annotation 계약에서의 TP**라는 의미로 유지하고, 별도 geometry
감사에서 source preset과 11/11 불일치라고 기록한다. 기존 결과를 소급 덮어쓰지 않는다.

v2 handoff의 `semantic_kind=box`는 legacy annotation 명칭이다. 실제 native geometry가
rectangle임을 독립 입증한 필드가 아니다. 후속 통합에서 이 한계를 숨기지 않아야 한다.

## 차기 target의 두 채널

다음은 **설계 제안**이며 아직 구현·승인·학습하지 않았다.

### 역할 채널

`semantic_role`은 구조에서의 역할을 담는다. 처음에는 node/container/excluded/unknown
정도로 제한하고, source를 함께 저장한다. label_anchor는 새로운 기능적 의미를
추측하기보다 `semantic_role=node`, `rendered_geometry=text_only`처럼 표현할 수 있다.
이 대응 역시 데이터 정의와 리뷰를 통해 확정해야 한다.

source PPT의 ellipse/rectangle만 보고 node 역할을 자동 부여하지 않는다.
사진·로고·차트 marker·장식도 같은 native preset으로 만들 수 있다. 합성 자료는
검증된 generator 객체 역할을, 일반 PPT는 별도 구조 역할 annotation을 사용한다.
역할을 모르면 unknown 또는 loss mask로 두며 임의 구조 정답을 만들지 않는다.

### 렌더 도형 채널

`rendered_geometry`는 실제 작성된 native geometry를 별도로 담는다.
최초 범위는 rect/round_rect/ellipse/text_only와 unsupported/unknown을 제안한다.
line/connector는 독립 관계·경로 target으로 다룬다. 미지원 preset을 box로 바꾸지 않는다.

source PPT에서 `prstGeom`, geometry 조정값, xfrm, line/fill visibility, 그룹 변환,
슬라이드 clipping 등을 추출하고 raw 값을 보존한다. parser가 해석하지 못하는 custGeom,
효과/그룹/변환은 unsupported 사유와 supervision mask를 남긴다.
회전한 shape의 axis-aligned bbox와 실제 preset 종류는 다른 필드로 유지한다.

예시(향후 schema 초안):

```json
{
  "target_schema_version": "role_render_geometry_vnext_draft",
  "object_id": "source-ppt-sha:slide1:shape4",
  "semantic_role": {
    "value": "node",
    "source": "reviewed_generator_role",
    "supervise": true
  },
  "rendered_geometry": {
    "value": "ellipse",
    "source_prstGeom": "ellipse",
    "source": "source_ppt_xml",
    "supervise": true
  },
  "legacy_annotation_kind": "box",
  "coordinate_system": "rendered_rgb_pixels",
  "visibility": "reviewed_visible",
  "source_object_ref": {
    "slide_part": "ppt/slides/slide1.xml",
    "shape_id": "4"
  }
}
```

이 예시는 역할 출처와 source geometry 출처의 분리를 보여 주며, 실제 학습 manifest로
사용하기 전 bbox·RGB/PPT/code SHA·변환 및 가시성 근거 등의 필수 필드를 고정해야 한다.
legacy kind는 감사용으로 보관하며 새 geometry label에 자동 복사하지 않는다.

## 원본 PPT에서 target을 추출하는 경계

1. 원본 PPT bytes SHA와 slide/shape ID/그룹 ancestry로 source 객체 key를 만든다.
   shape name은 중복될 수 있으므로 일반적인 고유 key로 의존하지 않는다.
   이번 두 자료에서만 generator 이름과 annotation ID의 일대일 대응을 검증했다.
2. source XML의 raw geometry와 style visibility를 읽고, 검증된 native 범위만 해석한다.
   장식/비다이어그램 여부는 별도의 역할 채널에서 결정한다.
3. 그룹/회전/flip을 합성한 slide 변환 및 실제 render crop/scale로 pixel 좌표를 만든다.
   동일 source를 렌더한 PNG와 좌표를 확인하고 변환 정보·renderer/version/options를 남긴다.
4. 작성된 source geometry와 실제 RGB에서 관측 가능한 geometry를 구분한다.
   숨김·완전 가림·근거 부족 객체는 visible detection loss에 넣지 않는다.
   가려진 구조의 복원을 감독하려면 어떤 관측 근거가 충분한지 별도 규칙과 label이 필요하다.
5. 기존 파일 옆을 덮어쓰지 않고 새 version의 target/manifest를 만든다.
   원본 SHA·target 추출 code SHA·schema SHA·review 상태를 기록한다.

PPT는 이 **offline target 생성 및 평가 비교** 과정에서만 접근한다.
실제 inference는 RGB와 고정 모델/설정만 받고, source preset·역할·bbox·mask·라벨을
주입받지 않는다. 새 schema에서도 handoff의 파일 접근 검사와 GT 분리를 유지한다.

## 모델·평가 계약

역할 vocabulary와 geometry vocabulary는 각각 고정된 명시적 이름/ID/SHA를 갖는다.
checkpoint는 어느 head가 어느 vocabulary로 실제 학습됐는지 저장해야 한다.
기존 enum 열거 순서에서 동적으로 새 target 번호를 만들지 않는다.

기존 checkpoint에서 새 역할/geometry head를 만들 때는 별도 모델 버전으로 취급한다.
공유 backbone의 재사용과 head의 재학습을 분리하고, head weight를 padding해 신규
geometry가 학습된 것처럼 선언하지 않는다. 학습하지 않은 geometry는 unknown/abstain이다.
legacy box 예측만으로 새로운 geometry=rect를 확정하는 adapter를 만들지 않는다.

평가는 적어도 다음을 분리한다.

- 역할+위치 검출: node/container의 bbox TP/FP/FN.
- 렌더 geometry: 대응된 객체의 실제 source preset 정확도와 unknown/unsupported 비율.
  표본의 역할/geometry label 상태와 분모를 함께 보고한다.
- 실제 native geometry: 최종 PPT의 preset·좌표·가시성·개별 편집 가능 객체를 검사한다.
- 라벨: 글자 정확도·누락·거짓 객체 위 라벨을 구분한다.
- 연결: 추적 및 native 단계의 방향·끝점·owner·누락을 각각 보고한다.

bbox가 맞은 ellipse→rect 사례는 위치 검출에서 성공할 수 있지만 geometry에서도
성공한 것으로 세지 않는다. 단순 전체 지표 하나로 이 차이를 감추지 않는다.

## 분할과 다음 검증 순서

새 target을 만들더라도 원본 slide/구조 lineage 단위로 split을 유지하고 모든 renderer,
scale, color/style, 증강 변종을 같은 그룹에 둔다. 이름이나 seed만 다르다는 이유로
독립 자료로 간주하지 않는다. 기존 near-duplicate/구조 중복 감사도 함께 적용한다.
이미 살펴본 validation 두 graph는 진단용 개발 사례로 남긴다.

다음 허용된 작업은 우선 GPU 없이 별도 source-PPT target extractor 계약을 검증하는
것이다. 이번 node 11개를 source ellipse로 재현하면서 bbox/role 출처를 분리하고,
다른 shape·text-only·비구조 preset·미지원 변환의 기권 규칙을 검토한 뒤 새 학습 범위를
결정한다. **이 문서 작성으로 target 수정·새 학습·제품 승격을 승인하지 않는다.**
