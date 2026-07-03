"""Merge a (possibly OCR-annotated) text layer into a provider-built SlideIR.

The ML SlideIR provider recovers structure only — its scene has no text. The
text branch stays a v3 concern, so after the provider runs, ``convert_image``
extracts the heuristic text layer (plus optional OCR) and merges it here:

- every text region becomes a ``PrimitiveText`` in the primitive scene;
- a region whose centre falls inside exactly one smallest node is *owned* by
  that node (``owner_ids``), and its recognized text is promoted to the node
  label so downstream emit can put it inside the shape;
- regions outside any node stay standalone (emit renders them as text boxes
  only when they carry recognized text).
"""
from __future__ import annotations

from dataclasses import replace

from image_to_editable_ppt.v3.ir.models import (
    PrimitiveNode,
    PrimitiveText,
    SlideIR,
    TextLayerResult,
    TextRegion,
)


def merge_text_layer_into_slide_ir(slide_ir: SlideIR, text_layer: TextLayerResult) -> SlideIR:
    scene = slide_ir.primitive_scene
    if scene is None or not text_layer.regions:
        return replace(slide_ir, text_layer=text_layer, text_regions=text_layer.regions)

    nodes_by_area = sorted(scene.nodes, key=lambda node: node.bbox.area)
    owner_by_region: dict[str, str] = {}
    for region in text_layer.regions:
        owner = _owning_node_id(region, nodes_by_area)
        if owner is not None:
            owner_by_region[region.id] = owner

    texts = tuple(
        PrimitiveText(
            id=region.id,
            role=region.role,
            bbox=region.bbox,
            confidence=region.confidence,
            text=region.text,
            owner_ids=(owner_by_region[region.id],) if region.id in owner_by_region else (),
            source=region.source,
            provenance=(*region.provenance, "merge_text:primitive_text"),
        )
        for region in text_layer.regions
    )

    labels: dict[str, list[TextRegion]] = {}
    for region in text_layer.regions:
        owner = owner_by_region.get(region.id)
        if owner is not None and region.text:
            labels.setdefault(owner, []).append(region)

    nodes = tuple(_labelled_node(node, labels.get(node.id)) for node in scene.nodes)
    merged_scene = replace(
        scene,
        nodes=nodes,
        texts=(*scene.texts, *texts),
        provenance=(*scene.provenance, "merge_text:text_layer"),
    )
    return replace(
        slide_ir,
        text_layer=text_layer,
        text_regions=text_layer.regions,
        primitive_scene=merged_scene,
    )


def _owning_node_id(region: TextRegion, nodes_by_area: list[PrimitiveNode]) -> str | None:
    center = region.bbox.center
    for node in nodes_by_area:  # smallest containing node wins
        if node.bbox.contains_point(center):
            return node.id
    return None


def _labelled_node(node: PrimitiveNode, regions: list[TextRegion] | None) -> PrimitiveNode:
    if not regions or node.label:
        return replace(node, text_region_ids=(*node.text_region_ids, *(r.id for r in regions or ()))) if regions else node
    ordered = sorted(regions, key=lambda region: (region.bbox.y0, region.bbox.x0))
    label = "\n".join(region.text for region in ordered if region.text)
    return replace(
        node,
        label=label or node.label,
        text_region_ids=(*node.text_region_ids, *(region.id for region in ordered)),
        provenance=(*node.provenance, "merge_text:label_from_ocr"),
    )
