"""Train the learned node/container detector on a synthetic dataset.

Consumes a dataset directory produced by
``image-to-editable-ppt-generate-dataset`` and runs a Lightning training
loop over the Faster R-CNN detector. Every run writes
``train_detector_run.json`` capturing config, dataset manifest identity,
final metrics, and the checkpoint path so experiments stay reproducible.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True, frozen=True)
class TrainDetectorConfig:
    dataset_dir: Path
    output_dir: Path
    experiment_name: str
    batch_size: int
    max_epochs: int
    learning_rate: float
    num_workers: int
    accelerator: str
    tracking_backend: str
    seed: int
    limit_train_batches: float | None
    limit_val_batches: float | None


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train the learned detector on a synthetic dataset.")
    parser.add_argument("--dataset-dir", type=Path, required=True, help="Dataset root containing dataset_manifest.json.")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory for run manifest, logs, and checkpoints.")
    parser.add_argument("--experiment-name", default="phase7_detector", help="Logical experiment name.")
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--max-epochs", type=int, default=10)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--num-workers", type=int, default=0, help="Data loader worker count.")
    parser.add_argument("--accelerator", choices=("auto", "cpu", "gpu", "mps"), default="auto")
    parser.add_argument("--tracking-backend", choices=("none", "csv", "tensorboard"), default="csv")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--limit-train-batches", type=float, help="Optional Lightning train batch limit (for smoke runs).")
    parser.add_argument("--limit-val-batches", type=float, help="Optional Lightning val batch limit.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    config = TrainDetectorConfig(
        dataset_dir=args.dataset_dir,
        output_dir=args.output_dir,
        experiment_name=args.experiment_name,
        batch_size=args.batch_size,
        max_epochs=args.max_epochs,
        learning_rate=float(args.learning_rate),
        num_workers=args.num_workers,
        accelerator=args.accelerator,
        tracking_backend=args.tracking_backend,
        seed=args.seed,
        limit_train_batches=args.limit_train_batches,
        limit_val_batches=args.limit_val_batches,
    )

    manifest_path = config.dataset_dir / "dataset_manifest.json"
    if not manifest_path.exists():
        parser.error(f"dataset manifest does not exist: {manifest_path}")
    if config.batch_size <= 0 or config.max_epochs <= 0 or config.num_workers < 0:
        parser.error("batch-size and max-epochs must be positive; num-workers must be non-negative")
    if config.learning_rate <= 0:
        parser.error("learning-rate must be positive")

    run_manifest = train_detector(config)
    run_manifest_path = config.output_dir / "train_detector_run.json"
    print(f"wrote training run manifest to {run_manifest_path}")
    print(json.dumps({"status": run_manifest["status"], "final_metrics": run_manifest["final_metrics"]}, indent=2))
    return 0


def train_detector(config: TrainDetectorConfig) -> dict[str, object]:
    import lightning as L
    from lightning.pytorch.callbacks import ModelCheckpoint
    from torch.utils.data import DataLoader

    from image_to_editable_ppt.ml.dataset import DetectorTorchDataset, detection_collate
    from image_to_editable_ppt.ml.lightning_module import DetectorLightningModule

    L.seed_everything(config.seed, workers=True)

    train_dataset = DetectorTorchDataset(config.dataset_dir, split="train")
    if len(train_dataset) == 0:
        raise ValueError(f"no train split samples in {config.dataset_dir}")
    val_dataset = DetectorTorchDataset(config.dataset_dir, split="val")

    def loader(dataset: DetectorTorchDataset, *, shuffle: bool) -> DataLoader:
        return DataLoader(
            dataset,
            batch_size=config.batch_size,
            shuffle=shuffle,
            num_workers=config.num_workers,
            collate_fn=detection_collate,
        )

    module = DetectorLightningModule(learning_rate=config.learning_rate)
    checkpoint_callback = ModelCheckpoint(
        dirpath=config.output_dir / "checkpoints",
        filename="detector-{epoch:02d}",
        save_last=True,
    )
    trainer = L.Trainer(
        accelerator=config.accelerator,
        max_epochs=config.max_epochs,
        default_root_dir=config.output_dir,
        logger=_build_logger(config),
        callbacks=[checkpoint_callback],
        limit_train_batches=config.limit_train_batches if config.limit_train_batches is not None else 1.0,
        limit_val_batches=config.limit_val_batches if config.limit_val_batches is not None else 1.0,
        log_every_n_steps=1,
        enable_progress_bar=False,
    )
    trainer.fit(
        module,
        train_dataloaders=loader(train_dataset, shuffle=True),
        val_dataloaders=loader(val_dataset, shuffle=False) if len(val_dataset) > 0 else None,
    )

    dataset_manifest = json.loads((config.dataset_dir / "dataset_manifest.json").read_text(encoding="utf-8"))
    final_metrics = {name: float(value) for name, value in trainer.callback_metrics.items()}
    payload: dict[str, object] = {
        "status": "trained",
        "stage": "phase7_ml_experiment_bootstrap",
        "experiment_name": config.experiment_name,
        "config": {
            "dataset_dir": str(config.dataset_dir),
            "output_dir": str(config.output_dir),
            "batch_size": config.batch_size,
            "max_epochs": config.max_epochs,
            "learning_rate": config.learning_rate,
            "num_workers": config.num_workers,
            "accelerator": config.accelerator,
            "tracking_backend": config.tracking_backend,
            "seed": config.seed,
            "limit_train_batches": config.limit_train_batches,
            "limit_val_batches": config.limit_val_batches,
        },
        "dataset": {
            "schema_version": dataset_manifest.get("schema_version"),
            "generator": dataset_manifest.get("generator"),
            "split_counts": dataset_manifest.get("split_counts"),
            "family_counts": dataset_manifest.get("family_counts"),
        },
        "final_metrics": final_metrics,
        "checkpoint": {
            "best": checkpoint_callback.best_model_path or None,
            "last": checkpoint_callback.last_model_path or None,
        },
        "optional_dependency_availability": _optional_dependency_availability(),
    }
    config.output_dir.mkdir(parents=True, exist_ok=True)
    (config.output_dir / "train_detector_run.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def _build_logger(config: TrainDetectorConfig):
    if config.tracking_backend == "csv":
        from lightning.pytorch.loggers import CSVLogger

        return CSVLogger(save_dir=config.output_dir, name=config.experiment_name)
    if config.tracking_backend == "tensorboard":
        from lightning.pytorch.loggers import TensorBoardLogger

        return TensorBoardLogger(save_dir=config.output_dir, name=config.experiment_name)
    return False


def _optional_dependency_availability() -> dict[str, bool]:
    packages = ("torch", "torchvision", "lightning", "torchmetrics", "omegaconf", "tensorboard", "mlflow")
    return {name: importlib.util.find_spec(name) is not None for name in packages}


if __name__ == "__main__":
    raise SystemExit(main())
