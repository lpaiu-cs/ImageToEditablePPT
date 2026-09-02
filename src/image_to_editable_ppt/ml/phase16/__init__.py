"""Phase 16 Multi-scale Evidence Graph experiment.

This namespace is intentionally opt-in.  Importing it must not alter the
frozen Phase 15 provider or the default conversion path.
"""

from .models import (
    ANNOTATION_SCHEMA_VERSION,
    MANIFEST_SCHEMA_VERSION,
    AnnotationDocument,
    BBox,
    ConnectorAnnotation,
    ExcludedRegionAnnotation,
    LabelAnnotation,
    RegionHypothesis,
    StructuralObjectAnnotation,
)
from .validation import ValidationError, validate_phase16_manifests

__all__ = [
    "ANNOTATION_SCHEMA_VERSION",
    "MANIFEST_SCHEMA_VERSION",
    "AnnotationDocument",
    "BBox",
    "ConnectorAnnotation",
    "ExcludedRegionAnnotation",
    "LabelAnnotation",
    "RegionHypothesis",
    "StructuralObjectAnnotation",
    "ValidationError",
    "validate_phase16_manifests",
]
