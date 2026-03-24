from __future__ import annotations

from dataclasses import dataclass

from PIL import Image

from ..config import PipelineConfig
from ..detector import RefinedNode, verify_edge_exists
from ..graph import GraphBuildResult
from ..ir import Element
from ..router import generate_connections
from ..schema import DropReason, EmissionRecord
from ..vlm_parser import VLMEdge


@dataclass(slots=True)
class VerifiedConnectorSet:
    verified_edges: list[VLMEdge]
    dropped_records: list[EmissionRecord]


def verify_graph_connectors(
    image: Image.Image,
    nodes: list[RefinedNode],
    candidate_edges: list[VLMEdge],
    config: PipelineConfig,
) -> VerifiedConnectorSet:
    node_map = {node.id: node for node in nodes}
    verified: list[VLMEdge] = []
    dropped: list[EmissionRecord] = []
    for index, edge in enumerate(candidate_edges, start=1):
        source = node_map.get(edge.source)
        target = node_map.get(edge.target)
        if source is None or target is None:
            dropped.append(
                EmissionRecord(
                    id=f"emit-edge-drop:{index}",
                    kind="connector_drop",
                    bbox=None,
                    score_total=0.0,
                    score_terms={"missing_endpoint": 1.0},
                    source_ids=[edge.source, edge.target],
                    primitive_kind="connector",
                    object_type="connector",
                    hypothesis_ids=[edge.source, edge.target],
                    drop_reason=DropReason.NO_GEOMETRY_SUPPORT,
                )
            )
            continue
        if verify_edge_exists(
            image,
            source.exact_bbox,
            target.exact_bbox,
            config,
            expect_dashed=edge.type == "dashed_arrow",
        ):
            verified.append(edge)
            continue
        dropped.append(
            EmissionRecord(
                id=f"emit-edge-drop:{index}",
                kind="connector_drop",
                bbox=None,
                score_total=0.0,
                score_terms={"visual_verification_failed": 1.0},
                source_ids=[edge.source, edge.target],
                primitive_kind="connector",
                object_type="connector",
                hypothesis_ids=[edge.source, edge.target],
                drop_reason=DropReason.EDGE_NOT_VERIFIED,
            )
        )
    return VerifiedConnectorSet(verified_edges=verified, dropped_records=dropped)


def emit_connector_elements(
    nodes: list[RefinedNode],
    edges: list[VLMEdge],
    config: PipelineConfig,
) -> list[Element]:
    return generate_connections(nodes, edges, config)
