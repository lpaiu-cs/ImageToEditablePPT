from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

from image_to_editable_ppt.v3.core.enums import DiagramFamily

if TYPE_CHECKING:
    from image_to_editable_ppt.v3.core.contracts import FamilyDetector, SlideIRProvider


DEFAULT_ENABLED_FAMILIES = frozenset(
    {
        DiagramFamily.ORTHOGONAL_FLOW,
    }
)


@dataclass(slots=True, frozen=True)
class V3Config:
    enabled_families: frozenset[DiagramFamily] = field(default_factory=lambda: DEFAULT_ENABLED_FAMILIES)
    strict_validation: bool = True
    emit_enabled: bool = False
    preserve_unresolved_residuals: bool = True
    soft_mask_text_in_structure: bool = True
    split_raster_early: bool = True
    keep_debug_stage_records: bool = True
    # Opt-in: when set, FAMILY_DETECT delegates to this detector instead of the
    # registered heuristic detectors. It is typed as the v3 FamilyDetector
    # protocol so the v3 package never depends on the ml package; the ml-backed
    # implementation (image_to_editable_ppt.ml.family_detector.MLFamilyDetector)
    # is constructed outside v3 and injected here.
    family_detector_override: "FamilyDetector | None" = None
    # Opt-in: when set, convert_image delegates the whole structure recovery to
    # this provider (e.g. the ML detector + classifier + connector segmenter) and
    # bypasses the heuristic family/connector stages. Injected from outside v3.
    slide_ir_provider: "SlideIRProvider | None" = None
    # Opt-in (Phase 10): restore editable text. The provider path additionally
    # runs the heuristic text branch and merges the regions into the SlideIR;
    # both paths annotate regions with OCR when a backend is installed. Regions
    # whose recognition falls below the confidence threshold keep text=None.
    recover_text: bool = False
    ocr_min_confidence: float = 0.6

    def family_enabled(self, family: DiagramFamily) -> bool:
        return family in self.enabled_families

    def with_family(self, family: DiagramFamily, *, enabled: bool) -> "V3Config":
        updated = set(self.enabled_families)
        if enabled:
            updated.add(family)
        else:
            updated.discard(family)
        return replace(self, enabled_families=frozenset(updated))
