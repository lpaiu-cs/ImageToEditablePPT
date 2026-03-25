from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, Sequence

from image_to_editable_ppt.v3.core.enums import StageName

if TYPE_CHECKING:
    from PIL import Image

    from image_to_editable_ppt.v3.app.config import V3Config
    from image_to_editable_ppt.v3.ir.models import (
        ConnectorSpec,
        DiagramInstance,
        FamilyProposal,
        MultiViewBundle,
        RasterRegion,
        ResidualRegion,
        StyleToken,
        TextRegion,
    )


class ContractViolationError(ValueError):
    """Raised when stage handoff data breaks an explicit contract."""


@dataclass(slots=True)
class StageRecord:
    stage: StageName
    summary: dict[str, object] = field(default_factory=dict)
    notes: tuple[str, ...] = ()


class MultiViewBuilder(Protocol):
    def build(self, image: "Image.Image", *, config: "V3Config") -> "MultiViewBundle": ...


class TextExtractor(Protocol):
    def extract(self, bundle: "MultiViewBundle", *, config: "V3Config") -> Sequence["TextRegion"]: ...


class RasterExtractor(Protocol):
    def extract(
        self,
        bundle: "MultiViewBundle",
        *,
        text_regions: Sequence["TextRegion"],
        config: "V3Config",
    ) -> Sequence["RasterRegion"]: ...


class FamilyDetector(Protocol):
    def detect(
        self,
        bundle: "MultiViewBundle",
        *,
        text_regions: Sequence["TextRegion"],
        raster_regions: Sequence["RasterRegion"],
        config: "V3Config",
    ) -> Sequence["FamilyProposal"]: ...


class FamilyParser(Protocol):
    def parse(
        self,
        bundle: "MultiViewBundle",
        *,
        proposals: Sequence["FamilyProposal"],
        text_regions: Sequence["TextRegion"],
        raster_regions: Sequence["RasterRegion"],
        config: "V3Config",
    ) -> Sequence["DiagramInstance"]: ...


class ConnectorResolver(Protocol):
    def resolve(
        self,
        bundle: "MultiViewBundle",
        *,
        instances: Sequence["DiagramInstance"],
        config: "V3Config",
    ) -> Sequence["ConnectorSpec"]: ...


class StyleResolver(Protocol):
    def resolve(
        self,
        bundle: "MultiViewBundle",
        *,
        instances: Sequence["DiagramInstance"],
        config: "V3Config",
    ) -> Sequence["StyleToken"]: ...


class ResidualComposer(Protocol):
    def compose(
        self,
        bundle: "MultiViewBundle",
        *,
        instances: Sequence["DiagramInstance"],
        text_regions: Sequence["TextRegion"],
        raster_regions: Sequence["RasterRegion"],
        config: "V3Config",
    ) -> Sequence["ResidualRegion"]: ...
