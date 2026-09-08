# R19 개별 구조 객체 source 데이터 감사

확정 데이터는 `artifacts/r19-instance-source-data-v1/dataset_manifest.json`이다. SHA는 `23b9dabaa5d584d31552b15116e9887b309b844fef86c710bad78dee77471cb2`이다. native1200×750의384개 1-slide PPT를 실제 PowerPoint COM960×600으로 렌더했다. 학습·추론·GPU·신규 라이브러리 설치는 수행하지 않았다.

## 구성과 사전 고정

colored_fill_white_bg, white_card_color_bg, outline_white_bg, nested_container, mixed_dense, hard_negative 각각 train48/calibration8/eval8이다. 합계 train288/calibration48/eval48이다. source ID는 전부 `r19-`로 시작한다.

family 순서에 따른 index0..5를 train190100/calibration190200/eval190300에 더해 독립 RNG seed를 정했다. 일반 scene의 자식 수는3..9, mixed_dense는9..15다. family/split별 총자식 수가6의 배수가 되도록 마지막 scene 개수를 허용 범위에서 정하고,6종을 정확히 같은 수로 만든 전체 pool을 shuffle해 배정했다. 따라서 장면마다 종류 구성은 달라도 각 family/split의 자식 종류 분포는 정확히 균등하다.

nested_container와 mixed_dense에는 큰 rounded 부모1개 또는2개가 있다. 각 family/split에서 절반씩 배정하며 각 child의 parent_id를 보존한다. 부모 없는 일반3family와 구분한다. 전체 자식2268개는 종류별378개이며, 부모192개는 추가 rounded 객체로 별도 집계한다. 따라서 전체 객체를 섞으면 rounded 빈도가 증가하며 이를 종류 균형으로 숨기지 않는다.

자식 스타일은 전체 filled734/whitecard768/outline766개다. 일반family의 스타일은family가 정하고 nested/mixed 내부는 세 스타일을 순환한다. 종류 pool과 스타일 선택은 분리했다. 부모는 noFill이며 기본preset adjustments를 사용한다.

## geometry와 역할 계약

`objects`에는 closed_structure만 들어간다. source bbox와960×600 bbox, kind, ID, source_shape_id, role, parent_id, fill/stroke, adjustments를 보존한다. `elements`에는 배경, 배너, 외부 텍스트, 구조 라벨, 장식, 열린 선도 있다. native rectangle 배너·별·원은 decoration으로서 구조 GT가 아니다. 선은 open_structure이며 겹쳐 보이더라도 추측한 connector 관계를 부여하지 않는다. parent/child를 union mask로 합치지 않았다.

각 영역을 객체 수에 맞춘 grid cell로 나누고 폭은cell의53~80%, 높이는44~76%로 추출해 종횡비를 바꾼다. train/cal 일반은3열, dense는5열, 두 부모 내부는2열이다. eval은일반/dense4열, 두 부모 내부3열 및 교대행 위치 shift를 사용한다. node끼리 bbox가 겹치지 않고 각 child bbox는 parent bbox 내부에 있다. 이 검사는 bbox 포함이며 rounded parent의 곡선 내부 픽셀 포함을 별도 증명한 것은 아니다.

내부 라벨은2~3개 source 문단이고 문단마다1~2단어다. native word-wrap 때문에 보이는 줄 수가 늘거나 가늘고 작은 도형의 실제 윤곽 밖에 텍스트가 보일 수 있다. 그 경우에도 bbox는 source 도형 geometry이며 텍스트 외곽으로 확장하지 않는다. 작은 glyph도 별도 decoration으로 유지한다. 열린 선2~5개는 구조/텍스트와 겹칠 수 있다.

eval의12개 어휘는 train/cal12개 어휘와 겹치지 않는다. layout·어휘·seed를 함께 분리했으므로 각각의 효과를 독립적으로 추정하지 않는다. 모든 자료는 native 합성이며 자연사진·실제 로고·복잡한 의미 역할 일반화를 입증하지 않는다. CogBot17node 수동 장부는 생성·학습에 사용하지 않았다.

## 검증과 육안 확인

- 전체 source XML의1slide, picture 부재, ID/name, preset, source xfrm bbox, noFill, role 대응 검사 통과.
- node bbox의 화면 내부/서로 비중첩/parent 참조와 bbox 포함 관계 검사 통과. node/parent 개수와 objects/elements의 closed_structure 집합도 일치한다.
- 각 family/split의6종 자식 수가 정확히 동일한 것을 검사했다.
- train 대표5family+negative6개를 먼저 실제 COM 렌더하고 직접 확인한 뒤 같은960폭 설정으로 전체384개를 렌더했다.
-384개 source PPT SHA, COM render SHA, 변환 RGB 픽셀 동일성,960×600 크기 및 서로 다른384개 RGB SHA 검사 통과.
- train 비교 보드는 `artifacts/r19-instance-source-data-v1/train-qa-<family>.png`6개다. 입력과 closed_structure GT를 나란히 표시하며 nested 보드에서 부모/자식 별도 bbox를 직접 확인했다. 사전 source 렌더는 `sample-renders/`에 보존했다.
- eval 이미지 육안 확인·성능 측정·root에 eval 시각 정보 전달은 하지 않았다. eval은 source/GT/receipt 감사만 했다.
- COM은 반환했고 POWERPNT 프로세스가 남지 않았다. 기존 R18 등 동결 파일·데이터는 수정하지 않았다.

## 재현과 해시

```powershell
C:/vs/ImageToEditablePPT/.venv/Scripts/python.exe tools/r19_instance_source_data.py build --out <새폴더>
# COM 슬롯과 기존 POWERPNT 부재를 확인한다.
& C:/vs/ImageToEditablePPT/tools/render_pptx_via_powerpoint.ps1 -InputPath <새폴더>/pptx -OutputDirectory <새폴더>/renders -Width 960
C:/vs/ImageToEditablePPT/.venv/Scripts/python.exe tools/r19_instance_source_data.py finalize --out <새폴더>
C:/vs/ImageToEditablePPT/.venv/Scripts/python.exe tools/r19_instance_source_data.py qa --out <새폴더>
```

- preregister SHA: `5fb621db1bdd481d3af95efe244292720068b37b55ed4c399c43113c7902dc34`
- COM manifest SHA: `08483bbd6772dab334beafbfc59a18126ff24b1b569573fd4e8f90940c8c284a`
- generator SHA: `3824ad7868e1bda2a003bef3535817b25e554ef269dac5ceff72da566a7ee4fe`

root의 `docs/r19_instance_detector_spec.md`를 읽고 데이터 계약과 대조했다. 데이터는 모델 결과에 맞춰 바꾸지 않았으며 READY 이후 고정한다.
