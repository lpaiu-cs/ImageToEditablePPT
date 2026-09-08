# 연구용 label_anchor native attachment adapter v1

## 범위와 호출 계약

`image_to_editable_ppt.research.label_anchor_native.write_label_anchor_native(scene, path, styles=None)`는 `(semantic_emitted_scene, audit)`를 반환한다. 제품 emitter, enum, writer는 수정하지 않는다. 기존 `supported_owner_connections`로 label_anchor 연결을 제거하기 **전** scene을 전달해야 한다. R8-P와 R8-T의 고정 source scene을 각각 통과시켜 OCR 효과와 attachment 효과를 분리한다. 이 커밋은 실제 15개 입력 실험, COM 렌더, 학습을 수행하지 않았다.

입력 shape kind, ID, bbox, label, owned text, provenance, connector path/방향/화살표 플래그는 변경하지 않는다. 반환 scene의 shape kind도 `label_anchor`이다. 연결은 기존 `region.emitter.supported_scene`의 endpoint/owner/path 조건에 따라 기권할 수 있으며 사유는 기존 `rejected_connectors`에 남는다. 기존 preset fitter의 최대 4px 근사 허용도 그대로다. 따라서 입력 path의 불변성과 출력 경로의 픽셀 단위 동일성을 혼동하지 않는다.

## writer 경계의 표현

writer에만 label_anchor를 BOX로 표현하고 해당 owner의 fill/stroke를 항상 없음으로 고정한다. 기존 native writer가 동일 ID/bbox의 이 객체에 사각형 custom geometry와 실제 `stCxn`/`endCxn` connection-site를 만든다. 끝점 위치는 기존 경계 정규화/site 인덱스 정책을 그대로 사용한다. 최종 결과의 객체는 기존 owner와 connector뿐이며, 래스터나 별도의 보이지 않는 연결 보조 객체를 추가하지 않는다.

BOX writer는 textbox와 폰트 계산 및 wrap 정책이 다르다. 따라서 임시 semantic reference PPT를 기존 writer로 만들고, label_anchor의 `p:txBody` 전체를 최종 native 객체에 복사한다. 이렇게 owned-text 선택, 문자, 폰트 크기/색, margin, 정렬, no-wrap을 보존한다. `region:text_clockwise`도 기존 native writer 조건에 따라 유지한다. 이 임시 reference는 최종 슬라이드에 추가되지 않으며 자동 삭제한다. 최종 owner는 일반 native autoshape의 연결 기능을 사용하고 텍스트 편집은 text frame에서 가능하다.

원 writer가 Legend 등의 정책으로 anchor를 생략하면 전체 호출을 명시적 오류로 중단한다. ID가 사라진 owner를 몰래 만들거나 다른 owner에 연결하지 않는다. anchor가 있는 실행에서는 검증·저장이 완료된 임시 파일로 최종 경로를 교체하므로 오류 시 기존 출력은 보존한다. anchor가 없으면 기존 `write_native`에 그대로 위임한다.

## 빈 문자와 중복 정책

- 빈 문자열, None, 공백만 있는 기존 owner도 semantic ID/bbox를 보존한다. 연결은 가능하지만 그 사실을 표시 가능한 라벨 복원 성공으로 세지 않는다. 없는 문자를 생성하지 않는다.
- `audit.label_anchor_adapter.owners`에 ID, semantic kind, writer geometry, `has_nonblank_text`, `attached_connector_ids`를 기록한다.
- `visible_label_count`는 출력된 nonblank text owner 수일 뿐이다. 정답 문자, 중복 없는 객체, 유용한 복원 또는 사람의 수정 시간 개선을 뜻하지 않는다. 빈 owner는 0개로 센다.
- 겹친 bbox나 같은 문자의 서로 다른 owner를 자동 병합하지 않는다. 잘못된 OCR과 중복 검출은 그대로 별도 평가 대상이다. 이 adapter는 OCR 오류를 해결하지 않는다.

## portable 검증

`rtk proxy C:/vs/ImageToEditablePPT/.venv/Scripts/python.exe -m pytest tests/test_label_anchor_native.py tests/test_region_runtime.py -q`

결과: **40 passed** (새 adapter 22개, 기존 runtime 18개).

검증 범위: anchor↔anchor 및 일반 node↔anchor, off-center site의 실제 ID/좌표 바인딩, 정·역방향 경로, 양끝/한끝/무화살표, 직선·꺾인 preset, noFill/noLine, 추가 객체·래스터 부재, owned text와 빈 문자별 text XML 동일성, 세로 문자, 겹친 owner 유지, unsupported path/unknown owner 기권, 중복 ID 및 생략 owner 오류 시 기존 출력 보존. 일반 BOX/ROUNDED_BOX/ELLIPSE scene은 기존 writer와 슬라이드 XML 및 반환 geometry/connection audit가 동일하다.

이 검증은 OOXML 구조와 python-pptx 재열기를 확인한다. PowerPoint에서 이동 후 rerouting, 실제 글꼴 대체/화면 렌더, 15개 원본의 attachment 정확성 및 편집 비용은 아직 검증하지 않았다. 제품 채택 근거로 사용하지 않는다.
