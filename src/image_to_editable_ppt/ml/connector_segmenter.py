"""Pixel-wise connector segmentation (U-Net).

Connectors are thin, elongated strokes that anchor-box detectors handle poorly.
This module trains a small from-scratch U-Net to paint connector pixels, then
extracts connector instances from the predicted mask and attaches each endpoint
to the nearest detected node. Ground-truth masks are rasterized on the fly from
the synthetic annotation's connector ``path_points`` (no extra files).

Public surface:
- ``ConnectorSegModule`` — the Lightning module (load checkpoints from it).
- ``train_connector_segmenter`` / ``main`` — training CLI.
- ``segment_connector_mask`` — checkpoint-backed mask inference for one image.
- ``rasterize_connector_mask`` — GT mask from an annotation document.
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
from PIL import Image, ImageDraw
from torch.utils.data import DataLoader, Dataset

from image_to_editable_ppt.ml.annotation_schema import (
    AnnotationBBox,
    AnnotationConnectorCandidate,
    AnnotationConnectorEndpoint,
    AnnotationNode,
    AnnotationPoint,
    AnnotationPort,
    DetectorAnnotationDocument,
)
from image_to_editable_ppt.v3.core.enums import ConnectorKind, PortOwnerKind, PortSide

STROKE_WIDTH = 3  # matches the synthetic renderer's connector stroke
_DOWNSAMPLE = 8  # U-Net depth-3; inputs are padded to a multiple of this


# --------------------------------------------------------------------------- #
# Ground-truth mask
# --------------------------------------------------------------------------- #


def rasterize_connector_mask(document: DetectorAnnotationDocument, *, width: int, height: int) -> np.ndarray:
    """Binary (H, W) float32 mask of connector strokes from path_points."""
    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    scene = document.primitive_scene
    if scene is not None:
        for connector in scene.connector_candidates:
            points = [(point.x, point.y) for point in connector.effective_path_points()]
            if len(points) >= 2:
                draw.line(points, fill=1, width=STROKE_WIDTH)
    return np.asarray(mask, dtype=np.float32)


# --------------------------------------------------------------------------- #
# Model
# --------------------------------------------------------------------------- #


def _gn(channels: int) -> nn.GroupNorm:
    return nn.GroupNorm(num_groups=min(8, channels), num_channels=channels)


def _conv_block(in_ch: int, out_ch: int) -> nn.Sequential:
    return nn.Sequential(
        nn.Conv2d(in_ch, out_ch, kernel_size=3, padding=1),
        _gn(out_ch),
        nn.ReLU(inplace=True),
        nn.Conv2d(out_ch, out_ch, kernel_size=3, padding=1),
        _gn(out_ch),
        nn.ReLU(inplace=True),
    )


class _UNet(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.enc1 = _conv_block(3, 16)
        self.enc2 = _conv_block(16, 32)
        self.enc3 = _conv_block(32, 64)
        self.bottleneck = _conv_block(64, 128)
        self.pool = nn.MaxPool2d(2)
        self.up3 = nn.ConvTranspose2d(128, 64, kernel_size=2, stride=2)
        self.dec3 = _conv_block(128, 64)
        self.up2 = nn.ConvTranspose2d(64, 32, kernel_size=2, stride=2)
        self.dec2 = _conv_block(64, 32)
        self.up1 = nn.ConvTranspose2d(32, 16, kernel_size=2, stride=2)
        self.dec1 = _conv_block(32, 16)
        self.head = nn.Conv2d(16, 1, kernel_size=1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        e1 = self.enc1(x)
        e2 = self.enc2(self.pool(e1))
        e3 = self.enc3(self.pool(e2))
        b = self.bottleneck(self.pool(e3))
        d3 = self.dec3(torch.cat([self.up3(b), e3], dim=1))
        d2 = self.dec2(torch.cat([self.up2(d3), e2], dim=1))
        d1 = self.dec1(torch.cat([self.up1(d2), e1], dim=1))
        return self.head(d1)


def _dice_loss(logits: torch.Tensor, target: torch.Tensor, *, eps: float = 1.0) -> torch.Tensor:
    probs = torch.sigmoid(logits)
    intersection = (probs * target).sum(dim=(1, 2, 3))
    union = probs.sum(dim=(1, 2, 3)) + target.sum(dim=(1, 2, 3))
    dice = (2.0 * intersection + eps) / (union + eps)
    return (1.0 - dice).mean()


class ConnectorSegModule(L.LightningModule):
    def __init__(self, *, learning_rate: float = 1e-3, pos_weight: float = 10.0) -> None:
        super().__init__()
        self.save_hyperparameters()
        self.model = _UNet()

    def forward(self, images: torch.Tensor) -> torch.Tensor:
        return self.model(images)

    def _loss(self, logits: torch.Tensor, masks: torch.Tensor) -> torch.Tensor:
        pos_weight = torch.tensor(self.hparams.pos_weight, device=logits.device)
        bce = F.binary_cross_entropy_with_logits(logits, masks, pos_weight=pos_weight)
        return bce + _dice_loss(logits, masks)

    @staticmethod
    def _dice_score(logits: torch.Tensor, masks: torch.Tensor) -> torch.Tensor:
        preds = (torch.sigmoid(logits) >= 0.5).float()
        intersection = (preds * masks).sum(dim=(1, 2, 3))
        union = preds.sum(dim=(1, 2, 3)) + masks.sum(dim=(1, 2, 3))
        return ((2.0 * intersection + 1.0) / (union + 1.0)).mean()

    def training_step(self, batch, batch_idx: int) -> torch.Tensor:
        images, masks = batch
        logits = self.model(images)
        loss = self._loss(logits, masks)
        self.log("train_loss", loss, prog_bar=True, batch_size=len(images))
        return loss

    def validation_step(self, batch, batch_idx: int) -> torch.Tensor:
        images, masks = batch
        logits = self.model(images)
        loss = self._loss(logits, masks)
        self.log("val_loss", loss, prog_bar=True, batch_size=len(images))
        self.log("val_dice", self._dice_score(logits, masks), prog_bar=True, batch_size=len(images))
        return loss

    def configure_optimizers(self):
        return torch.optim.AdamW(self.parameters(), lr=self.hparams.learning_rate)


# --------------------------------------------------------------------------- #
# Dataset
# --------------------------------------------------------------------------- #


@dataclass(slots=True, frozen=True)
class _SegSample:
    image_path: Path
    annotation_path: Path


class ConnectorSegDataset(Dataset):
    def __init__(self, dataset_dir: Path, *, split: str) -> None:
        manifest = json.loads((dataset_dir / "dataset_manifest.json").read_text(encoding="utf-8"))
        self.samples = tuple(
            _SegSample(dataset_dir / item["image"], dataset_dir / item["annotation"])
            for item in manifest["samples"]
            if item["split"] == split
        )

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, index: int):
        sample = self.samples[index]
        with Image.open(sample.image_path) as image:
            rgb = image.convert("RGB")
            width, height = rgb.size
            array = np.asarray(rgb, dtype=np.float32) / 255.0
        image_tensor = _pad_to_multiple(torch.from_numpy(array).permute(2, 0, 1))
        document = DetectorAnnotationDocument.from_dict(
            json.loads(sample.annotation_path.read_text(encoding="utf-8"))
        )
        mask = rasterize_connector_mask(document, width=width, height=height)
        mask_tensor = _pad_to_multiple(torch.from_numpy(mask).unsqueeze(0))
        return image_tensor, mask_tensor


def _pad_to_multiple(tensor: torch.Tensor, *, multiple: int = _DOWNSAMPLE) -> torch.Tensor:
    _, height, width = tensor.shape
    pad_h = (multiple - height % multiple) % multiple
    pad_w = (multiple - width % multiple) % multiple
    if pad_h == 0 and pad_w == 0:
        return tensor
    return F.pad(tensor, (0, pad_w, 0, pad_h))


# --------------------------------------------------------------------------- #
# Inference
# --------------------------------------------------------------------------- #

_MODULE_CACHE: dict[str, ConnectorSegModule] = {}


def _load_module(checkpoint: str) -> ConnectorSegModule:
    cached = _MODULE_CACHE.get(checkpoint)
    if cached is not None:
        return cached
    module = ConnectorSegModule.load_from_checkpoint(checkpoint, map_location="cpu")
    module.eval()
    _MODULE_CACHE[checkpoint] = module
    return module


def segment_connector_mask(checkpoint: str, image: np.ndarray, *, threshold: float = 0.5) -> np.ndarray:
    """Binary connector mask (H, W) at the input image's native resolution."""
    array = np.asarray(image)
    if array.ndim == 2:
        array = np.stack([array, array, array], axis=-1)
    elif array.ndim == 3 and array.shape[2] == 1:
        array = np.repeat(array, 3, axis=2)
    array = array.astype(np.float32)
    if array.max() > 1.0:
        array = array / 255.0
    height, width = array.shape[:2]
    tensor = _pad_to_multiple(torch.from_numpy(array[..., :3]).permute(2, 0, 1)).unsqueeze(0)
    module = _load_module(checkpoint)
    with torch.no_grad():
        logits = module(tensor)
    probs = torch.sigmoid(logits)[0, 0, :height, :width].cpu().numpy()
    return (probs >= threshold).astype(np.uint8)


# --------------------------------------------------------------------------- #
# Instance extraction (mask -> connector candidates attached to nodes)
# --------------------------------------------------------------------------- #


def extract_connectors(
    mask: np.ndarray,
    nodes: tuple[AnnotationNode, ...],
    *,
    image_id: str,
    min_area: int = 12,
) -> tuple[tuple[AnnotationConnectorCandidate, ...], tuple[AnnotationPort, ...]]:
    """Turn a binary connector mask into connector candidates attached to nodes.

    Each connected component becomes one connector: its principal-axis extremes
    are the endpoints, oriented by reading order (left->right / top->bottom, the
    synthetic generator's convention since the mask carries no arrowhead), and
    each endpoint attaches to the nearest node with the matching side.
    """
    import cv2

    if len(nodes) < 2:
        return (), ()
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    # Collect raw candidates, then keep one per node-pair: a connector fragmented
    # by the mask into several components would otherwise emit duplicate edges.
    raw: dict[frozenset[str], dict] = {}
    for component in range(1, count):
        if stats[component, cv2.CC_STAT_AREA] < min_area:
            continue
        ys, xs = np.where(labels == component)
        if len(xs) < 2:
            continue
        start_xy, end_xy = _principal_extremes(xs.astype(np.float64), ys.astype(np.float64))
        start_owner = _nearest_node(nodes, start_xy)
        end_owner = _nearest_node(nodes, end_xy, exclude=start_owner)
        if start_owner is None or end_owner is None or start_owner.id == end_owner.id:
            continue
        span = (end_xy[0] - start_xy[0]) ** 2 + (end_xy[1] - start_xy[1]) ** 2
        key = frozenset({start_owner.id, end_owner.id})
        if key in raw and raw[key]["span"] >= span:
            continue
        pad = float(STROKE_WIDTH)
        raw[key] = {
            "span": span,
            "start_owner": start_owner,
            "end_owner": end_owner,
            "start_side": _side_toward(start_owner, start_xy),
            "end_side": _side_toward(end_owner, end_xy),
            "start_point": AnnotationPoint(float(start_xy[0]), float(start_xy[1])),
            "end_point": AnnotationPoint(float(end_xy[0]), float(end_xy[1])),
            # Pad to match the synthetic GT's _path_bbox(pad=3); the painted stroke
            # is only ~3px wide, so a tight box undershoots thin IoU at 0.5.
            "bbox": AnnotationBBox(
                x0=float(xs.min()) - pad, y0=float(ys.min()) - pad,
                x1=float(xs.max()) + pad, y1=float(ys.max()) + pad,
            ),
        }

    connectors: list[AnnotationConnectorCandidate] = []
    ports: list[AnnotationPort] = []
    for emitted, item in enumerate(raw.values()):
        connector_id = f"connector:{image_id}:{emitted}"
        connectors.append(
            AnnotationConnectorCandidate(
                id=connector_id,
                kind=ConnectorKind.ARROW,
                bbox=item["bbox"],
                confidence=1.0,
                source_evidence_id=f"evidence:{connector_id}",
                path_points=(item["start_point"], item["end_point"]),
                start_endpoint=AnnotationConnectorEndpoint(
                    point=item["start_point"], owner_id=item["start_owner"].id,
                    owner_kind=PortOwnerKind.NODE, side=item["start_side"],
                ),
                end_endpoint=AnnotationConnectorEndpoint(
                    point=item["end_point"], owner_id=item["end_owner"].id,
                    owner_kind=PortOwnerKind.NODE, side=item["end_side"],
                ),
                arrowhead_end=True,
                source="ml_segmenter",
                provenance=("ml_segmenter:connector_mask",),
            )
        )
        ports.append(_port(item["start_owner"].id, image_id, emitted, "start", item["start_side"], item["start_point"]))
        ports.append(_port(item["end_owner"].id, image_id, emitted, "end", item["end_side"], item["end_point"]))
    return tuple(connectors), tuple(ports)


def _principal_extremes(xs: np.ndarray, ys: np.ndarray) -> tuple[tuple[float, float], tuple[float, float]]:
    coords = np.stack([xs, ys], axis=1)
    centered = coords - coords.mean(axis=0)
    # Principal direction via the covariance's dominant eigenvector.
    cov = np.cov(centered, rowvar=False)
    eigvals, eigvecs = np.linalg.eigh(cov)
    direction = eigvecs[:, int(np.argmax(eigvals))]
    projection = centered @ direction
    a = coords[int(np.argmin(projection))]
    b = coords[int(np.argmax(projection))]
    # Orient by reading order along the dominant span (mask has no arrowhead).
    if abs(b[0] - a[0]) >= abs(b[1] - a[1]):
        start, end = (a, b) if a[0] <= b[0] else (b, a)
    else:
        start, end = (a, b) if a[1] <= b[1] else (b, a)
    return (float(start[0]), float(start[1])), (float(end[0]), float(end[1]))


def _nearest_node(
    nodes: tuple[AnnotationNode, ...], point: tuple[float, float], *, exclude: AnnotationNode | None = None
) -> AnnotationNode | None:
    best: AnnotationNode | None = None
    best_distance = float("inf")
    for node in nodes:
        if exclude is not None and node.id == exclude.id:
            continue
        bbox = node.bbox
        dx = max(bbox.x0 - point[0], 0.0, point[0] - bbox.x1)
        dy = max(bbox.y0 - point[1], 0.0, point[1] - bbox.y1)
        distance = dx * dx + dy * dy
        if distance < best_distance:
            best_distance = distance
            best = node
    return best


def _side_toward(node: AnnotationNode, point: tuple[float, float]) -> PortSide:
    center_x = (node.bbox.x0 + node.bbox.x1) / 2.0
    center_y = (node.bbox.y0 + node.bbox.y1) / 2.0
    dx = point[0] - center_x
    dy = point[1] - center_y
    if abs(dx) >= abs(dy):
        return PortSide.RIGHT if dx >= 0 else PortSide.LEFT
    return PortSide.BOTTOM if dy >= 0 else PortSide.TOP


def _port(owner_id: str, image_id: str, index: int, role: str, side: PortSide, point: AnnotationPoint) -> AnnotationPort:
    return AnnotationPort(
        id=f"port:{image_id}:{index}:{role}",
        owner_id=owner_id,
        owner_kind=PortOwnerKind.NODE,
        side=side,
        point=point,
        confidence=1.0,
        source="ml_segmenter",
        provenance=("ml_segmenter:port",),
    )


# --------------------------------------------------------------------------- #
# Training CLI
# --------------------------------------------------------------------------- #


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train the connector segmentation U-Net.")
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--max-epochs", type=int, default=20)
    parser.add_argument("--accelerator", default="auto")
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--pos-weight", type=float, default=10.0)
    parser.add_argument("--num-workers", type=int, default=0)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--limit-train-batches", type=float, default=None)
    parser.add_argument("--limit-val-batches", type=float, default=None)
    return parser


def train_connector_segmenter(args: argparse.Namespace) -> dict[str, object]:
    from lightning.pytorch.callbacks import ModelCheckpoint

    L.seed_everything(args.seed)
    train_loader = DataLoader(
        ConnectorSegDataset(args.dataset_dir, split="train"),
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=args.num_workers,
    )
    val_loader = DataLoader(
        ConnectorSegDataset(args.dataset_dir, split="val"),
        batch_size=args.batch_size,
        num_workers=args.num_workers,
    )
    module = ConnectorSegModule(learning_rate=args.learning_rate, pos_weight=args.pos_weight)
    checkpoint_dir = args.output_dir / "checkpoints"
    checkpoint_cb = ModelCheckpoint(dirpath=checkpoint_dir, filename="connector_seg-{epoch}", save_last=True)
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
        "stage": "phase8_connector_segmenter",
        "config": {
            "dataset_dir": str(args.dataset_dir),
            "batch_size": args.batch_size,
            "max_epochs": args.max_epochs,
            "learning_rate": args.learning_rate,
            "pos_weight": args.pos_weight,
            "seed": args.seed,
        },
        "final_metrics": metrics,
        "checkpoint": {
            "best": checkpoint_cb.best_model_path or None,
            "last": checkpoint_cb.last_model_path or None,
        },
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "train_connector_segmenter_run.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    if not (args.dataset_dir / "dataset_manifest.json").exists():
        parser.error(f"dataset manifest not found under {args.dataset_dir}")
    manifest = train_connector_segmenter(args)
    print(json.dumps({"status": manifest["status"], "final_metrics": manifest["final_metrics"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
