from __future__ import annotations

from dataclasses import replace

from PIL import Image

from ..config import PipelineConfig
from ..detector import RefinedNode, refine_node_geometry
from ..schema import ObjectHypothesis
from ..vlm_parser import VLMNode


def hypothesis_to_refined_node(
    image: Image.Image,
    node: VLMNode,
    hypothesis: ObjectHypothesis,
    config: PipelineConfig,
    *,
    anchor_bbox=None,
) -> RefinedNode:
    proposal = replace(node, approx_bbox=hypothesis.bbox) if hypothesis.bbox is not None else node
    return refine_node_geometry(
        image,
        proposal,
        config,
        text_anchor=None if anchor_bbox is None else anchor_bbox.bbox,
    )
