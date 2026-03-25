"""Preprocessing entry points for v3."""

from .multiview import build_multiview_bundle
from .residual import build_residual_canvas

__all__ = ["build_multiview_bundle", "build_residual_canvas"]
