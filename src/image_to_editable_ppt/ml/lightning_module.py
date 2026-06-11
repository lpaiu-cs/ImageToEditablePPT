"""Lightning module for the learned node/container detector.

Wraps a torchvision Faster R-CNN (MobileNetV3 FPN backbone, no pretrained
weights so training is fully offline) over the shared node/container label
space defined in ``ml.dataset``. Validation reports the same multi-task
losses as training (the model is briefly switched to train mode without
gradients), so no external COCO tooling is required.
"""

from __future__ import annotations

import lightning as L
import torch
from torchvision.models.detection import fasterrcnn_mobilenet_v3_large_fpn

from image_to_editable_ppt.ml.dataset import NUM_DETECTION_CLASSES


class DetectorLightningModule(L.LightningModule):
    def __init__(self, *, num_classes: int = NUM_DETECTION_CLASSES, learning_rate: float = 1e-3) -> None:
        super().__init__()
        self.save_hyperparameters()
        self.model = fasterrcnn_mobilenet_v3_large_fpn(
            weights=None,
            weights_backbone=None,
            num_classes=num_classes,
        )

    def forward(self, images: list[torch.Tensor]) -> list[dict[str, torch.Tensor]]:
        self.model.eval()
        return self.model(images)

    def training_step(self, batch: tuple[list[torch.Tensor], list[dict[str, torch.Tensor]]], batch_idx: int) -> torch.Tensor:
        images, targets = batch
        loss_dict = self.model(images, targets)
        loss = torch.stack(list(loss_dict.values())).sum()
        self.log("train_loss", loss, prog_bar=True, batch_size=len(images))
        for name, value in loss_dict.items():
            self.log(f"train_{name}", value, batch_size=len(images))
        return loss

    def validation_step(self, batch: tuple[list[torch.Tensor], list[dict[str, torch.Tensor]]], batch_idx: int) -> torch.Tensor:
        images, targets = batch
        # Detection models only produce losses in train mode; flip mode
        # without gradients to reuse the same multi-task objective for val.
        self.model.train()
        with torch.no_grad():
            loss_dict = self.model(images, targets)
        self.model.eval()
        loss = torch.stack(list(loss_dict.values())).sum()
        self.log("val_loss", loss, prog_bar=True, batch_size=len(images))
        return loss

    def predict_step(
        self,
        batch: tuple[list[torch.Tensor], list[dict[str, torch.Tensor]]],
        batch_idx: int,
    ) -> list[dict[str, torch.Tensor]]:
        images, _ = batch
        return self(images)

    def configure_optimizers(self) -> torch.optim.Optimizer:
        return torch.optim.AdamW(self.parameters(), lr=self.hparams.learning_rate)
