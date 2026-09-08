# R11 spatial v3: fresh RGB 32건과 실제 COM 검증

고정된 새 probe arm에서 사진 caption12의 기존 9건 오출력이 모두 사라졌다. 기존20 RGB까지 포함한 전체32건은 exit0이며, 사진20건은 box/label/edge/picture 모두0이고 실제 COM PNG도 전 픽셀 흰색이다. 양성12건은 기존 box44/label44/edge24를 유지했다. 일반 사진 의미 분류의 완성을 주장하는 결과는 아니다.

## 고정과 재실행

- root commit: `a5f17cd96489a20810c3cc0c71b6e053b545422e`
- artifact: `artifacts/r11-spatial-fresh-v3`
- lock SHA256: `c0e3285157e3b4e1351fef2178113748ddc6c4cbdb664570d76c257dcdf58389`
- probe flags: `--trace --boundary-union --owned-text --portrait-boxes --texture-guard --nested-owners --pixel-agreement --portrait-text --spatial-texture`
- spatial arm은 `palette_guard=True`, `all_text_regions=True`다. 기존 CLI 기본 경로를 변경한 검증이 아니라 별도 probe의 fresh 실행이다.

기존 `tools/r10_closed_native_integration_audit.py`에 spatial 설정만 추가해 재사용했다. lock에 감사 도구 SHA와 root source snapshot을 기록했다. 기존20의 id/RGB SHA는 `artifacts/r10-pixel-integration-v1/lock.json`과 완전 일치를 assert했고, caption12는 기존 caption CLI lock의 records를 그대로 사용했다. 매 건 원본 RGB 및 root source hash를 검증했다. runtime에 정답·사진 역할·PPT를 전달하지 않고 RGB에서 OCR을 새로 실행했다. 32개 runtime lock의 관련 flags도 확인했다.

재현 실행:

```text
C:/vs/ImageToEditablePPT/.venv/Scripts/python.exe tools/r10_closed_native_integration_audit.py run --out artifacts/r11-spatial-fresh-v3 --nested-owners --pixel-agreement --spatial-texture
```

이미 완료된 폴더를 덮어쓰는 명령이 아니다. 재실행 시 별도 output lock과 폴더를 준비해야 한다.

## 결과와 실제 출력

| 입력 | 건수 | box | label | edge | picture |
|---|---:|---:|---:|---:|---:|
| native diagram | 6 | 24 | 24 | 12 | 0 |
| diagram-as-picture | 6 | 20 | 20 | 12 | 0 |
| 기존 사진 변형 | 8 | 0 | 0 | 0 | 0 |
| 추가 사진 caption | 12 | 0 | 0 | 0 | 0 |

모든 양성에서 connector owner label 쌍은 정확히 Read–Build와 Build–Check이며 PPT XML connector 수도 각각2다. 대표 train-base1-diagram_picture의 실제 COM 렌더에서 세 자식 박스와 두 선, 부모 박스 및 제목을 확인했다. 기존 `Processoverview` 공백 손실과 raster4건의 부모/제목 생략은 그대로 남았다.

대표 flower-color-input은 기존 fraction `.17708474242778263`에서 새 공간 관측 fraction `.25578907239568605`가 되어 `eligible=false`, `dense_spatial_or_color_texture`로 차단됐다. 원본 caption은 실제 OCR로 승인되지만 사진 프레임을 출력하지 않는다. 새 result에는 legacy 관측도 보존되어 있다.

출력32개를 PowerPoint COM으로800×450 렌더했다. 모든 PPT/PNG receipt SHA가 일치하며 사진20개 PNG의 모든 RGB 픽셀이255임을 확인했다. COM manifest SHA256은 `95a2a62172c8ea0c68c1113c030b7b9768e1eed3960397670815bf2dbd53bf5a`다. `verification.json`에 receipt 결과, 합계, 각 입력의 connector label 쌍을 보존했다. COM은 완료 즉시 반환했고 GPU는 사용하지 않았다.

## 판정 경계

사진 원본은 china/flower 2개이며32개 전체에는 도식12개와 사진 파생20개가 포함된다. 독립 사진32개, 미관측 모집단 성능, 사람 수정 시간의 증거가 아니다. 기존9건 실패 산출물은 `artifacts/r10-caption-cli-v1`에 그대로 보존했다. 결과에 맞춘 threshold·코드 변경은 하지 않았다.

root가 별도로 관측한 복잡 도식99 owner 중3건 과잉 기권은 이번 worker32건의 검증 대상이 아니다. 이 보고서의 양성 유지 결과로 그 손실을 취소할 수 없다. 새 arm의 전체 채택 판단에는 그 구조 생략 비용을 함께 명시해야 한다.
