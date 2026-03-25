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

__all__ = [
    "EmitConnectorPrimitive",
    "EmitSceneDiff",
    "EmitResidualPrimitive",
    "EmitScene",
    "EmitShapePrimitive",
    "EmitTextPrimitive",
    "build_emit_scene",
    "diff_emit_scene",
]
