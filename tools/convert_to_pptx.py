"""Repo-local wrapper: convert a diagram image to an editable .pptx.

Usage (no install needed):
    py -3.12 tools/convert_to_pptx.py figure.png
    py -3.12 tools/convert_to_pptx.py data/paper_figures/architecture -o out/

Defaults --models-dir to <repo>/workbench-ml so the canonical checkpoints are
found when run from anywhere inside the repo.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

os.environ.setdefault("IEP_MODELS_DIR", str(ROOT / "workbench-ml"))

from image_to_editable_ppt.ml.convert_to_pptx import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
