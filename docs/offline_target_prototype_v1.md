# 연구용 offline PPT target extractor prototype

## 완료 결과와 범위

기존 graph 두 원본 PPT에서 **11개 ellipse target을 재현**했다. geometry는 source PPT
XML에서, node 역할은 별도 annotation의 검증된 `primitive_scene.nodes` 소속에서 얻었다.
기존 `kind=box`는 감사용 legacy 값으로만 보존하고 geometry로 복사하지 않는다.

| 원본 | 감독 가능한 node/ellipse | 마스킹한 기타 객체 | 이전 XML 감사와 bbox 차이 |
|---|---:|---:|---:|
| graph_1302_00029 | 5 | container shape2 + connector5 | 0px |
| graph_1302_00063 | 6 | container shape1 + connector7 | 0px |

이는 이미 본 validation 두 자료의 **target 추출 재현**이다. 새 모델의 검출 성공률,
미관측 평가, 제품 개선을 측정한 결과가 아니다. 추가 학습·checkpoint 추론·COM 실행은 없다.

## 구현 경계

추가한 파일:

- `research/offline_ppt_targets.py`: SHA 검증, 역할 결합, 제한 geometry 추출.
- `tools/extract_offline_ppt_targets.py`: 기존 두 graph의 준비 및 offline 실행 CLI.
- `tests/test_offline_ppt_targets.py`: portable XML/PNG/annotation fixture를 이용한 회귀 검사.
- `benchmarks/offline_target_prototype_v1.json`: 실제 원본 재현 및 불변 검증 요약.

기존 enum/dataset/loader/checkpoint/제품 source와 동결 산출물은 수정하지 않았다.
이 모듈은 모델·제품 inference 경로를 import하지 않는다. target 출력을 기존 prediction
handoff로 가장하지 않으며 최상위에 `research_only=true`, `inference_input_allowed=false`,
`training_performed=false`를 기록한다. GT는 offline target 구성에서만 읽는다.

## 명시적 입력 계약

`offline_target_request_v1`의 각 case는 다음을 요구한다.

- sample ID와 원본 PPT/RGB 파일 경로·SHA.
- 별도 reviewed role JSON 경로·SHA.
- 원 dataset manifest 경로·SHA와 renderer ID, renderer version 또는 명시적 null.
- `full_slide=true`: crop/미상 변환은 지원하지 않는다.

source manifest의 sample ID가 유일해야 하며 PPT/PNG/annotation 경로가 요청과 같아야 한다.
PPT는 단일 slide로 제한하고 실제 presentation relationship이 `ppt/slides/slide1.xml`을
가리키는지 확인한다. duplicate ZIP part, slide relationship, source shape ID는 거부한다.

role JSON은 source PPT/RGB/annotation SHA, review 출처, 각 shape ID/name과
annotation 객체 ID/collection/role/visibility를 가진다. 허용된 역할 결합은 다음과 같다.

| 별도 annotation collection | semantic_role |
|---|---|
| primitive_scene.nodes | node |
| primitive_scene.containers | container |
| excluded_objects | excluded |
| unclassified_objects | unknown |

collection에 객체가 실제 존재해야 하고 지정 role이 collection과 같아야 한다.
중복 annotation/assignment, 모호한 name join, 누락된 review·SHA는 거부한다.
review 선언 자체는 외부 검토의 출처이지 사람의 판단을 자동 증명하는 인증은 아니다.

실제 실행에서는 이전 두 원본 감사와 이번 RGB 육안 확인에 근거해 **node11개만**
reviewed_visible로 지정했다. container3개는 이번 역할 검증 범위에 넣지 않았으므로
기존 annotation에 있더라도 자동 감독 대상으로 추가하지 않았다.

## 지원 geometry와 마스킹

PPT의 `p:sp`이며 group ancestry/회전/flip이 없는 다음 geometry만 지원한다.

- rect → rect
- roundRect → round_rect
- ellipse → ellipse
- `txBox=true`이며 fill/line 모두 명시적 noFill이고 문자열이 있는 textbox → text_only

raw `prstGeom`, preset adjustment, source shape ID/name/type, group ancestry,
hidden 상태, EMU offset/extent, rotation/flip은 그대로 기록한다. preset adjustment는
보존만 하며 추가 파라미터 학습이나 완전한 렌더 해석을 구현한 것은 아니다.

그룹·회전·flip·숨김·미지원 preset/custGeom·상속된 미상 transform·비양수 extent·
slide 밖/clipping은 geometry를 추정하거나 좌표를 보정하지 않고 마스킹한다.
알 수 없는 shape-tree 구성은 조용히 생략하지 않고 전체 요청을 거부한다.
connector·picture·graphic frame 등 미지원 shape type도 이유를 남기고 마스킹한다.

**preset만으로 역할을 만들지 않는다.** 별도 역할이 없으면 ellipse도 unknown이며
role/geometry/bbox supervision mask가 모두 false다. excluded/unknown 역할,
미확인·가림 visibility도 같은 방식으로 감독 대상에서 제외한다.
raw로 관찰된 geometry 값이 남아 있더라도 `supervision_mask=false`를 무시해 학습하면 안 된다.

## 좌표와 renderer provenance

좌표는 annotation bbox를 사용하지 않고 PPT `a:xfrm`에서 얻는다.
source slide 크기와 실제 RGB 크기로 각각 x/y scale 및 3×3 변환행렬을 기록한다.
두 실제 자료는 6096000×3429000 EMU → 640×360px이므로 양축 scale은
`1/9525 = 0.00010498687664041995 px/EMU`다.

renderer ID는 source manifest의 `soffice_png_v1`과 대조했다. 기존 자료에는 정확한
renderer version이 없어 null/not_recorded로 남겼다. 전체 slide 변환은 source manifest와
기존 렌더에 근거한 선언이며 이번 실행에서 renderer를 다시 돌려 입증한 것은 아니다.
그룹·crop·회전·flip 좌표를 일반적으로 처리하는 도구로 해석하지 않는다.

객체 identity는 `PPT SHA:slide part:shape ID`다. source name은 이번 generator 자료의
검증된 annotation join에만 사용한다. 일반 PPT의 이름이 항상 유일하다고 가정하지 않는다.

## 검증

**33 passed**. 핵심 검사는 다음과 같다.

- rect/roundRect/ellipse/textbox 지원과 별도 container 역할.
- annotation kind=box/bbox가 다른 값이어도 source ellipse/PPT 좌표를 사용.
- 단일 preset이 node 역할을 생성하지 않는 negative controls.
- excluded/unknown/미확인 visibility는 false loss mask.
- group/rotation/flip/unknown preset/hidden/clipping의 명시적 마스킹.
- 중복 identity·잘못된 역할 결합·SHA 변조·비유한 XML 좌표·미상 crop/slide 관계는 거부.
- 출력은 새 파일만 작성하고 기존 파일을 덮어쓰지 않음.

unit fixture의 작은 ZIP은 parser 계약 검증용 XML 묶음이다. 실제 렌더 품질 검사라고
주장하지 않는다. 그와 별도로 실제 원본2개의11개 shape ID/prstGeom/bbox를 이전 XML
감사와 비교해 전부 일치함을 확인했다.

source PPT/RGB/annotation/manifest SHA, v1 고정 artifact 전체 SHA, v2 final handoff SHA,
기존 dataset/enum 코드 SHA와 checkpoint SHA도 확인하여 불변임을 검증했다.

## 산출물과 재현

새 로컬 산출물: `artifacts/offline-target-prototype-v1`.
최종 target은 **`targets.final.json`**이다. `targets.json`은 unknown tree 구성의 엄격
거부를 보완하기 전 초기 실행본이며 보존하지만 후속 비교에는 final 파일을 사용한다.
`request.json`과 두 `*.roles.json`이 입력/역할 provenance를 담는다.

target SHA:
`599161414e460be37ce3c1820295635f9f1a0d5c981c7569a1390e07b8962ff8`.
extractor SHA:
`6e0887896a9d23d7a433b20522e54c94d6e63d49d031afad47f3792d3c965d24`.

```text
rtk proxy C:/vs/ImageToEditablePPT/.venv/Scripts/python.exe tools/extract_offline_ppt_targets.py prepare --audit benchmarks/rendered_geometry_target_audit_v1.json --output-dir <새 폴더>
rtk proxy C:/vs/ImageToEditablePPT/.venv/Scripts/python.exe tools/extract_offline_ppt_targets.py extract --request <새 폴더>/request.json --output <새 폴더>/targets.final.json
rtk proxy C:/vs/ImageToEditablePPT/.venv/Scripts/python.exe -m pytest -q tests/test_offline_ppt_targets.py
```

후속 학습을 결정하려면 별도 target/vocabulary/원본 단위 split 계약을 고정해야 한다.
현재 두 validation target을 미관측 성능 측정이나 학습 승인으로 사용하지 않는다.
