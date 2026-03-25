from __future__ import annotations

import numpy as np
from PIL import Image

from image_to_editable_ppt.v3.app.config import V3Config
from image_to_editable_ppt.v3.core.enums import BranchKind
from image_to_editable_ppt.v3.core.types import ImageSize
from image_to_editable_ppt.v3.ir.models import MultiViewBranch, MultiViewBundle


def build_multiview_bundle(image: Image.Image, *, config: V3Config | None = None) -> MultiViewBundle:
    del config
    rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    gray = np.asarray(image.convert("L"), dtype=np.uint8)
    soft_mask = np.zeros(gray.shape, dtype=np.float32)
    image_size = ImageSize(width=int(rgb.shape[1]), height=int(rgb.shape[0]))
    branches = {
        BranchKind.RGB: MultiViewBranch(
            kind=BranchKind.RGB,
            image=rgb,
            description="Source RGB image.",
        ),
        BranchKind.STYLE: MultiViewBranch(
            kind=BranchKind.STYLE,
            image=rgb.copy(),
            description="Style-preserving RGB branch.",
        ),
        BranchKind.TEXT: MultiViewBranch(
            kind=BranchKind.TEXT,
            image=gray.copy(),
            description="Text-sensitive grayscale branch.",
        ),
        BranchKind.STRUCTURE: MultiViewBranch(
            kind=BranchKind.STRUCTURE,
            image=gray.copy(),
            description="Structure-focused grayscale branch.",
        ),
        BranchKind.STRUCTURAL_CANVAS: MultiViewBranch(
            kind=BranchKind.STRUCTURAL_CANVAS,
            image=gray.copy(),
            description="Residual structural canvas before text or raster subtraction.",
            soft_mask=soft_mask,
        ),
    }
    return MultiViewBundle(image_size=image_size, branches=branches)
