# 추가 사진 caption12 COM 입력 준비

china/flower × color/gray × Input/Photo/Encoder =12개를 생성했다. 모든 역할은 non_diagram_photo로 PPT 생성 전에 고정했으며 자산 계보/원본 SHA/캡션은 evaluator 전용이다. 기존 번들 sklearn README를 보존하고 새 다운로드·학습·holdout 사용은 하지 않았다.

- 생성 도구: `tools/r10_photo_caption_controls.py`
- artifact: `artifacts/r10-photo-caption-v1`
- preregister SHA: `c6a3307e32d7ac5a1fff2d72fa5ba818520bb1c6f4185708658520413d076a1b`
- 최종 RGB manifest SHA: `789f5162cf32be342ab868a1edd5f25166f735fbd44c7e87436764391ead0cda`

각 PPT의 실제 XML은 picture1개와 지정 caption1개다. 원본 frame/layout은 앞선 사진 negative와 동일하다. 모든12개를 PowerPoint COM으로800×450 렌더했고 PPT/PNG receipt SHA를 검증했다. 일부 palette PNG는 별도 RGB로 무손실 정규화했으며 decoded pixel 동일성을 검증했다. 원본과 파생물을 덮어쓰지 않았다.

`pptx-receipts.json`, `xml-verification.json`, `renders/powerpoint_render_manifest.json`, `rgb-manifest.json`을 보존했다. 파일·사진·PPT는 내부 artifact로만 두며 커밋하지 않는다.

현재 단계는 **입력 준비만 완료**다. root의 portrait 통합 source SHA가 고정되기 전에는 runtime을 실행하지 않았다. runtime에 caption/역할을 전달하지 않고 최종 RGB만 전달할 예정이다. COM은 입력12개 렌더 완료 즉시 root에 반환했다.
