from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from enum import StrEnum
from typing import Any

from .ir import BBox, Point


class SuppressionReason(StrEnum):
    DUPLICATE_LOWER_SCORE = "duplicate_lower_score"
    OVERLAP_CONFLICT = "overlap_conflict"
    GUIDE_CONFLICT = "guide_conflict"
    LOW_SCORE = "low_score"


class DropReason(StrEnum):
    NO_GEOMETRY_SUPPORT = "no_geometry_support"
    NO_TEXT_ASSIGNMENT = "no_text_assignment"
    EDGE_NOT_VERIFIED = "edge_not_verified"
    FALLBACK_NOT_ALLOWED = "fallback_not_allowed"
    EMISSION_UNSUPPORTED = "emission_unsupported"


class FailureTag(StrEnum):
    MISSING = "missing"
    MERGED_INTO_PARENT = "merged_into_parent"
    MERGED_SIBLINGS = "merged_siblings"
    SPLIT_FRAGMENTS = "split_fragments"
    WRONG_TYPE = "wrong_type"
    WRONG_ATTACHMENT = "wrong_attachment"
    NEAR_MISS_GEOMETRY = "near_miss_geometry"
    HALLUCINATED_PREDICTION = "hallucinated_prediction"


@dataclass(slots=True)
class StageEntity:
    id: str
    kind: str
    bbox: BBox | None
    score_total: float
    score_terms: dict[str, float] = field(default_factory=dict)
    source_ids: list[str] = field(default_factory=list)
    provenance: dict[str, list[str]] = field(default_factory=dict)
    parent_ids: list[str] = field(default_factory=list)
    guide_ids: list[str] = field(default_factory=list)
    assigned_text_ids: list[str] = field(default_factory=list)
    assigned_vlm_ids: list[str] = field(default_factory=list)

    def to_row(self) -> dict[str, Any]:
        row = asdict(self)
        if self.bbox is not None:
            row["bbox"] = bbox_to_row(self.bbox)
        return row


@dataclass(slots=True)
class OCRWord(StageEntity):
    text: str = ""
    normalized_text: str = ""
    confidence: float = 0.0


@dataclass(slots=True)
class OCRPhrase(StageEntity):
    text: str = ""
    normalized_text: str = ""
    word_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class VLMNode(StageEntity):
    text: str = ""
    object_type: str = "box"


@dataclass(slots=True)
class LinePrimitive(StageEntity):
    orientation: str = "unknown"
    point_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CornerPrimitive(StageEntity):
    point: Point | None = None

    def to_row(self) -> dict[str, Any]:
        row = StageEntity.to_row(self)
        row["point"] = None if self.point is None else {"x": self.point.x, "y": self.point.y}
        return row


@dataclass(slots=True)
class RegionPrimitive(StageEntity):
    fill_enabled: bool = False


@dataclass(slots=True)
class RectCandidate(StageEntity):
    object_type: str = "container"
    corner_radius: float = 0.0


@dataclass(slots=True)
class ConnectorCandidate(StageEntity):
    object_type: str = "connector"
    edge_type: str = "line"
    point_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Guide(StageEntity):
    axis: str = "x"
    position: float = 0.0
    member_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SizeCluster(StageEntity):
    axis: str = "x"
    value: float = 0.0
    member_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SpacingCluster(StageEntity):
    axis: str = "x"
    value: float = 0.0
    member_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class GuideField(StageEntity):
    guides: list[Guide] = field(default_factory=list)
    size_clusters: list[SizeCluster] = field(default_factory=list)
    spacing_clusters: list[SpacingCluster] = field(default_factory=list)

    def to_row(self) -> dict[str, Any]:
        row = StageEntity.to_row(self)
        row["guides"] = [guide.to_row() for guide in self.guides]
        row["size_clusters"] = [cluster.to_row() for cluster in self.size_clusters]
        row["spacing_clusters"] = [cluster.to_row() for cluster in self.spacing_clusters]
        return row


@dataclass(slots=True)
class ObjectHypothesis(StageEntity):
    object_type: str = "unknown"
    candidate_id: str | None = None
    fallback: bool = False
    suppression_reason: SuppressionReason | None = None
    drop_reason: DropReason | None = None


@dataclass(slots=True)
class MotifHypothesis(StageEntity):
    object_type: str = "motif"
    member_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class GraphEdge:
    id: str
    edge_type: str
    source_id: str
    target_id: str
    score_total: float
    score_terms: dict[str, float] = field(default_factory=dict)
    source_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_row(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AuthoringGraph(StageEntity):
    node_ids: list[str] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)

    def to_row(self) -> dict[str, Any]:
        row = StageEntity.to_row(self)
        row["node_ids"] = list(self.node_ids)
        row["edges"] = [edge.to_row() for edge in self.edges]
        return row


@dataclass(slots=True)
class EmissionRecord(StageEntity):
    object_type: str = "unknown"
    primitive_kind: str = "unknown"
    graph_node_ids: list[str] = field(default_factory=list)
    hypothesis_ids: list[str] = field(default_factory=list)
    emitted_element_id: str | None = None
    drop_reason: DropReason | None = None


@dataclass(slots=True)
class FallbackRegion(StageEntity):
    object_type: str = "fallback"
    strategy: str = "grow_fallback"


def bbox_to_row(bbox: BBox | None) -> dict[str, float] | None:
    if bbox is None:
        return None
    return {"x0": bbox.x0, "y0": bbox.y0, "x1": bbox.x1, "y1": bbox.y1}


def as_serializable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, BBox):
        return bbox_to_row(value)
    if isinstance(value, Point):
        return {"x": value.x, "y": value.y}
    if isinstance(value, list):
        return [as_serializable(item) for item in value]
    if isinstance(value, tuple):
        return [as_serializable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): as_serializable(item) for key, item in value.items()}
    if hasattr(value, "to_row"):
        return as_serializable(value.to_row())
    if is_dataclass(value):
        return as_serializable(asdict(value))
    return value
