# R15.1-A 경계 보완 독립 회귀: 채택 불가

## 판정

root `c9b5d1740c2372028f1f88623eb9c970daa31ae2`의 `--boundary-gaps`를 R14 fixed flow 옵션에 추가하여 기존 RGB 43건을 새로 실행했다. 모두 exit 0이며 입력·소스 해시 검사가 통과했다. 기존 proposal prefix는 43/43 보존했지만 최종 emitted scene은 11/43에서 바뀌었다. 사진 캡션 오탐과 기존 연결 손실 때문에 이 arm을 채택할 수 없다.

| 대상 | R14 v4 shape/label/edge | R15.1-A | 관측 |
|---|---:|---:|---|
| both-out | 2/2/0 | 3/3/0 | Photo 캡션 strip 추가 |
| failed-chain | 2/2/0 | 4/4/0 | Photo strip 2개 추가 |
| one-way | 2/2/0 | 3/3/0 | Photo strip 추가 |
| flower-flow | 3/2/2 | 3/3/0 | 기존 frame과 연결 2개 손실, 캡션 추가 |
| gray-flow | 3/2/2 | 4/4/2 | 부모 Photo·어두운 채움 및 별도 Photo strip |
| flower color/gray × Encoder/Input/Photo, 6건 각각 | 0/0/0 | 1/1/0 | 단독 사진 캡션 기권 실패 |

전체 합계는 68/64/32에서 79/77/30으로 바뀌었다. picture 객체는 모두 0이다. 나머지 32건의 emitted scene JSON은 R14 v4와 완전히 같다. 기존 사진 음성 20건 중 14건만 최종 공백을 유지했다. 새 잘못된 방향 간선 추가는 없지만 flower-flow의 기존 방향 간선 2개가 사라졌다.

## 실패 경로

gray-flow의 신규 `closed:3`은 `[281,126,520,165]`, `canny_one_pixel_gap`, raw support 최대 거리 1.0이다. 사진 카드의 흰 캡션 영역이 독립 Photo 라벨 노드가 된다. 기존 전체 카드 `closed:2`의 nontext unexplained fraction은 약 0.483841이지만 spatial texture eligibility는 true다.

`frame_witnesses`의 내부 labelled seed 보호 조건 때문에 부모의 빈 프레임 승인이 차단된다. 이후 공통 `admitted_ids`는 spatial eligible+label인 부모를 일반 객체로 승인한다. 그 결과 부모와 캡션이 모두 Photo로 출력되고 부모에는 어두운 채움이 남는다. flower-flow는 부모의 texture veto가 유지되어 부모와 연결이 빠지고 캡션만 추가된다. 이는 raw 거리 bound 위반이 아니라 새 후보가 내부 역할 판정을 바꾸는 상호작용이다.

기존 후보 ID·좌표 보존만으로 최종 출력 보존을 보장할 수 없다. 후보 역할 및 admission 관계를 함께 검증해야 한다.

## 효용 검증의 한계

신규 proposal은 13사례 14개이고 모두 사진 캡션 strip이다. `eval-base0-caption`과 `eval-base0-gray_caption`은 신규 후보가 생겨도 최종 공백을 유지했다. 이 43건에서 정상 gap-closed 양성 회복은 0건이다. 따라서 후속 내부/경계 중첩 후보 제한이 43건을 통과하더라도 신규 recall 효용까지 입증하는 것은 아니다. 정상 nested child 회복을 보류하는 경우 그 제한을 별도로 명시해야 한다.

## 재현과 렌더 증거

- artifact: `artifacts/r15-boundary-fresh-v1`
- lock SHA: `a64fe174ac19718f498861963f2a50944ef9deadeeae2c9fc35ceef715f1d714`
- 입력: R14 v4 lock의 43 records 및 RGB SHA 그대로.
- 실행: worker `tools/r10_closed_native_integration_audit.py run --out artifacts/r15-boundary-fresh-v1 --nested-owners --pixel-agreement --spatial-texture --flow-frames --boundary-gaps`. root probe를 직접 호출하며 root src/tools 및 관련 명세 스냅샷을 매 사례 해시 검사했다.
- `comparison.json`/`compare.py`: 전체 scene 차이, 객체·연결 추가/손실, XML 텍스트·채움, proposal prefix 검사.
- 대표 COM 3건: gray-flow, both-out, flower-flow. 모두 800×450으로 렌더하고 직접 이미지를 확인했다. 전체 43 COM 실행으로 주장하지 않는다.
- COM manifest SHA: `8fe1235c0f7062dad6f99df840cd6ecdb71615fa1bbe00cedd063d34a438f0c5`.
- `receipt-binding.json`/`verify_receipts.py`: 원본 PPT·RGB, fresh 출력 PPT, COM 렌더 SHA를 연결하고 확인했다. COM 슬롯을 반환했고 POWERPNT 프로세스가 남지 않았다.

동결된 root 소스에는 손대지 않았다. 신규 대조군 생성·학습·다운로드·Phase16 holdout 접근은 없었다. 기존 자료의 경계 coverage 제한은 `docs/r15_boundary_source_inventory.md`에 별도로 기록했다.
