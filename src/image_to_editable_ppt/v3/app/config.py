from __future__ import annotations

from dataclasses import dataclass, field, replace

from image_to_editable_ppt.v3.core.enums import DiagramFamily


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

    def family_enabled(self, family: DiagramFamily) -> bool:
        return family in self.enabled_families

    def with_family(self, family: DiagramFamily, *, enabled: bool) -> "V3Config":
        updated = set(self.enabled_families)
        if enabled:
            updated.add(family)
        else:
            updated.discard(family)
        return replace(self, enabled_families=frozenset(updated))
