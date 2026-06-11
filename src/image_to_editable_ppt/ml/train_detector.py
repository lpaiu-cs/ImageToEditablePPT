from __future__ import annotations

import argparse
import importlib.util
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True, frozen=True)
class TrainDetectorConfig:
    train_annotations: Path
    val_annotations: Path | None
    output_dir: Path
    experiment_name: str
    batch_size: int
    max_epochs: int
    num_workers: int
    accelerator: str
    tracking_backend: str
    seed: int


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bootstrap the learned detector training workflow.")
    parser.add_argument("--train-annotations", type=Path, required=True, help="Training annotation manifest or JSON path.")
    parser.add_argument("--val-annotations", type=Path, help="Validation annotation manifest or JSON path.")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory for experiment artifacts.")
    parser.add_argument("--experiment-name", default="phase7_detector_bootstrap", help="Logical experiment name.")
    parser.add_argument("--batch-size", type=int, default=4, help="Per-step batch size placeholder.")
    parser.add_argument("--max-epochs", type=int, default=10, help="Placeholder epoch count.")
    parser.add_argument("--num-workers", type=int, default=4, help="Data loader worker count.")
    parser.add_argument("--accelerator", choices=("auto", "cpu", "gpu", "mps"), default="auto")
    parser.add_argument("--tracking-backend", choices=("none", "tensorboard", "mlflow"), default="none")
    parser.add_argument("--seed", type=int, default=7, help="Bootstrap seed value.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    config = TrainDetectorConfig(
        train_annotations=args.train_annotations,
        val_annotations=args.val_annotations,
        output_dir=args.output_dir,
        experiment_name=args.experiment_name,
        batch_size=args.batch_size,
        max_epochs=args.max_epochs,
        num_workers=args.num_workers,
        accelerator=args.accelerator,
        tracking_backend=args.tracking_backend,
        seed=args.seed,
    )

    if not config.train_annotations.exists():
        parser.error(f"train annotation path does not exist: {config.train_annotations}")
    if config.val_annotations is not None and not config.val_annotations.exists():
        parser.error(f"validation annotation path does not exist: {config.val_annotations}")
    if config.batch_size <= 0 or config.max_epochs <= 0 or config.num_workers < 0:
        parser.error("batch-size, max-epochs, and num-workers must be non-negative with positive batch/epoch values")

    config.output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = config.output_dir / "train_detector_run.json"
    payload = {
        "status": "bootstrap_ready",
        "stage": "phase7_ml_experiment_bootstrap",
        "notes": [
            "Training orchestration is scaffolded, but model and datamodule implementation remain intentionally empty.",
            "Use this manifest as the integration point for Lightning modules, datasets, and tracker hooks.",
        ],
        "config": {
            "train_annotations": str(config.train_annotations),
            "val_annotations": None if config.val_annotations is None else str(config.val_annotations),
            "output_dir": str(config.output_dir),
            "experiment_name": config.experiment_name,
            "batch_size": config.batch_size,
            "max_epochs": config.max_epochs,
            "num_workers": config.num_workers,
            "accelerator": config.accelerator,
            "tracking_backend": config.tracking_backend,
            "seed": config.seed,
        },
        "optional_dependency_availability": _optional_dependency_availability(),
    }
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote training bootstrap manifest to {manifest_path}")
    return 0


def _optional_dependency_availability() -> dict[str, bool]:
    packages = ("torch", "torchvision", "lightning", "torchmetrics", "omegaconf", "tensorboard", "mlflow")
    return {name: importlib.util.find_spec(name) is not None for name in packages}


if __name__ == "__main__":
    raise SystemExit(main())
