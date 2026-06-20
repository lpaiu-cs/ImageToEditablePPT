"""Torch dataset over a generated synthetic detector dataset.

Loads samples from a ``dataset_manifest.json`` produced by
``image-to-editable-ppt-generate-dataset`` and yields torchvision detection
targets (boxes + labels). Node and container kinds share one label space so
a single detection head can localize both.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from torch.utils.data import Dataset

from image_to_editable_ppt.ml.annotation_schema import (
    AnnotationPrimitiveScene,
    DetectorAnnotationDocument,
)
from image_to_editable_ppt.v3.core.enums import ContainerKind, NodeKind

# Label 0 is reserved for background by torchvision detection heads.
NODE_KIND_LABELS: dict[NodeKind, int] = {kind: index + 1 for index, kind in enumerate(NodeKind)}
CONTAINER_KIND_LABELS: dict[ContainerKind, int] = {
    kind: index + 1 + len(NodeKind) for index, kind in enumerate(ContainerKind)
}
NUM_DETECTION_CLASSES = 1 + len(NodeKind) + len(ContainerKind)

_LABEL_TO_KIND: dict[int, NodeKind | ContainerKind] = {
    **{label: kind for kind, label in NODE_KIND_LABELS.items()},
    **{label: kind for kind, label in CONTAINER_KIND_LABELS.items()},
}


def label_to_kind(label: int) -> NodeKind | ContainerKind:
    kind = _LABEL_TO_KIND.get(label)
    if kind is None:
        raise ValueError(f"unknown detection label: {label}")
    return kind


def get_or_load(cache: dict, key: str, loader):
    """Return ``cache[key]``, computing it via ``loader()`` and storing it on a miss.

    Shared by the checkpoint caches in the inference modules. Note: never
    invalidated, which is fine for one-shot CLI processes but means a checkpoint
    retrained to the same path within a live process serves the stale model.
    """
    cached = cache.get(key)
    if cached is None:
        cached = loader()
        cache[key] = cached
    return cached


def to_rgb_chw_tensor(image: np.ndarray) -> torch.Tensor:
    """Image array -> float32 (3, H, W) tensor in [0, 1].

    Accepts grayscale (H, W), single-channel (H, W, 1), or RGB(A) arrays, and
    scales 0-255 inputs to [0, 1] (already-normalized arrays are left as-is).
    """
    array = np.asarray(image)
    if array.ndim == 2:
        array = np.stack([array, array, array], axis=-1)
    elif array.ndim == 3 and array.shape[2] == 1:
        array = np.repeat(array, 3, axis=2)
    array = array.astype(np.float32)
    if array.max() > 1.0:
        array = array / 255.0
    return torch.from_numpy(array[..., :3]).permute(2, 0, 1)


@dataclass(slots=True, frozen=True)
class DetectorSample:
    sample_id: str
    split: str
    image_path: Path
    annotation_path: Path


class DetectorTorchDataset(Dataset):
    """Detection dataset returning ``(image_tensor, target_dict)`` pairs."""

    def __init__(self, dataset_dir: Path, *, split: str) -> None:
        self.dataset_dir = Path(dataset_dir)
        manifest_path = self.dataset_dir / "dataset_manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"dataset manifest not found: {manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.samples = tuple(
            DetectorSample(
                sample_id=item["id"],
                split=item["split"],
                image_path=self.dataset_dir / item["image"],
                annotation_path=self.dataset_dir / item["annotation"],
            )
            for item in manifest["samples"]
            if item["split"] == split
        )
        self.split = split

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, dict[str, torch.Tensor]]:
        sample = self.samples[index]
        with Image.open(sample.image_path) as image:
            array = np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0
        image_tensor = torch.from_numpy(array).permute(2, 0, 1)

        document = load_annotation_document(sample.annotation_path)
        boxes, labels = document_to_detection_target(document)
        target = {
            "boxes": boxes,
            "labels": labels,
            "image_id": torch.tensor(index, dtype=torch.int64),
        }
        return image_tensor, target


def load_annotation_document(path: Path) -> DetectorAnnotationDocument:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return DetectorAnnotationDocument.from_dict(payload)


def document_to_detection_target(document: DetectorAnnotationDocument) -> tuple[torch.Tensor, torch.Tensor]:
    scene = document.primitive_scene or AnnotationPrimitiveScene()
    boxes: list[list[float]] = []
    labels: list[int] = []
    for node in scene.nodes:
        boxes.append([node.bbox.x0, node.bbox.y0, node.bbox.x1, node.bbox.y1])
        labels.append(NODE_KIND_LABELS[node.kind])
    for container in scene.containers:
        boxes.append([container.bbox.x0, container.bbox.y0, container.bbox.x1, container.bbox.y1])
        labels.append(CONTAINER_KIND_LABELS[container.kind])
    if not boxes:
        return (
            torch.zeros((0, 4), dtype=torch.float32),
            torch.zeros((0,), dtype=torch.int64),
        )
    return (
        torch.tensor(boxes, dtype=torch.float32),
        torch.tensor(labels, dtype=torch.int64),
    )


def detection_collate(
    batch: list[tuple[torch.Tensor, dict[str, torch.Tensor]]],
) -> tuple[list[torch.Tensor], list[dict[str, torch.Tensor]]]:
    images = [item[0] for item in batch]
    targets = [item[1] for item in batch]
    return images, targets
