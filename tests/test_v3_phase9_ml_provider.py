from __future__ import annotations

import numpy as np
from PIL import Image

from image_to_editable_ppt.ml.adapter import AnnotationMLAdapter, DetectorModelOutput
from image_to_editable_ppt.ml.annotation_schema import (
    AnnotationBBox,
    AnnotationFamilyProposal,
    AnnotationImageSize,
    AnnotationNode,
)
from image_to_editable_ppt.v3.app.config import V3Config
from image_to_editable_ppt.v3.app.convert import convert_image
from image_to_editable_ppt.v3.core.enums import DiagramFamily, NodeKind, StageName


class _StubProvider:
    """Minimal SlideIRProvider that ignores the image and returns a fixed SlideIR."""

    def __init__(self, slide_ir) -> None:
        self._slide_ir = slide_ir
        self.calls = 0

    def build(self, image, *, config):  # noqa: ANN001 - protocol signature
        self.calls += 1
        return self._slide_ir


def _stub_slide_ir(*, width: int, height: int):
    output = DetectorModelOutput(
        image_id="stub",
        image_size=AnnotationImageSize(width=width, height=height),
        family_predictions=(
            AnnotationFamilyProposal(
                id="family:cycle:0", family=DiagramFamily.CYCLE, confidence=0.9,
                focus_bbox=AnnotationBBox(10.0, 10.0, 60.0, 60.0), evidence=("ml",), provenance=("ml",),
            ),
        ),
        node_predictions=(
            AnnotationNode(
                id="node:stub:0", kind=NodeKind.BOX, bbox=AnnotationBBox(10.0, 10.0, 40.0, 40.0),
                confidence=0.9, source="ml", provenance=("ml",),
            ),
        ),
    )
    adapter = AnnotationMLAdapter()
    return adapter.to_slide_ir(adapter.from_model_output(output))


def test_convert_image_delegates_to_slide_ir_provider() -> None:
    width, height = 320, 240
    slide_ir = _stub_slide_ir(width=width, height=height)
    provider = _StubProvider(slide_ir)
    image = Image.fromarray(np.full((height, width, 3), 255, dtype=np.uint8), mode="RGB")

    result = convert_image(image, config=V3Config(slide_ir_provider=provider))

    assert provider.calls == 1
    assert result.slide_ir is slide_ir  # heuristic family/connector stages bypassed
    assert result.slide_ir.family_proposals[0].family is DiagramFamily.CYCLE
    assert len(result.slide_ir.primitive_scene.nodes) == 1
    stages = {record.stage for record in result.stage_records}
    assert StageName.MULTIVIEW in stages
    assert StageName.COMPOSE in stages


def test_convert_image_without_provider_uses_heuristic_path() -> None:
    image = Image.fromarray(np.full((240, 320, 3), 255, dtype=np.uint8), mode="RGB")
    result = convert_image(image, config=V3Config())  # no provider
    # blank image -> heuristic pipeline still produces a valid (empty) scene
    assert result.slide_ir.primitive_scene is not None


def test_ml_provider_abstains_on_ood_figure(monkeypatch) -> None:
    """When the diagram gate rejects a figure, the provider returns an empty,
    contract-valid scene (no nodes, no family) instead of fabricating a diagram —
    so a chart/screenshot/photo emits nothing rather than a spurious diagram."""
    import image_to_editable_ppt.ml.diagram_gate as gate
    from image_to_editable_ppt.ml.slide_ir_provider import MLSlideIRProvider

    monkeypatch.setattr(gate, "is_diagram", lambda checkpoint, rgb, *, threshold=0.5: (False, 0.02))
    provider = MLSlideIRProvider(detector_checkpoint="unused.ckpt", diagram_gate_checkpoint="gate.ckpt")
    image = Image.fromarray(np.full((240, 320, 3), 255, dtype=np.uint8), mode="RGB")

    slide_ir = provider.build(image, config=None)  # type: ignore[arg-type]

    assert slide_ir.primitive_scene is not None
    assert len(slide_ir.primitive_scene.nodes) == 0
    assert slide_ir.family_proposals == ()


def test_convert_image_provider_resolves_connector_candidates() -> None:
    """Provider emits connector *candidates*; convert must resolve them into
    ConnectorSpecs (emit reads slide_ir.connectors, not candidates)."""
    import random

    from image_to_editable_ppt.ml.synthesize import generate_slide_spec

    spec = generate_slide_spec(random.Random(3), sample_id="conn", family=DiagramFamily.ORTHOGONAL_FLOW)
    output = DetectorModelOutput(
        image_id=spec.sample_id,
        image_size=spec.image_size,
        family_predictions=(spec.family_proposal,),
        node_predictions=spec.nodes,
        port_predictions=tuple(
            port for connector in spec.connectors for port in (connector.start_port, connector.end_port)
        ),
        connector_predictions=tuple(connector.candidate for connector in spec.connectors),
    )
    adapter = AnnotationMLAdapter()
    slide_ir = adapter.to_slide_ir(adapter.from_model_output(output))
    assert slide_ir.connector_candidates  # adapter produced candidates...
    assert not slide_ir.connectors  # ...but leaves them unresolved (like the real provider)

    provider = _StubProvider(slide_ir)
    image = Image.fromarray(
        np.full((spec.image_size.height, spec.image_size.width, 3), 255, dtype=np.uint8), mode="RGB"
    )
    result = convert_image(image, config=V3Config(slide_ir_provider=provider))

    # convert resolved every candidate -> ConnectorSpecs that emit can render.
    assert len(result.slide_ir.connectors) == len(slide_ir.connector_candidates)
    assert StageName.CONNECTOR_RESOLVE in {record.stage for record in result.stage_records}
