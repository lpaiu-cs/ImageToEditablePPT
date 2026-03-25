from __future__ import annotations

from dataclasses import dataclass

from image_to_editable_ppt.v3.app.config import V3Config
from image_to_editable_ppt.v3.core.contracts import FamilyDetector, FamilyParser
from image_to_editable_ppt.v3.core.enums import DiagramFamily
from image_to_editable_ppt.v3.ir.models import DiagramInstance, FamilyProposal, RasterLayerResult, ResidualStructuralCanvas, TextLayerResult

from .orthogonal_flow import OrthogonalFlowDetector, OrthogonalFlowParser


@dataclass(slots=True, frozen=True)
class FamilyDefinition:
    family: DiagramFamily
    detector: FamilyDetector
    parser: FamilyParser
    description: str


ORTHOGONAL_FLOW = FamilyDefinition(
    family=DiagramFamily.ORTHOGONAL_FLOW,
    detector=OrthogonalFlowDetector(),
    parser=OrthogonalFlowParser(),
    description="Residual-canvas-first orthogonal block flow skeleton.",
)

_REGISTRY = {
    ORTHOGONAL_FLOW.family: ORTHOGONAL_FLOW,
}


def get_family_registry() -> dict[DiagramFamily, FamilyDefinition]:
    return dict(_REGISTRY)


def iter_enabled_family_definitions(config: V3Config) -> tuple[FamilyDefinition, ...]:
    return tuple(definition for family, definition in _REGISTRY.items() if config.family_enabled(family))


def detect_family_proposals(
    canvas: ResidualStructuralCanvas,
    *,
    text_layer: TextLayerResult,
    raster_layer: RasterLayerResult,
    config: V3Config,
) -> tuple[FamilyProposal, ...]:
    proposals: list[FamilyProposal] = []
    for definition in iter_enabled_family_definitions(config):
        proposals.extend(
            definition.detector.detect(
                canvas,
                text_layer=text_layer,
                raster_layer=raster_layer,
                config=config,
            )
        )
    return tuple(proposals)


def parse_family_proposals(
    canvas: ResidualStructuralCanvas,
    *,
    proposals: tuple[FamilyProposal, ...],
    text_layer: TextLayerResult,
    raster_layer: RasterLayerResult,
    config: V3Config,
) -> tuple[DiagramInstance, ...]:
    proposals_by_family: dict[DiagramFamily, list[FamilyProposal]] = {}
    for proposal in proposals:
        if not config.family_enabled(proposal.family):
            continue
        proposals_by_family.setdefault(proposal.family, []).append(proposal)

    instances: list[DiagramInstance] = []
    for family, family_proposals in proposals_by_family.items():
        definition = _REGISTRY.get(family)
        if definition is None:
            continue
        instances.extend(
            definition.parser.parse(
                canvas,
                proposals=tuple(family_proposals),
                text_layer=text_layer,
                raster_layer=raster_layer,
                config=config,
            )
        )
    return tuple(instances)
