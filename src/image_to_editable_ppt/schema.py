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


class StageContractError(ValueError):
    """Raised when a stage artifact violates the expected machine-readable contract."""


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
    asset_id: str | None = None


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


def validate_stage_entities(
    stage: str,
    name: str,
    rows: list[StageEntity],
    *,
    require_bbox: bool = False,
) -> list[StageEntity]:
    validated: list[StageEntity] = []
    for row in rows:
        validate_stage_entity(stage, name, row, require_bbox=require_bbox)
        validated.append(row)
    return validated


def validate_stage_entity(
    stage: str,
    name: str,
    row: StageEntity,
    *,
    require_bbox: bool = False,
) -> None:
    if not isinstance(row, StageEntity):
        raise StageContractError(f"{stage}/{name}: expected StageEntity, got {type(row)!r}")
    if not row.id:
        raise StageContractError(f"{stage}/{name}: missing id")
    if not row.kind and not getattr(row, "object_type", ""):
        raise StageContractError(f"{stage}/{name}:{row.id}: missing kind/object_type")
    if not isinstance(row.score_total, (int, float)):
        raise StageContractError(f"{stage}/{name}:{row.id}: missing score_total")
    if not isinstance(row.score_terms, dict):
        raise StageContractError(f"{stage}/{name}:{row.id}: missing score_terms")
    if not isinstance(row.source_ids, list):
        raise StageContractError(f"{stage}/{name}:{row.id}: missing source_ids")
    if not isinstance(row.provenance, dict):
        raise StageContractError(f"{stage}/{name}:{row.id}: missing provenance")
    if require_bbox and row.bbox is None:
        raise StageContractError(f"{stage}/{name}:{row.id}: spatial entity missing bbox")
    if isinstance(row, Guide) and row.axis not in {"x", "y"}:
        raise StageContractError(f"{stage}/{name}:{row.id}: invalid guide axis")
    if isinstance(row, ObjectHypothesis):
        if not row.assigned_vlm_ids and not row.assigned_text_ids and not row.fallback:
            raise StageContractError(f"{stage}/{name}:{row.id}: hypothesis missing assignment links")
        if not row.source_ids:
            raise StageContractError(f"{stage}/{name}:{row.id}: hypothesis missing source_ids")
    if isinstance(row, MotifHypothesis) and not row.member_ids:
        raise StageContractError(f"{stage}/{name}:{row.id}: motif missing member_ids")
    if isinstance(row, EmissionRecord):
        if row.emitted_element_id is None and row.drop_reason is None:
            raise StageContractError(f"{stage}/{name}:{row.id}: emission missing emitted_element_id/drop_reason")
        if row.object_type != "connector" and row.drop_reason is None:
            if not row.graph_node_ids or not row.hypothesis_ids:
                raise StageContractError(f"{stage}/{name}:{row.id}: emission missing graph/hypothesis links")
    if isinstance(row, FallbackRegion) and "grow_fallback" not in row.source_ids and row.strategy == "grow_fallback":
        raise StageContractError(f"{stage}/{name}:{row.id}: fallback region missing grow_fallback source tag")


def validate_emission_trace(
    *,
    emission_records: list[EmissionRecord],
    graph: AuthoringGraph,
    object_hypotheses: list[ObjectHypothesis],
    motif_hypotheses: list[MotifHypothesis],
    geometry_candidates: list[RectCandidate],
    fallback_regions: list[FallbackRegion],
) -> None:
    hypothesis_ids = {hypothesis.id for hypothesis in object_hypotheses}
    graph_node_ids = set(graph.node_ids)
    geometry_ids = {candidate.id for candidate in geometry_candidates}
    fallback_ids = {region.id for region in fallback_regions}
    motif_ids = {motif.id for motif in motif_hypotheses}
    for record in emission_records:
        validate_stage_entity("07_emit", "emission_records", record, require_bbox=record.drop_reason is None)
        for node_id in record.graph_node_ids:
            if node_id not in graph_node_ids:
                raise StageContractError(f"07_emit/emission_records:{record.id}: unknown graph node {node_id}")
        for hypothesis_id in record.hypothesis_ids:
            if hypothesis_id not in hypothesis_ids and hypothesis_id not in motif_ids:
                raise StageContractError(f"07_emit/emission_records:{record.id}: unknown hypothesis {hypothesis_id}")
        if record.drop_reason is not None:
            continue
        if record.object_type == "connector":
            if len(record.graph_node_ids) < 2 or len(record.hypothesis_ids) < 2:
                raise StageContractError(f"07_emit/emission_records:{record.id}: connector missing endpoint provenance")
            continue
        if not any(source_id in geometry_ids or source_id in fallback_ids or source_id == "grow_fallback" for source_id in record.source_ids):
            raise StageContractError(f"07_emit/emission_records:{record.id}: no geometry/fallback source trace")
