# Handover: Phase 7 Detector 본 학습 (랩탑 → 데스크톱)

작성일: 2026-06-20
인계 사유: 랩탑 RAM 16GB로 Faster R-CNN 학습 중 메모리 오버플로로 다운. 데스크톱(더 큰 RAM/GPU)에서 본 학습과 수렴 확인을 이어간다.

---

## 0. 한 줄 요약

`phase7/ml-detector-training` 브랜치에서 `generate → train → infer → eval` 루프는 이미 코드로 닫혀 있고 랩탑에서 1-epoch 스모크까지 통과했다. 데스크톱에서 할 일은 **본 학습을 돌려 수렴 여부를 확인**하는 것 하나다.

## 1. 현재 상태 (랩탑에서 완료된 것)

- 브랜치 `phase7/ml-detector-training`이 `origin`에 푸시됨 (커밋 4개, `main` 기준 ahead 4).
  - `3f07f0e` Phase 7 ML bootstrap + contract tests
  - `79633da` synthetic ppt-render dataset generator
  - `97c7966` domain metrics (attachment accuracy + structural exactness)
  - `90f243d` Lightning 학습 루프 + soffice 렌더러
- 전체 테스트 71개 통과 (실제 1-epoch CPU 학습 스모크 포함).
- `plan.md`가 source of truth. Phase 7의 6개 task 모두 완료로 기록됨.
- 학습 데이터셋은 **커밋하지 않음** (seed 고정이라 재생성 가능). 랩탑의 `workbench-ml/`은 로컬 전용.

## 2. 미해결/이번에 할 일

- [ ] 본 학습 run으로 detector 수렴 확인 (랩탑은 RAM 부족으로 미실행)
- [ ] 수렴 판정 후 결과(run manifest + eval 요약 + tensorboard 로그)를 회수
- 수렴이 확인되면 다음 후보: detector 추론을 v3 `FAMILY_DETECT` stage에 주입하는 경로 설계 / generator family coverage 확장 (Phase 8 연동)

## 3. 환경 셋업 (데스크톱)

```bash
git fetch origin
git checkout phase7/ml-detector-training
git pull

# 가상환경에서
pip install -e ".[ml,test]"     # torch, torchvision, lightning, torchmetrics, tensorboard 등
python -m pytest -q             # 71개 통과 확인 (셋업 검증)
```

torchvision Faster R-CNN은 `weights=None`으로 초기화되므로 인터넷 없이도 학습된다 (사전학습 가중치 다운로드 없음).

## 4. 본 학습 실행

데이터셋은 seed 고정이라 어디서 생성하든 동일하다.

```bash
# 1) 데이터셋 생성 (랩탑과 동일 산출물)
python -m image_to_editable_ppt.ml.generate_dataset \
  --output-dir workbench-ml/ds-v1 --count 400 --seed 7 \
  --image-width 640 --image-height 360 --no-pptx
# 더 큰 학습을 원하면 --count 2000 등으로 늘려도 됨 (seed만 기록해두기)

# 2) 학습 (GPU면 --accelerator gpu, RAM 여유에 따라 batch 조절)
python -m image_to_editable_ppt.ml.train_detector \
  --dataset-dir workbench-ml/ds-v1 \
  --output-dir workbench-ml/run-v1 \
  --batch-size 8 --max-epochs 20 \
  --accelerator auto --tracking-backend tensorboard

# 3) 학습 곡선 보기
tensorboard --logdir workbench-ml/run-v1
```

메모리 주의: 랩탑(16GB)에서 batch 4 + 640x360에서도 다운됐다. 데스크톱 RAM/VRAM에 맞춰 `--batch-size`를 조절하고, 부족하면 `--image-width/--image-height`를 낮추거나 `--limit-train-batches`로 우선 작게 검증.

## 5. 수렴 확인

```bash
# run manifest에서 checkpoint 경로 확인
cat workbench-ml/run-v1/train_detector_run.json   # checkpoint.last / final_metrics

# test 샘플 하나 추론 → GT 평가
SAMPLE_ID=<workbench-ml/ds-v1/test 의 한 파일 stem>
python -m image_to_editable_ppt.ml.infer_detector \
  --image-id "$SAMPLE_ID" \
  --image-path "workbench-ml/ds-v1/test/$SAMPLE_ID.png" \
  --checkpoint workbench-ml/run-v1/checkpoints/last.ckpt \
  --score-threshold 0.5 \
  --output-json /tmp/pred.json --family orthogonal_flow --validate-ir

python -m image_to_editable_ppt.ml.eval_detector \
  --predictions-json /tmp/pred.json \
  --ground-truth-json "workbench-ml/ds-v1/test/$SAMPLE_ID.json"
```

**수렴 판정 기준**

- `val_loss`가 안정적으로 감소 (tensorboard).
- test 샘플에서 `node_f1`이 0을 벗어나 상승. synthetic 데이터가 단순하므로, 파이프라인이 정상이면 node F1은 충분히 높게(>0.8 목표) 나와야 한다.
- `structural_exact`가 일부 샘플에서 true로 나오기 시작하면 매우 양호.
- node F1이 계속 0이면 수렴 실패 — label space(`ml/dataset.py`), box 좌표계(image-space px), score threshold부터 점검.

## 6. 결과 회수 (분석은 랩탑 세션에서 이어받음)

아래만 있으면 충분하다 (대용량 checkpoint/데이터는 불필요):

- `workbench-ml/run-v1/train_detector_run.json` (config + dataset 정체성 + final_metrics + checkpoint 경로)
- eval CLI 출력(JSON) 1~수 개
- tensorboard `metrics.csv` 또는 스크린샷

이 파일들을 랩탑 세션에 전달하면 수렴 분석과 다음 단계를 이어간다.

## 7. 핵심 파일 지도

- `src/image_to_editable_ppt/ml/synthesize.py` — SyntheticSlideSpec, PIL/soffice 렌더, pptx writer, GT 생성
- `src/image_to_editable_ppt/ml/generate_dataset.py` — 데이터셋 CLI + manifest
- `src/image_to_editable_ppt/ml/dataset.py` — torch Dataset, node/container 공유 label space
- `src/image_to_editable_ppt/ml/lightning_module.py` — Faster R-CNN LightningModule
- `src/image_to_editable_ppt/ml/train_detector.py` — 학습 루프 + run manifest
- `src/image_to_editable_ppt/ml/infer_detector.py` — checkpoint 추론 → annotation → v3 IR
- `src/image_to_editable_ppt/ml/eval_detector.py` + `metrics.py` — 도메인 metrics
- `tests/test_v3_phase7*.py` — contract / dataset / training 회귀 테스트
