"""Conservative diagram-to-PPT pipeline."""

from .config import PipelineConfig
from .pipeline import ConversionResult, convert_image

__all__ = ["ConversionResult", "PipelineConfig", "convert_image"]
