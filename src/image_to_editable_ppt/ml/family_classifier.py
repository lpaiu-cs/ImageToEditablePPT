"""Learned diagram-family classifier.

A small from-scratch CNN that predicts the diagram family of a slide image, so
the FAMILY_DETECT stage no longer has to be told the family via a CLI flag (the
detector itself is family-blind). Trains fully offline over the synthetic
mixed-family dataset; the label space is the generator's ``SUPPORTED_FAMILIES``.

Public surface:
- ``FamilyClassifierModule`` — the Lightning module (load checkpoints from it).
- ``train_family_classifier`` / ``main`` — training CLI.
- ``classify_family`` — checkpoint-backed inference on a single image array.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import lightning as L
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image
from torch.utils.data import DataLoader, Dataset

from image_to_editable_ppt.ml.dataset import get_or_load
from image_to_editable_ppt.ml.synthesize import SUPPORTED_FAMILIES
from image_to_editable_ppt.v3.core.enums import DiagramFamily

# Class order tracks the generator's supported-family tuple; index == class label.
FAMILY_CLASS_ORDER: tuple[DiagramFamily, ...] = tuple(SUPPORTED_FAMILIES)
FAMILY_TO_INDEX: dict[DiagramFamily, int] = {family: index for index, family in enumerate(FAMILY_CLASS_ORDER)}
INPUT_SIZE = 128  # square resize fed to the CNN


def _build_cnn(num_classes: int) -> nn.Sequential:
    # GroupNorm (not BatchNorm) so train and eval use identical statistics — a
    # tiny CNN with BatchNorm collapsed in eval mode (val_acc ~chance) despite
    # perfect train accuracy.
    return nn.Sequential(
        nn.Conv2d(3, 16, kernel_size=3, stride=2, padding=1),
        nn.GroupNorm(4, 16),
        nn.ReLU(inplace=True),
        nn.Conv2d(16, 32, kernel_size=3, stride=2, padding=1),
        nn.GroupNorm(8, 32),
        nn.ReLU(inplace=True),
        nn.Conv2d(32, 64, kernel_size=3, stride=2, padding=1),
        nn.GroupNorm(8, 64),
        nn.ReLU(inplace=True),
        nn.AdaptiveAvgPool2d(1),
        nn.Flatten(),
        nn.Linear(64, num_classes),
    )


class FamilyClassifierModule(L.LightningModule):
    def __init__(self, *, num_classes: int = len(FAMILY_CLASS_ORDER), learning_rate: float = 1e-3) -> None:
        super().__init__()
        self.save_hyperparameters()
        self.model = _build_cnn(num_classes)

    def forward(self, images: torch.Tensor) -> torch.Tensor:
        return self.model(images)

    def _step(self, batch, stage: str) -> torch.Tensor:
        images, labels = batch
        logits = self.model(images)
        loss = F.cross_entropy(logits, labels)
        acc = (logits.argmax(dim=1) == labels).float().mean()
        self.log(f"{stage}_loss", loss, prog_bar=True, batch_size=len(images))
        self.log(f"{stage}_acc", acc, prog_bar=True, batch_size=len(images))
        return loss

    def training_step(self, batch, batch_idx: int) -> torch.Tensor:
        return self._step(batch, "train")

    def validation_step(self, batch, batch_idx: int) -> torch.Tensor:
        return self._step(batch, "val")

    def configure_optimizers(self):
        return torch.optim.AdamW(self.parameters(), lr=self.hparams.learning_rate)


_MODULE_CACHE: dict[str, FamilyClassifierModule] = {}


def _load_module(checkpoint: str) -> FamilyClassifierModule:
    def _load() -> FamilyClassifierModule:
        module = FamilyClassifierModule.load_from_checkpoint(checkpoint, map_location="cpu")
        module.eval()
        if module.hparams.num_classes != len(FAMILY_CLASS_ORDER):
            raise ValueError(
                f"family classifier checkpoint has {module.hparams.num_classes} classes but the current "
                f"FAMILY_CLASS_ORDER has {len(FAMILY_CLASS_ORDER)} ({[f.value for f in FAMILY_CLASS_ORDER]}); "
                "retrain the classifier on the current family set"
            )
        return module

    return get_or_load(_MODULE_CACHE, checkpoint, _load)


def _preprocess(image: np.ndarray) -> torch.Tensor:
    array = np.asarray(image)
    if array.ndim == 2:
        pil = Image.fromarray(array.astype(np.uint8), mode="L").convert("RGB")
    else:
        pil = Image.fromarray(array.astype(np.uint8)[..., :3], mode="RGB")
    pil = pil.resize((INPUT_SIZE, INPUT_SIZE))
    return torch.from_numpy(np.asarray(pil, dtype=np.float32) / 255.0).permute(2, 0, 1)


def classify_family(checkpoint: str, image: np.ndarray) -> tuple[DiagramFamily, float]:
    """Return the predicted family and its softmax probability for one image."""
    module = _load_module(checkpoint)
    tensor = _preprocess(image).unsqueeze(0)
    with torch.no_grad():
        probs = torch.softmax(module(tensor)[0], dim=0)
    index = int(probs.argmax())
    return FAMILY_CLASS_ORDER[index], float(probs[index])


# --------------------------------------------------------------------------- #
# Dataset + training
# --------------------------------------------------------------------------- #


@dataclass(slots=True, frozen=True)
class _ClassifierSample:
    image_path: Path
    label: int


def _build_torch_dataset(dataset_dir: Path, *, split: str) -> Dataset:
    manifest = json.loads((dataset_dir / "dataset_manifest.json").read_text(encoding="utf-8"))
    samples = tuple(
        _ClassifierSample(
            image_path=dataset_dir / item["image"],
            label=FAMILY_TO_INDEX[DiagramFamily(item["family"])],
        )
        for item in manifest["samples"]
        if item["split"] == split and DiagramFamily(item["family"]) in FAMILY_TO_INDEX
    )

    class FamilyClassifierDataset(Dataset):
        def __len__(self) -> int:
            return len(samples)

        def __getitem__(self, index: int):
            sample = samples[index]
            with Image.open(sample.image_path) as image:
                pil = image.convert("RGB").resize((INPUT_SIZE, INPUT_SIZE))
            tensor = torch.from_numpy(np.asarray(pil, dtype=np.float32) / 255.0).permute(2, 0, 1)
            return tensor, sample.label

    return FamilyClassifierDataset()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train the diagram-family classifier.")
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--max-epochs", type=int, default=15)
    parser.add_argument("--accelerator", default="auto")
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--num-workers", type=int, default=0)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--limit-train-batches", type=float, default=None)
    parser.add_argument("--limit-val-batches", type=float, default=None)
    return parser


def train_family_classifier(args: argparse.Namespace) -> dict[str, object]:
    from lightning.pytorch.callbacks import ModelCheckpoint

    L.seed_everything(args.seed)
    train_dataset = _build_torch_dataset(args.dataset_dir, split="train")
    val_dataset = _build_torch_dataset(args.dataset_dir, split="val")
    train_loader = DataLoader(
        train_dataset, batch_size=args.batch_size, shuffle=True, num_workers=args.num_workers
    )
    val_loader = DataLoader(val_dataset, batch_size=args.batch_size, num_workers=args.num_workers)

    module = FamilyClassifierModule(learning_rate=args.learning_rate)
    checkpoint_dir = args.output_dir / "checkpoints"
    checkpoint_cb = ModelCheckpoint(dirpath=checkpoint_dir, filename="family_classifier-{epoch}", save_last=True)
    trainer_kwargs: dict[str, object] = {
        "max_epochs": args.max_epochs,
        "accelerator": args.accelerator,
        "callbacks": [checkpoint_cb],
        "default_root_dir": str(args.output_dir),
        "logger": False,
    }
    if args.limit_train_batches is not None:
        trainer_kwargs["limit_train_batches"] = args.limit_train_batches
    if args.limit_val_batches is not None:
        trainer_kwargs["limit_val_batches"] = args.limit_val_batches
    trainer = L.Trainer(**trainer_kwargs)
    trainer.fit(module, train_loader, val_loader)

    metrics = {key: float(value) for key, value in trainer.callback_metrics.items()}
    manifest = {
        "status": "trained",
        "stage": "phase8_family_classifier",
        "families": [family.value for family in FAMILY_CLASS_ORDER],
        "config": {
            "dataset_dir": str(args.dataset_dir),
            "batch_size": args.batch_size,
            "max_epochs": args.max_epochs,
            "learning_rate": args.learning_rate,
            "seed": args.seed,
        },
        "final_metrics": metrics,
        "checkpoint": {
            "best": checkpoint_cb.best_model_path or None,
            "last": checkpoint_cb.last_model_path or None,
        },
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "train_family_classifier_run.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    if not (args.dataset_dir / "dataset_manifest.json").exists():
        parser.error(f"dataset manifest not found under {args.dataset_dir}")
    manifest = train_family_classifier(args)
    print(json.dumps({"status": manifest["status"], "final_metrics": manifest["final_metrics"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
