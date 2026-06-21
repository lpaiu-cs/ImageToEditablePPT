"""Binary OOD gate: is this figure a (convertible) diagram, or not?

Papers are full of non-diagram figures — bar/line/scatter charts, confusion
matrices, screenshots, photos — and the rest of the pipeline will happily force
any of them into a diagram family. For real-paper precision the pipeline must be
able to *abstain*. This is a small pixel CNN trained on real ACL-fig diagrams
(positives) vs real ACL-fig charts/screenshots/photos (negatives); both sides are
real figures so it learns diagram-vs-not, not synthetic-vs-real.

Public surface:
- ``DiagramGateModule`` — the Lightning binary classifier.
- ``train_diagram_gate`` / ``main`` — training CLI over two image-dir trees.
- ``is_diagram`` — checkpoint-backed inference returning (keep, p_diagram).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import lightning as L
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image
from torch.utils.data import DataLoader, Dataset

from image_to_editable_ppt.ml.dataset import get_or_load

INPUT_SIZE = 160
_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp")


def _build_cnn() -> nn.Sequential:
    return nn.Sequential(
        nn.Conv2d(3, 16, 3, stride=2, padding=1), nn.GroupNorm(4, 16), nn.ReLU(inplace=True),
        nn.Conv2d(16, 32, 3, stride=2, padding=1), nn.GroupNorm(8, 32), nn.ReLU(inplace=True),
        nn.Conv2d(32, 64, 3, stride=2, padding=1), nn.GroupNorm(8, 64), nn.ReLU(inplace=True),
        nn.Conv2d(64, 64, 3, stride=2, padding=1), nn.GroupNorm(8, 64), nn.ReLU(inplace=True),
        nn.AdaptiveAvgPool2d(1), nn.Flatten(), nn.Dropout(0.2), nn.Linear(64, 2),
    )


def preprocess(rgb: np.ndarray) -> torch.Tensor:
    image = Image.fromarray(rgb).convert("RGB").resize((INPUT_SIZE, INPUT_SIZE))
    array = np.asarray(image, dtype=np.float32) / 255.0
    return torch.from_numpy(array).permute(2, 0, 1)


class DiagramGateModule(L.LightningModule):
    def __init__(self, *, learning_rate: float = 1e-3) -> None:
        super().__init__()
        self.save_hyperparameters()
        self.model = _build_cnn()

    def forward(self, images: torch.Tensor) -> torch.Tensor:
        return self.model(images)

    def _step(self, batch, stage: str) -> torch.Tensor:
        images, labels = batch
        logits = self.model(images)
        loss = F.cross_entropy(logits, labels)
        preds = logits.argmax(dim=1)
        acc = (preds == labels).float().mean()
        self.log(f"{stage}_loss", loss, prog_bar=True, batch_size=len(images))
        self.log(f"{stage}_acc", acc, prog_bar=True, batch_size=len(images))
        if stage == "val":
            # diagram == class 1; track recall (kept diagrams) and specificity (rejected non).
            pos = labels == 1
            neg = labels == 0
            recall = (preds[pos] == 1).float().mean() if pos.any() else torch.tensor(0.0)
            specificity = (preds[neg] == 0).float().mean() if neg.any() else torch.tensor(0.0)
            self.log("val_diagram_recall", recall, prog_bar=True, batch_size=len(images))
            self.log("val_nondiagram_reject", specificity, prog_bar=True, batch_size=len(images))
        return loss

    def training_step(self, batch, batch_idx: int) -> torch.Tensor:
        return self._step(batch, "train")

    def validation_step(self, batch, batch_idx: int) -> torch.Tensor:
        return self._step(batch, "val")

    def configure_optimizers(self):
        return torch.optim.Adam(self.parameters(), lr=self.hparams.learning_rate)


def _list_images(roots: list[Path]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        files.extend(p for p in root.rglob("*") if p.suffix.lower() in _IMAGE_EXTS)
    return sorted(files)


class _GateDataset(Dataset):
    def __init__(self, items: list[tuple[Path, int]], *, augment: bool) -> None:
        self._items = items
        self._augment = augment

    def __len__(self) -> int:
        return len(self._items)

    def __getitem__(self, index: int):
        import random

        path, label = self._items[index]
        with Image.open(path) as raw:
            image = raw.convert("RGB").resize((INPUT_SIZE, INPUT_SIZE))
        if self._augment:
            if random.random() < 0.5:
                image = image.transpose(Image.FLIP_LEFT_RIGHT)
            if random.random() < 0.3:
                image = image.transpose(Image.FLIP_TOP_BOTTOM)
            array = np.asarray(image, dtype=np.float32) / 255.0
            array = np.clip(array * random.uniform(0.85, 1.15) + random.uniform(-0.05, 0.05), 0.0, 1.0)
        else:
            array = np.asarray(image, dtype=np.float32) / 255.0
        return torch.from_numpy(array).permute(2, 0, 1), label


def _split_items(diagram_dirs: list[Path], nondiagram_dirs: list[Path], *, val_ratio: float, seed: int):
    import random

    rng = random.Random(seed)
    items = [(p, 1) for p in _list_images(diagram_dirs)] + [(p, 0) for p in _list_images(nondiagram_dirs)]
    rng.shuffle(items)
    cut = int(len(items) * (1.0 - val_ratio))
    return items[:cut], items[cut:]


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train the diagram / not-a-diagram OOD gate.")
    parser.add_argument("--diagram-dir", type=Path, action="append", required=True, help="Directory tree of diagram (positive) images; repeatable.")
    parser.add_argument("--nondiagram-dir", type=Path, action="append", required=True, help="Directory tree of non-diagram (negative) images; repeatable.")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--max-epochs", type=int, default=40)
    parser.add_argument("--accelerator", default="auto")
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--val-ratio", type=float, default=0.2)
    parser.add_argument("--num-workers", type=int, default=0)
    parser.add_argument("--seed", type=int, default=7)
    return parser


def train_diagram_gate(args: argparse.Namespace) -> dict[str, object]:
    from lightning.pytorch.callbacks import ModelCheckpoint
    from lightning.pytorch.loggers import CSVLogger

    L.seed_everything(args.seed, workers=True)
    train_items, val_items = _split_items(
        args.diagram_dir, args.nondiagram_dir, val_ratio=args.val_ratio, seed=args.seed
    )
    train_loader = DataLoader(
        _GateDataset(train_items, augment=True), batch_size=args.batch_size, shuffle=True, num_workers=args.num_workers
    )
    val_loader = DataLoader(
        _GateDataset(val_items, augment=False), batch_size=args.batch_size, shuffle=False, num_workers=args.num_workers
    )
    module = DiagramGateModule(learning_rate=args.learning_rate)
    checkpoint = ModelCheckpoint(dirpath=args.output_dir / "checkpoints", save_last=True, monitor="val_acc", mode="max")
    trainer = L.Trainer(
        max_epochs=args.max_epochs, accelerator=args.accelerator, devices=1,
        logger=CSVLogger(save_dir=str(args.output_dir), name="logs"), callbacks=[checkpoint], enable_progress_bar=True,
    )
    trainer.fit(module, train_loader, val_loader)
    metrics = {key: float(value) for key, value in trainer.callback_metrics.items()}
    manifest = {
        "status": "trained",
        "config": {"train": len(train_items), "val": len(val_items), "seed": args.seed},
        "final_metrics": metrics,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "train_diagram_gate_run.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


_MODULE_CACHE: dict[str, DiagramGateModule] = {}


def _load_module(checkpoint: str) -> DiagramGateModule:
    def _load() -> DiagramGateModule:
        module = DiagramGateModule.load_from_checkpoint(checkpoint, map_location="cpu")
        module.eval()
        return module

    return get_or_load(_MODULE_CACHE, checkpoint, _load)


def is_diagram(checkpoint: str, rgb: np.ndarray, *, threshold: float = 0.5) -> tuple[bool, float]:
    """Return (keep, p_diagram): keep is True when the figure looks like a diagram."""
    module = _load_module(checkpoint)
    with torch.no_grad():
        prob = float(F.softmax(module(preprocess(rgb).unsqueeze(0)), dim=1)[0, 1])
    return prob >= threshold, prob


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    manifest = train_diagram_gate(args)
    print(json.dumps({"status": manifest["status"], "final_metrics": manifest["final_metrics"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
