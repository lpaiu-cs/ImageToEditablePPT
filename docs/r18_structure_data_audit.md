# R18 역할 기반 구조 데이터 감사

확정 manifest는 `artifacts/r18-structure-data-v1/dataset_manifest.json`이다. SHA는 `75a52efe4165de6c3a6605eb040eacbb348709c410110f099d980cc5e47d60ec`이다. source1200×750의 72개 1-slide PPT를 실제 PowerPoint COM640×400으로 렌더했다. 모델·예측·다운로드·사진 없이 source 객체를 작성했으며 pixelmask는 만들지 않았다.

| split | scene | negative | scene seed | negative seed |
|---|---:|---:|---:|---:|
| train | 32 | 8 | 18011 | 18021 |
| calibration | 12 | 4 | 18012 | 18022 |
| eval | 12 | 4 | 18013 | 18023 |

scene의 colored_fill_white_bg / white_card_color_bg / outline_white_bg / nested_container 네 family는 split마다 균등하다(각8/3/3장). 일반 scene은 rectangle/rounded rectangle/ellipse/diamond/parallelogram/cylinder 각1개 총6개이며 nested는 큰 rounded container와 내부6개를 각각 기록해7개다. negative의 closed_structure는0이다.

## 정답 역할

`objects`에는 `role=closed_structure`만 들어간다. `elements`는 배경·장식·구조 라벨·열린 구조까지 포함한다. native preset이 있다는 이유로 구조 정답으로 넣지 않는다. 예를 들어 배너는 rectangle이지만 decoration이고, 작은 별/원/원 둘과 선은 decoration이다. 내부2줄 텍스트는 owner_id를 가진 structural_label, 외부 제목과 문단은 decoration, 독립 열린 선은 open_structure다. 열린 선에는 추측한 connector endpoint 관계를 부여하지 않았다.

모든 구조 객체에 source_shape_id, kind1..6, source bbox,640×400 bbox, preset adjustments, fill/stroke, role이 있다. nested child는 parent_id로 별도 container를 참조한다. 구조 라벨·장식은 유효성 학습의 닫힌 구조 정답이 아니지만 전체 도식에서 무의미하다고 해석하지 않는다. 겹치는 parent/child GT를 union mask로 합치지 않았다.

## 분포와 제한

train/cal node는3열×2행, eval은2열×3행의 다른 위치 계열이다. source 폭180..250, train/cal 높이125..180, eval 높이120..155이므로 layout과 크기/종횡비 이동이 동시에 있다. 양쪽 효과를 분리했다고 주장하지 않는다. eval 어휘8개는 train/cal 어휘8개와 겹치지 않으며 제목·문단·라벨에 동일한 split 어휘 경계를 적용했다.

색·선폭·종류 배치·라벨 선택은 독립 추출한다. family가 fill/background 조건을 정하는 것은 의도한 대조다. outline은 noFill이고 nested parent도 noFill이다. 기본 preset adjustments만 사용한다. 장식은 일부 도형 bbox 안에 있지만 실제 diamond/ellipse 윤곽 바깥에 보일 수도 있으며 별도 decoration 역할을 유지한다. 자연사진·실제 로고·복잡한 관계/연결 복원 일반화는 검증하지 않는다.

## 검사와 육안 확인

- source XML의 구조 xfrm bbox, preset 종류, source_shape_id/name, 역할 대응을 검사했다. picture가 없고 모든 PPT가1 slide다. noFill 및 라벨 owner 참조도 확인했다.
- node끼리 bbox가 겹치지 않고 화면 내부에 있다. nested parent가 각 child bbox를 포함하며 parent/child는 별도 객체다.
- 72개 source/COM receipt SHA와 RGB 변환 픽셀 동일성,640×400 크기를 검사했다. 입력 RGB SHA72개가 모두 고유하다.
- split별4family 균등 및 어휘 집합 분리를 확인했다.
- train/cal 각각4family와negative 대표 총10개 보드를 직접 확인했다. 입력과 closed_structure GT만 표시한 비교 보드는 `artifacts/r18-structure-data-v1/development-qa-00.png`~`09.png`이다.00~04는train,05~09는calibration이다.
- eval은 source geometry/role/receipt 감사만 했고 이미지 육안 확인·모델 성능 측정·root에 eval 시각 정보 전달은 하지 않았다.
- 추가 XML 검사는 같은 artifact의 `audit_xml.py`/`xml-audit.json`, family·어휘·개발 보드는 generator의 `qa`와 `qa.json`에 남겼다.
- COM은 반환했고 POWERPNT 프로세스가 남지 않았다. 기존 동결 파일이나 root 모델 코드를 수정하지 않았다.

## 재현

```powershell
C:/vs/ImageToEditablePPT/.venv/Scripts/python.exe tools/r18_structure_data.py build --out <새폴더>
# COM 슬롯 확보 및 기존 POWERPNT 부재 확인 후 실행한다.
& C:/vs/ImageToEditablePPT/tools/render_pptx_via_powerpoint.ps1 -InputPath <새폴더>/pptx -OutputDirectory <새폴더>/renders -Width 640
C:/vs/ImageToEditablePPT/.venv/Scripts/python.exe tools/r18_structure_data.py finalize --out <새폴더>
C:/vs/ImageToEditablePPT/.venv/Scripts/python.exe tools/r18_structure_data.py qa --out <새폴더>
```

- preregister SHA: `9796465661527a86252b4e5ce1a229053e35d6141e6b1e76550eb9616acbcb2f`
- COM manifest SHA: `c980276716d4131c01b976f44b23d8ed8613b88510657f9a3fa378ba4d137bda`
- generator SHA: `c1a1aa255249b652f50270aaf281dee2230e42b990dabe2091c58c92eeb9e24f`

root의 `docs/r18_candidate_validity_spec.md`를 읽고 데이터 계약과 대조했다. 데이터는 예측 결과에 맞춰 수정하지 않았고 학습 준비 이후 고정한다.
