"""Editable PPT emitters for v3."""

from .adapt import build_emit_scene
from .diff import EmitSceneDiff, diff_emit_scene
from .models import (
    EmitConnectorPrimitive,
    EmitResidualPrimitive,
    EmitScene,
    EmitShapePrimitive,
    EmitTextPrimitive,
)
from .pptx_writer import write_pptx
from .style import ShapeVisualStyle, sample_shape_styles

__all__ = [
    "EmitConnectorPrimitive",
    "EmitSceneDiff",
    "EmitResidualPrimitive",
    "EmitScene",
    "EmitShapePrimitive",
    "EmitTextPrimitive",
    "ShapeVisualStyle",
    "build_emit_scene",
    "diff_emit_scene",
    "sample_shape_styles",
    "write_pptx",
]
