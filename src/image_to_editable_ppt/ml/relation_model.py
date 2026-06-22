"""Pairwise node-relation model: recover graph topology from line evidence.

The connector segmenter + heuristic extraction under-recovers edges on real
figures, which forced a brittle text-fraction shortcut for tree detection.
Reformulate edge recovery as *relation classification* over every unordered node
pair: ``{no edge, i->j, j->i}``. A pure image-crop model proved unreliable (it
guesses edges from geometry because a downsized crop loses the thin connecting
line), so the features are built from the segmenter's *line + arrowhead masks* —
the actual drawn-stroke evidence — sampled along the i–j segment, plus geometry.
Considering every pair independently (vs tracing merged line components) lifts
edge recall on crossing/long lines, and the line-coverage requirement keeps
precision honest: no stroke between two nodes -> no edge. The resulting directed
adjacency *derives* the family (tree = acyclic hierarchy, cycle = single ring,
graph = general) instead of asserting it from a surface proxy.

Public surface:
- ``segment_line_features`` — per-pair features from the line/arrow masks.
- ``RelationModule`` — the Lightning classifier.
- ``train_relation_model`` / ``main`` — training CLI (needs a segmenter checkpoint).
- ``predict_relations`` — masks + node boxes -> directed edges.
"""
from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import lightning as L
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image
from torch.utils.data import DataLoader, Dataset

from image_to_editable_ppt.ml.classical_connectors import (
    CANDIDATE_FEATURE_DIM,
    NO_CANDIDATE_FEATURES,
    candidate_features,
)
from image_to_editable_ppt.ml.dataset import get_or_load

GEOM_DIM = 9
LINE_DIM = 7
PATH_DIM = 2
CAND_DIM = CANDIDATE_FEATURE_DIM  # morphological-candidate geometry (existence + shape)
FEATURE_DIM = GEOM_DIM + LINE_DIM + PATH_DIM + CAND_DIM
NUM_CLASSES = 3  # 0 = no edge, 1 = i->j, 2 = j->i


@dataclass(slots=True, frozen=True)
class _Box:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2.0

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2.0


def _as_box(obj: object) -> _Box:
    b = getattr(obj, "bbox", obj)
    return _Box(b.x0, b.y0, b.x1, b.y1)  # type: ignore[attr-defined]


def _inside(box: _Box, x: float, y: float) -> bool:
    return box.x0 <= x <= box.x1 and box.y0 <= y <= box.y1


def pair_geometric_features(box_i: _Box, box_j: _Box, *, width: float, height: float) -> list[float]:
    diag = max(1.0, (width**2 + height**2) ** 0.5)
    dx, dy = (box_j.cx - box_i.cx), (box_j.cy - box_i.cy)
    span = abs(dx) + abs(dy) + 1e-6
    return [
        dx / max(1.0, width),
        dy / max(1.0, height),
        ((dx**2 + dy**2) ** 0.5) / diag,
        (box_i.x1 - box_i.x0) / max(1.0, width),
        (box_i.y1 - box_i.y0) / max(1.0, height),
        (box_j.x1 - box_j.x0) / max(1.0, width),
        (box_j.y1 - box_j.y0) / max(1.0, height),
        abs(dx) / span,
        abs(dy) / span,
    ]


def segment_line_features(
    line_mask: np.ndarray,
    arrow_mask: np.ndarray,
    box_i: _Box,
    box_j: _Box,
    *,
    occluders: Sequence[_Box] = (),
    n_samples: int = 28,
    radius: int = 3,
) -> list[float]:
    """Sample the segmenter line/arrowhead masks along the i->j segment.

    Returns [coverage, max_gap_frac, abs_coverage, arrow_near_i, arrow_near_j,
    occlusion, has_samples]. Coverage is the fraction of inter-node samples on a
    segmented connector stroke — the *honest* edge signal. ``occlusion`` is the
    fraction of the straight segment that passes through *other* nodes: real edges
    route around nodes, so a high value flags a spurious long-range pair that only
    looks connected because the straight line clips intervening boxes/arrows. (A
    raw image-darkness feature was tried for recall but rejected — it fired on any
    darkness; the segmenter mask is the learned line detector.)
    """
    h, w = line_mask.shape
    ci, cj = (box_i.cx, box_i.cy), (box_j.cx, box_j.cy)
    covered = total = occluded = 0
    cur_gap = max_gap = 0
    arrow_i = arrow_j = 0.0
    for k in range(n_samples + 1):
        t = k / n_samples
        x = ci[0] + (cj[0] - ci[0]) * t
        y = ci[1] + (cj[1] - ci[1]) * t
        if _inside(box_i, x, y) or _inside(box_j, x, y):
            continue
        total += 1
        if any(_inside(box, x, y) for box in occluders):
            occluded += 1
        xi, yi = int(round(x)), int(round(y))
        x0, x1 = max(0, xi - radius), min(w, xi + radius + 1)
        y0, y1 = max(0, yi - radius), min(h, yi + radius + 1)
        line_win = line_mask[y0:y1, x0:x1]
        if line_win.size > 0 and line_win.max() > 0:
            covered += 1
            cur_gap = 0
        else:
            cur_gap += 1
            max_gap = max(max_gap, cur_gap)
        arrow_win = arrow_mask[y0:y1, x0:x1]
        a = float(arrow_win.max()) if arrow_win.size > 0 else 0.0
        if t >= 0.65:
            arrow_j = max(arrow_j, a)
        if t <= 0.35:
            arrow_i = max(arrow_i, a)
    denom = max(1, total)
    return [
        covered / denom,
        max_gap / denom,
        covered / float(n_samples),
        arrow_i,
        arrow_j,
        occluded / denom,
        1.0 if total > 0 else 0.0,
    ]


def compute_node_components(
    line_mask: np.ndarray, boxes: Sequence[_Box], *, dilate_iter: int = 2, ring: int = 5
) -> tuple[list[set[int]], dict[int, int]]:
    """Label the line mask's connected strokes and, per node, the stroke labels that
    touch a ring around its box. ``fanout[label]`` = how many nodes that stroke
    touches (a clean connector touches 2; a merged/crossing blob touches more).

    This is the mask-path signal: two nodes joined by the *same* stroke component
    are connected along the actual (elbow) route, whereas an unrelated arrow that a
    straight segment merely clips is a different component touching only one of them.
    """
    from scipy import ndimage as ndi

    mask = line_mask > 0
    if dilate_iter:
        mask = ndi.binary_dilation(mask, iterations=dilate_iter)
    labels, _ = ndi.label(mask, structure=np.ones((3, 3), dtype=np.uint8))
    h, w = labels.shape
    node_labels: list[set[int]] = []
    label_nodes: dict[int, set[int]] = {}
    for idx, box in enumerate(boxes):
        x0, y0 = max(0, int(box.x0) - ring), max(0, int(box.y0) - ring)
        x1, y1 = min(w, int(box.x1) + ring), min(h, int(box.y1) + ring)
        region = labels[y0:y1, x0:x1]
        labs = {int(value) for value in np.unique(region) if value > 0}
        node_labels.append(labs)
        for label in labs:
            label_nodes.setdefault(label, set()).add(idx)
    fanout = {label: len(nodes) for label, nodes in label_nodes.items()}
    return node_labels, fanout


def path_features(labels_i: set[int], labels_j: set[int], fanout: dict[int, int]) -> list[float]:
    """[path_connected, clean_connector] from shared stroke components."""
    shared = labels_i & labels_j
    if not shared:
        return [0.0, 0.0]
    min_fanout = min(fanout.get(label, 99) for label in shared)
    # A clean connector's stroke touches just its two endpoints (fanout 2).
    return [1.0, 1.0 if min_fanout <= 3 else 0.0]


def pair_features(
    line_mask: np.ndarray,
    arrow_mask: np.ndarray,
    box_i: _Box,
    box_j: _Box,
    *,
    width: float,
    height: float,
    occluders: Sequence[_Box] = (),
    path_feats: Sequence[float] = (0.0, 0.0),
    cand_feats: Sequence[float] | None = None,
) -> list[float]:
    return (
        pair_geometric_features(box_i, box_j, width=width, height=height)
        + segment_line_features(line_mask, arrow_mask, box_i, box_j, occluders=occluders)
        + list(path_feats)
        + list(cand_feats if cand_feats is not None else NO_CANDIDATE_FEATURES)
    )


class RelationModule(L.LightningModule):
    def __init__(self, *, learning_rate: float = 1e-3, class_weights: tuple[float, float, float] | None = None) -> None:
        super().__init__()
        self.save_hyperparameters()
        self.head = nn.Sequential(
            nn.Linear(FEATURE_DIM, 64), nn.LayerNorm(64), nn.ReLU(inplace=True), nn.Dropout(0.1),
            nn.Linear(64, 64), nn.LayerNorm(64), nn.ReLU(inplace=True),
            nn.Linear(64, NUM_CLASSES),
        )

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        return self.head(features)

    def _step(self, batch, stage: str) -> torch.Tensor:
        features, labels = batch
        logits = self(features)
        weight = (
            torch.tensor(self.hparams.class_weights, dtype=logits.dtype, device=logits.device)
            if self.hparams.class_weights is not None
            else None
        )
        loss = F.cross_entropy(logits, labels, weight=weight)
        preds = logits.argmax(dim=1)
        self.log(f"{stage}_loss", loss, prog_bar=True, batch_size=len(labels))
        self.log(f"{stage}_acc", (preds == labels).float().mean(), prog_bar=True, batch_size=len(labels))
        if stage == "val":
            true_edge, pred_edge = labels > 0, preds > 0
            tp = (true_edge & pred_edge & (preds == labels)).sum().float()
            self.log("val_edge_recall", tp / true_edge.sum().clamp(min=1), prog_bar=True, batch_size=len(labels))
            self.log("val_edge_precision", tp / pred_edge.sum().clamp(min=1), prog_bar=True, batch_size=len(labels))
        return loss

    def training_step(self, batch, batch_idx: int) -> torch.Tensor:
        return self._step(batch, "train")

    def validation_step(self, batch, batch_idx: int) -> torch.Tensor:
        return self._step(batch, "val")

    def configure_optimizers(self):
        return torch.optim.Adam(self.parameters(), lr=self.hparams.learning_rate)


def _sample_pairs(document, image, line_mask, arrow_mask, *, width, height, rng: random.Random, neg_per_pos: int = 3):
    scene = document.primitive_scene
    nodes = list(scene.nodes)
    if len(nodes) < 2:
        return []
    index_of = {node.id: i for i, node in enumerate(nodes)}
    boxes = [_as_box(node) for node in nodes]
    directed: dict[tuple[int, int], int] = {}
    for connector in scene.connector_candidates:
        s = connector.start_endpoint.owner_id if connector.start_endpoint else None
        t = connector.end_endpoint.owner_id if connector.end_endpoint else None
        if s in index_of and t in index_of and index_of[s] != index_of[t]:
            directed[(index_of[s], index_of[t])] = 1
    node_labels, fanout = compute_node_components(line_mask, boxes)
    cand = candidate_features(image, nodes, list(scene.containers))
    pos, neg = [], []
    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            label = 1 if (i, j) in directed else (2 if (j, i) in directed else 0)
            occluders = [boxes[k] for k in range(len(nodes)) if k != i and k != j]
            feat = pair_features(
                line_mask, arrow_mask, boxes[i], boxes[j], width=width, height=height,
                occluders=occluders, path_feats=path_features(node_labels[i], node_labels[j], fanout),
                cand_feats=cand.get((i, j), NO_CANDIDATE_FEATURES),
            )
            (pos if label else neg).append((feat, label))
    rng.shuffle(neg)
    return pos + neg[: max(5, neg_per_pos * len(pos))]


def _masks_for_training(document, image, connector_source: str, connector_checkpoint: str | None):
    """Line/arrow masks for a synthetic training image: from the learned segmenter,
    or from classical detection (filtered with the sample's GT node/container boxes)."""
    if connector_source == "classical":
        from image_to_editable_ppt.ml.classical_connectors import classical_connector_masks

        scene = document.primitive_scene
        return classical_connector_masks(image, list(scene.nodes), list(scene.containers))
    from image_to_editable_ppt.ml.connector_segmenter import segment_connector_masks

    if not connector_checkpoint:
        raise ValueError("segmenter source requires --connector-checkpoint")
    return segment_connector_masks(connector_checkpoint, image)


class _RelationDataset(Dataset):
    def __init__(
        self,
        dataset_dir: Path,
        *,
        split: str,
        augment: bool,
        seed: int,
        connector_source: str = "segmenter",
        connector_checkpoint: str | None = None,
    ) -> None:
        from image_to_editable_ppt.ml.dataset import load_annotation_document

        manifest = json.loads((dataset_dir / "dataset_manifest.json").read_text(encoding="utf-8"))
        rng = random.Random(seed)
        self._rows: list[tuple[list[float], int]] = []
        for item in manifest["samples"]:
            if item["split"] != split:
                continue
            document = load_annotation_document(dataset_dir / item["annotation"])
            with Image.open(dataset_dir / item["image"]) as raw:
                image = np.asarray(raw.convert("RGB"), dtype=np.uint8)
            line, arrow = _masks_for_training(document, image, connector_source, connector_checkpoint)
            h, w = image.shape[:2]
            self._rows.extend(_sample_pairs(document, image, line, arrow, width=w, height=h, rng=rng))
        self._augment = augment

    def __len__(self) -> int:
        return len(self._rows)

    def __getitem__(self, index: int):
        feat, label = self._rows[index]
        array = np.asarray(feat, dtype=np.float32)
        if self._augment:
            array = array + np.random.normal(0.0, 0.02, array.shape).astype(np.float32)
        return torch.from_numpy(array), label

    def class_counts(self) -> tuple[int, int, int]:
        counts = [0, 0, 0]
        for _, label in self._rows:
            counts[label] += 1
        return tuple(counts)  # type: ignore[return-value]


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train the pairwise node-relation model.")
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument("--connector-source", choices=("segmenter", "classical"), default="classical",
                        help="Line/arrow mask source: classical CV detection (default) or the learned segmenter.")
    parser.add_argument("--connector-checkpoint", default=None, help="Segmenter checkpoint (required for --connector-source segmenter).")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--max-epochs", type=int, default=40)
    parser.add_argument("--accelerator", default="auto")
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--num-workers", type=int, default=0)
    parser.add_argument("--seed", type=int, default=7)
    return parser


def train_relation_model(args: argparse.Namespace) -> dict[str, object]:
    from lightning.pytorch.callbacks import ModelCheckpoint
    from lightning.pytorch.loggers import CSVLogger

    L.seed_everything(args.seed, workers=True)
    train_set = _RelationDataset(
        args.dataset_dir, split="train", augment=True, seed=args.seed,
        connector_source=args.connector_source, connector_checkpoint=args.connector_checkpoint,
    )
    val_set = _RelationDataset(
        args.dataset_dir, split="val", augment=False, seed=args.seed,
        connector_source=args.connector_source, connector_checkpoint=args.connector_checkpoint,
    )
    counts = train_set.class_counts()
    total = sum(counts) or 1
    class_weights = tuple(total / (NUM_CLASSES * c) if c else 0.0 for c in counts)
    train_loader = DataLoader(train_set, batch_size=args.batch_size, shuffle=True, num_workers=args.num_workers)
    val_loader = DataLoader(val_set, batch_size=args.batch_size, shuffle=False, num_workers=args.num_workers)
    module = RelationModule(learning_rate=args.learning_rate, class_weights=class_weights)
    checkpoint = ModelCheckpoint(dirpath=args.output_dir / "checkpoints", save_last=True, monitor="val_edge_recall", mode="max")
    trainer = L.Trainer(
        max_epochs=args.max_epochs, accelerator=args.accelerator, devices=1,
        logger=CSVLogger(save_dir=str(args.output_dir), name="logs"), callbacks=[checkpoint], enable_progress_bar=True,
    )
    trainer.fit(module, train_loader, val_loader)
    metrics = {key: float(value) for key, value in trainer.callback_metrics.items()}
    manifest = {
        "status": "trained",
        "config": {"train_pairs": len(train_set), "val_pairs": len(val_set), "class_counts": counts, "seed": args.seed},
        "final_metrics": metrics,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "train_relation_run.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


_MODULE_CACHE: dict[str, RelationModule] = {}


def _load_module(checkpoint: str) -> RelationModule:
    def _load() -> RelationModule:
        module = RelationModule.load_from_checkpoint(checkpoint, map_location="cpu")
        module.eval()
        return module

    return get_or_load(_MODULE_CACHE, checkpoint, _load)


@dataclass(slots=True, frozen=True)
class PredictedEdge:
    source: int
    target: int
    probability: float


def predict_relations(
    checkpoint: str,
    line_mask: np.ndarray,
    arrow_mask: np.ndarray,
    node_boxes: Sequence[object],
    *,
    width: float,
    height: float,
    threshold: float = 0.5,
    image: np.ndarray | None = None,
    container_boxes: Sequence[object] = (),
) -> list[PredictedEdge]:
    """Predict directed edges among detected nodes from the line/arrow masks plus the
    morphological-candidate geometry. ``image`` is needed for the candidate features;
    without it every pair falls back to the no-candidate sentinel."""
    module = _load_module(checkpoint)
    boxes = [_as_box(box) for box in node_boxes]
    pairs = [(i, j) for i in range(len(boxes)) for j in range(i + 1, len(boxes))]
    if not pairs:
        return []
    node_labels, fanout = compute_node_components(line_mask, boxes)
    cand = candidate_features(image, node_boxes, container_boxes) if image is not None else {}
    feats = torch.tensor(
        [
            pair_features(
                line_mask, arrow_mask, boxes[i], boxes[j], width=width, height=height,
                occluders=[boxes[k] for k in range(len(boxes)) if k != i and k != j],
                path_feats=path_features(node_labels[i], node_labels[j], fanout),
                cand_feats=cand.get((i, j), NO_CANDIDATE_FEATURES),
            )
            for i, j in pairs
        ],
        dtype=torch.float32,
    )
    with torch.no_grad():
        probs = F.softmax(module(feats), dim=1)
    edges: list[PredictedEdge] = []
    for (i, j), prob in zip(pairs, probs):
        p_ij, p_ji = float(prob[1]), float(prob[2])
        if max(p_ij, p_ji) >= threshold:
            edges.append(PredictedEdge(i, j, p_ij) if p_ij >= p_ji else PredictedEdge(j, i, p_ji))
    return edges


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    manifest = train_relation_model(args)
    print(json.dumps({"status": manifest["status"], "final_metrics": manifest["final_metrics"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
