from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, Sequence

from image_to_editable_ppt.v3.core.enums import StageName

if TYPE_CHECKING:
    from PIL import Image

    from image_to_editable_ppt.v3.app.config import V3Config
    from image_to_editable_ppt.v3.ir.models import (
        ConnectorEvidence,
        ConnectorSpec,
        DiagramInstance,
        FamilyProposal,
        MultiViewBundle,
        PortSpec,
        PrimitiveConnectorCandidate,
        PrimitiveScene,
        RasterLayerResult,
        ResidualCanvasResult,
        ResidualStructuralCanvas,
        ResidualRegion,
        StyleToken,
        TextLayerResult,
        UnattachedConnectorEvidence,
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
    def extract(self, bundle: "MultiViewBundle", *, config: "V3Config") -> "TextLayerResult": ...


class RasterExtractor(Protocol):
    def extract(
        self,
        bundle: "MultiViewBundle",
        *,
        text_layer: "TextLayerResult",
        config: "V3Config",
    ) -> "RasterLayerResult": ...


class FamilyDetector(Protocol):
    def detect(
        self,
        canvas: "ResidualStructuralCanvas",
        *,
        text_layer: "TextLayerResult",
        raster_layer: "RasterLayerResult",
        config: "V3Config",
    ) -> Sequence["FamilyProposal"]: ...


class FamilyParser(Protocol):
    def parse(
        self,
        canvas: "ResidualStructuralCanvas",
        *,
        proposals: Sequence["FamilyProposal"],
        text_layer: "TextLayerResult",
        raster_layer: "RasterLayerResult",
        config: "V3Config",
    ) -> Sequence["DiagramInstance"]: ...


class ConnectorResolver(Protocol):
    def resolve(
        self,
        *,
        connector_candidates: Sequence["PrimitiveConnectorCandidate"],
        config: "V3Config",
    ) -> Sequence["ConnectorSpec"]: ...


class ConnectorEvidenceExtractor(Protocol):
    def extract(
        self,
        canvas: "ResidualStructuralCanvas",
        *,
        instances: Sequence["DiagramInstance"],
        config: "V3Config",
    ) -> Sequence["ConnectorEvidence"]: ...


class PortGenerator(Protocol):
    def generate(
        self,
        *,
        instances: Sequence["DiagramInstance"],
        config: "V3Config",
    ) -> Sequence["PortSpec"]: ...


class ConnectorAttachmentBuilder(Protocol):
    def attach(
        self,
        *,
        connector_evidence: Sequence["ConnectorEvidence"],
        ports: Sequence["PortSpec"],
        config: "V3Config",
    ) -> tuple[Sequence["PrimitiveConnectorCandidate"], Sequence["UnattachedConnectorEvidence"]]: ...


class PrimitiveSceneMapper(Protocol):
    def build(
        self,
        bundle: "MultiViewBundle",
        *,
        text_layer: "TextLayerResult",
        raster_layer: "RasterLayerResult",
        residual_canvas: "ResidualCanvasResult",
        instances: Sequence["DiagramInstance"],
        ports: Sequence["PortSpec"],
        connector_candidates: Sequence["PrimitiveConnectorCandidate"],
        unattached_connector_evidence: Sequence["UnattachedConnectorEvidence"],
        residual_regions: Sequence["ResidualRegion"],
        config: "V3Config",
    ) -> "PrimitiveScene": ...


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
        text_layer: "TextLayerResult",
        raster_layer: "RasterLayerResult",
        config: "V3Config",
    ) -> "ResidualCanvasResult": ...
