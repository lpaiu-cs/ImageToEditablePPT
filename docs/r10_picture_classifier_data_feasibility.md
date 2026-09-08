# Source-closed 후보 의미 분류: 로컬 학습쌍 감사와 최소 실험안

## 결론

**확인한 실제 PPT→PNG train336쌍은 구조 양성의 출처를 복구할 수 있지만, picture 음성이 0개여서 그대로 이진 분류기를 학습·검증할 수 없다.** 새 학습이나 데이터 생성은 수행하지 않았다. 현재 로컬 자료를 이용한 제한적 합성 pilot은 가능하나, 먼저 의미 라벨과 음성 쌍을 별도로 만들어야 한다. 실제 사진의 일반화 성능을 입증할 데이터는 이번 감사에서 확보하지 못했다.

PPT의 `p:pic`은 저장 표현이고 diagram/picture 의미는 별개다. 래스터 다이어그램도 변환 대상일 수 있고 native 도형으로 그린 장식은 비대상일 수 있다. 따라서 `p:sp=positive`, `p:pic=negative`만으로 만든 학습은 저장 형식 분류에 그칠 위험이 있다.

## 확인 범위와 실재 규모

root `C:/vs/ImageToEditablePPT/workbench-ml`의 manifest 여섯 개를 읽었다. payload는 `split=train`인 원본 soffice 두 데이터셋만 열었다. val/test는 manifest 분할 metadata만 확인했으며 이미지·annotation·PPT payload를 열지 않았다. Phase16/real holdout을 열지 않았다. worker checkout에는 별도 `workbench-ml` 폴더가 없다.

| 원본 데이터 | manifest 전체 | train | 직접 검증한 PPT/PNG/JSON train쌍 | 원본 PPT |
|---|---:|---:|---:|---|
| ds-v13-pil, seed1301 | 350 | 280 | 0 | manifest pptx_written=False |
| ds-v13-soffice, seed1302 | 210 | 168 | 168 | 존재 |
| ds-v13b-pil, seed1308 | 350 | 280 | 0 | manifest pptx_written=False |
| ds-v13b-soffice, seed1309 | 210 | 168 | 168 | 존재 |

soffice 전체420 중 val42/test42 payload는 미검증이다. PIL700은 동일 spec의 합성 RGB/annotation이며 실제 PPT 렌더 쌍으로 세지 않는다. mixed560과 extended1120은 위 원본의 경로를 합친 manifest여서 추가 독립 쌍이 아니다. 소규모 session-experiment manifest는3개(2train/1test)를 기록하지만 이번336 payload 감사에는 포함하지 않았다.

검증한336개 모두 PNG640×360, PPT1slide다. 원본 XML의 `p:sp`2046개는 annotation node1874+container172와 전부 name으로 매칭된다. `p:cxnSp`1825개이며 `p:pic`, `a:blip`, `ppt/media`, graphicFrame, group은 모두0이다. preset은 rect1058, roundRect804, ellipse184이며 connector line1825가 별도다. 이는 candidate crop 수가 아니다. 새 source-closed 제안기를 돌려 실제 수집 가능한 candidate 수를 따로 측정해야 한다.

## 출처 근거와 SHA

감사 도구: `tools/r10_pair_provenance_audit.py`.
모든336개의 절대 경로, PPT/PNG/annotation SHA, 크기, XML 개수, 이름 매칭 결과는 `artifacts/r10-pair-provenance-v2/results.json`에 기록했다. 결과 SHA는 `caa75aa20f16662ecfd610a686ecce659f95ce54b5cf2e7b98f1f875a8e7fdc7`이다. v1은 annotation을 최상위에서 잘못 찾아 node0으로 센 초기 감사였고, `primitive_scene`을 읽도록 고친 v2를 최종 근거로 삼는다. v1은 덮어쓰지 않았다.

원본 manifest SHA:

- ds-v13-soffice: `671c4fe856c5d6393ba19b4255020304642929797cfdadcb75d102f6ed224557`
- ds-v13b-soffice: `b4885f947bab99c6194b891c281b5a93674dac895bea3cdb0f909bc4ac76295d`
- ds-v13-pil: `665db9aefe3e3196be52aa9b08f4e27c25def1423534a3a5d9488cbf995fffb0`
- ds-v13b-pil: `cdb1bee32e38e2621effd15f9aa4dfc1983f83e0eb5ca67279d60c9af20ea181`
- ds-v13-mixed: `c28737091a654fd8c35017b76318def3aec85edfffe1d070ba7b487629c7e5f9`
- ds-v13-extended: `05fc41c9a9f6322f8bf4f8e18fee68d60cfc9650a2871c5b3586b9de0257c823`

대표 실재 쌍은 `C:/vs/ImageToEditablePPT/workbench-ml/ds-v13-soffice/train/table_matrix_1302_00000`의 세 파일이다.

- PPTX SHA: `5a17c7542248fb771e37bb1ea63b9350f0508ae1e660589f27cf6999500e413d`
- PNG SHA: `42ddc59e8a718bcbb2bdd7aae6cf025ac82cfce1eccc33edea4be86583469ba1`
- JSON SHA: `7bf89ec3524accd26d20a0350611f3b04b3a235fb2c2752a67a70c6bb7a088b1`
- slide6096000×3429000EMU、PNG640×360、node6=roundRect6、picture0。

현재 생성 경로 `ml/generate_dataset.py`는 spec→PPT/annotation을 쓰고 soffice renderer에서 `render_pptx_batch_via_soffice`를 호출한다. `ml/synthesize.py`는 `soffice --headless --convert-to png`를 실행하고 크기가 다르면 resize한다. 현재 파일 SHA는 각각 `4ffb1487575e924a6a2a31f4fd0f508fc3c827e986d5d53b52584a6178438e55`, `b8d64dda53c5a0f2ac0b2f98ccd5f82244a38dd29ac4982cf4c93a409300461a`다. 이는 현재 코드 증거이며 과거 실행 코드와 같다는 attestation은 아니다.

별도 COM manifest `C:/vs/ImageToEditablePPT/artifacts/region-native-production/synthetic-v3-renders/powerpoint_render_manifest.json`은11개 PPT/PNG의 기록 SHA가 모두 현재 파일과 일치했다(manifest SHA `c7ecce108949353d6e17cf05445f9c9239d8c09b9a279af06fad98f22d8e0c8f`). 그러나 `tools/validate_region_synthetic.py`는 RGB를 생성한 후 변환기로 PPT를 만들고 그 출력을 렌더한다. **이11개는 PPT 렌더 실재 증거이지 원본 semantic GT가 아니다.** root의 fresh7 및 worker의 conversion output도 같은 이유로 교사 라벨로 재사용하지 않는다.

## 부족하거나 주의할 필드

1. 의미 라벨: annotation은 node/container 역할 중심이며 picture/photo/icon/decoration/unknown 라벨이 없다. XML preset도 annotation kind와 별도다. 기존 `docs/rendered_geometry_target_contract_proposal.md`는 이미 노출된 graph의 ellipse/box 불일치를 기록한다. 이번에 그 val payload를 재개봉하지 않았다.
2. 렌더 출처: soffice336 annotation의 `metadata.renderer`가 전부 `pil_raster_v1`이다. dataset manifest만 `soffice_png_v1`이다. 개별 renderer version/options, 실행 codeSHA, PPT→PNG 당시 hash receipt, resize 여부 기록이 없다. 이번 현재 파일 hash는 그 과거 연결을 소급 증명하지 않는다.
3. candidate target: candidate ID/contour/crop SHA, 후보 발생 경로, source object ID와의 겹침, picture 내부/프레임/parent 혼합 여부, 보이는 면적과 가림 관계가 없다. name 매칭만으로 모든 crop의 의미가 정해지지 않는다.
4. split lineage: 원본 slide/asset ID, 재렌더·crop·색변형의 동족 group, asset 중복 hash, 이미 노출된 사례 여부를 별도 고정해야 한다. mixed alias를 다른 split으로 재사용하면 누출이다.
5. 음성 분포: 실제 자연사진/회색사진/평면 삽화 음성이 없고 worker texture/glyph fixture는 PNG만 있는 합성 진단이다. 학습용 원본 PPT 쌍으로 세면 안 된다.

## 가장 작은 실행 가능한 실험 명세 — 아직 실행하지 않음

목적은 일반 semantic 완성이 아니라 **source-closed 후보의 사진 caption/glyph 오승인을 줄이는 제한적 합성 분류 실험**이다. converter의 geometry/연결/OCR threshold는 고정하고 기존 frozen 결과와 별도로 기록한다.

1. 기존336 train 중7family×6개의 원본 slide를 ID 정렬 후 고정 선택한다(42개). 각 family에서4/1/1개를 pilot train/calibration/eval로 나눈다. 이는 기존 train 내부의 개발 분할이며 기존 val/test/holdout을 열지 않는다. 같은 base scene의 모든 파생본은 같은 split에 둔다.
2. 원본별4개 파생 deck을 만든다(계획168개; crop 수는 제안 후 보고). native diagram, 같은 diagram을 raster로 넣은 표현 대조, local procedural 비구조 picture+caption, native 장식+텍스트 혼합을 포함한다. 기존 PNG fixture를 쓸 때는 새 PPT에 명시적으로 삽입하고 다시 렌더하여 출처를 만든다. texture asset/색·회색 변형은 split별 독립 seed와 asset lineage로 분리한다. 외부 다운로드·유료모델은 필요 없다.
3. 별도 semantic manifest에 `diagram_structure / non_diagram / mixed_unknown`과 작성 이유를 기록한다. `p:pic` 여부는 보조 provenance만 둔다. 사진을 포함한 구조적 parent는 무조건 negative로 만들지 말고 mixed_unknown 및 source child 관계를 기록한다. 교차하는 crop은 abstain 평가 대상으로 보존한다. 독립 인간/검토자의 source-image 대조 없이 synthetic role을 실제 사진 의미 GT로 확대하지 않는다.
4. 모든 새 원본 PPT를 **동일한 PowerPoint COM**으로 스크린샷 렌더한다. 새 출력에 원본 PPT/렌더 PNG/asset/semantic annotation의 개별 SHA receipt, COM version·명령·실제크기·resize, source commit, object ID·EMU bbox·rotation/group/shape/picture type, pixel mapping을 잠근다. 후보 제안 sourceSHA와 cropSHA를 추가한다. metadata는 classifier 입력으로 주지 않는다. 현재 closed-candidate pipeline을 먼저 동결하고 classifier 판정만 비교한다.
5. 작은 crop CNN을 임의 초기화해 CPU에서 학습하고, 현 texture veto/항상기권 baseline과 비교한다. 기존 detector checkpoint는 클래스 목적이 달라 이진분류 정답으로 재사용하지 않는다. 단일 사전 고정 구성으로 시작하고 dev에서만 abstention threshold를 정한다. 입력은 원본 candidate crop 및 고정 문맥 범위이며 GT/PPT XML은 학습 target 생성 쪽에만 둔다.
6. internal-check는 고정 후 한 번 평가한다. picture caption false-accept, diagram false-reject, unknown abstention, raster diagram 유지율을 각각 보고한다. family/asset lineage별 실패와 분모를 공개하고 단일 accuracy로 합치지 않는다. 이미 본 worker 반례는 회귀 대조군으로만 사용한다. 표본이 작아 production gate나 자연사진 일반화 판정은 내리지 않는다.

지금 바로 가능한 것은 긍정 쌍의 candidate/target 출처 추출과 이 명세의 준비다. 음성 쌍·semantic annotation·새 렌더 receipt 없이 현재 detector 데이터만 이진분류로 바꾸는 학습은 권하지 않는다.

## 외부 이미지의 기존 로컬 출처 확인

새 다운로드 없이 `benchmarks/real_v1/manifest.json`의 source metadata와 파일 존재만 확인했다(manifest SHA `711fef61a0bb6635411b1fc71e1c38db4471b036eb128a5108b7f2cb9ae30ea9`). non_diagram5개가 `data/real_benchmark_v1`에 존재한다: identification-rate-plot, tsne-scatter, energy-plot, generated-pan, cell-images. 모두 `public-` 접두사 PNG다. 이번 추가 확인에서는 해당 이미지 payload를 열거나 모델에 입력하지 않았다.

출처는 로컬 manifest가 고정한 Hugging Face `yousefg-codes/research-paper-figures`, revision `3e8a1a190f814b48a358e5be60e69de28e886110` 및 각 shard/row/hash다. 이름만으로 자연사진의 종류·품질을 확정하지 않는다. 이들은 이미 고정된 acceptance 집합이고 원본 PPT와 object-level semantic GT도 없으므로 **새 학습 음성으로 이동시키지 않는다.** 현 상태에서 확인된 독립 train 사진 pool은 없다. 현재 manifest에 권리 확인 필드가 없어 재사용 가능성까지 검증한 자료도 아니다. 후속 실제 사진 수집이 필요하면 기존 평가 자산과 분리된 출처·사용권·asset lineage를 확보해야 하며, 이번에는 다운로드나 수집을 하지 않았다.

worker의 procedural texture/사진 캡션 fixture는 외부 사진이 아니다. 제한적 pilot에는 새 PPT로 감싼 합성 대조군으로 사용할 수 있지만 실제 자연사진 일반화 주장의 대체물은 아니다. 이 제안은 개발 진단이며 holdout 또는 production acceptance가 아니다. 기존 annotation renderer metadata는 수정하지 않았다.
