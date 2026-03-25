"""ImageToEditablePPT package.

The root package is now v3-first. The removed v2 runtime is available only in
git history; new work should use the `image_to_editable_ppt.v3` path.
"""

from .v3 import V3Config, V3ConversionResult, convert_image

__all__ = ["V3Config", "V3ConversionResult", "convert_image"]
