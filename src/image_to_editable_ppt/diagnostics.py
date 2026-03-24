from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Iterable

from PIL import Image

from .schema import StageEntity, as_serializable, validate_stage_entities


class DiagnosticsRecorder:
    enabled: bool = False
    base_path: Path | None = None

    def summary(self, stage: str, payload) -> None:
        return None

    def items(self, stage: str, name: str, rows: Iterable[object]) -> None:
        return None

    def overlay(self, stage: str, name: str, image: Image.Image) -> None:
        return None

    def artifact(self, stage: str, name: str, payload) -> None:
        return None


class NoOpDiagnosticsRecorder(DiagnosticsRecorder):
    pass


@dataclass(slots=True)
class FilesystemDiagnosticsRecorder(DiagnosticsRecorder):
    run_id: str
    slide_id: str = "slide"
    root_dir: Path = Path("artifacts") / "diagnostics"

    def __post_init__(self) -> None:
        self.enabled = True
        self.base_path = self.root_dir / self.run_id / self.slide_id
        self.base_path.mkdir(parents=True, exist_ok=True)

    def summary(self, stage: str, payload) -> None:
        stage_dir = self._stage_dir(stage)
        path = stage_dir / "summary.json"
        path.write_text(json.dumps(as_serializable(payload), indent=2), encoding="utf-8")

    def items(self, stage: str, name: str, rows: Iterable[object]) -> None:
        rows = list(rows)
        if rows and isinstance(rows[0], StageEntity):
            rows = validate_stage_entities(stage, name, rows)
        stage_dir = self._stage_dir(stage)
        path = stage_dir / f"{name}.jsonl"
        with path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(as_serializable(row), ensure_ascii=False) + "\n")

    def overlay(self, stage: str, name: str, image: Image.Image) -> None:
        stage_dir = self._stage_dir(stage)
        image.save(stage_dir / f"{name}.png")

    def artifact(self, stage: str, name: str, payload) -> None:
        stage_dir = self._stage_dir(stage)
        path = stage_dir / f"{name}.json"
        path.write_text(json.dumps(as_serializable(payload), indent=2), encoding="utf-8")

    def _stage_dir(self, stage: str) -> Path:
        path = self.base_path / stage
        path.mkdir(parents=True, exist_ok=True)
        return path


def build_recorder(
    *,
    enabled: bool,
    run_id: str,
    slide_id: str = "slide",
    root_dir: str | Path = Path("artifacts") / "diagnostics",
) -> DiagnosticsRecorder:
    if not enabled:
        return NoOpDiagnosticsRecorder()
    return FilesystemDiagnosticsRecorder(run_id=run_id, slide_id=slide_id, root_dir=Path(root_dir))


def write_manifest(
    base_path: str | Path,
    payload,
) -> None:
    path = Path(base_path) / "manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(as_serializable(payload), indent=2), encoding="utf-8")
