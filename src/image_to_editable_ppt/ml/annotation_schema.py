from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from enum import StrEnum
from math import isfinite
from typing import Any, Callable, Mapping, Self

from image_to_editable_ppt.shared.geometry import BBox, ImageSize, Point
from image_to_editable_ppt.v3.core.enums import (
    ConnectorKind,
    ContainerKind,
    DiagramFamily,
    NodeKind,
    PortOwnerKind,
    PortSide,
    ResidualKind,
    TextRegionRole,
)


type JsonScalar = None | bool | int | float | str
type JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


SCHEMA_VERSION = "phase7_ml_annotation_v1"


class AnnotationSchemaError(ValueError):
    """Raised when an ML annotation payload breaks the bootstrap contract."""


def annotation_to_json(value: object) -> JsonValue:
    if value is None:
        return None
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [annotation_to_json(item) for item in value]
    if isinstance(value, tuple):
        return [annotation_to_json(item) for item in value]
    if isinstance(value, dict):
        return {str(key): annotation_to_json(item) for key, item in value.items()}
    if is_dataclass(value):
        return annotation_to_json(asdict(value))
    raise AnnotationSchemaError(f"unsupported JSON value type: {type(value)!r}")


def _require_mapping(raw: object, *, label: str) -> Mapping[str, object]:
    if not isinstance(raw, Mapping):
        raise AnnotationSchemaError(f"{label} must be an object")
    return raw


def _require_sequence(raw: object, *, label: str) -> list[object]:
    if not isinstance(raw, list):
        raise AnnotationSchemaError(f"{label} must be a list")
    return raw


def _require_str(raw: object, *, label: str) -> str:
    if not isinstance(raw, str) or not raw:
        raise AnnotationSchemaError(f"{label} must be a non-empty string")
    return raw


def _read_optional_str(raw: object, *, label: str) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise AnnotationSchemaError(f"{label} must be a string or null")
    return raw


def _require_float(raw: object, *, label: str) -> float:
    if not isinstance(raw, (int, float)):
        raise AnnotationSchemaError(f"{label} must be numeric")
    value = float(raw)
    if not isfinite(value):
        raise AnnotationSchemaError(f"{label} must be finite")
    return value


def _require_int(raw: object, *, label: str) -> int:
    if not isinstance(raw, int):
        raise AnnotationSchemaError(f"{label} must be an integer")
    return raw


def _read_bool(raw: object, *, label: str, default: bool = False) -> bool:
    if raw is None:
        return default
    if not isinstance(raw, bool):
        raise AnnotationSchemaError(f"{label} must be a boolean")
    return raw


def _read_string_tuple(raw: object, *, label: str) -> tuple[str, ...]:
    if raw is None:
        return ()
    items = _require_sequence(raw, label=label)
    return tuple(_require_str(item, label=f"{label}[{index}]") for index, item in enumerate(items))


def _read_nested_tuple[T](
    raw: object,
    *,
    label: str,
    loader: Callable[[Mapping[str, object]], T],
) -> tuple[T, ...]:
    if raw is None:
        return ()
    items = _require_sequence(raw, label=label)
    return tuple(
        loader(_require_mapping(item, label=f"{label}[{index}]"))
        for index, item in enumerate(items)
    )


def _read_enum[T: StrEnum](raw: object, *, label: str, enum_cls: type[T]) -> T:
    if isinstance(raw, enum_cls):
        return raw
    if not isinstance(raw, str):
        raise AnnotationSchemaError(f"{label} must be one of {[item.value for item in enum_cls]}")
    try:
        return enum_cls(raw)
    except ValueError as exc:
        raise AnnotationSchemaError(f"{label} must be one of {[item.value for item in enum_cls]}") from exc


def _validate_confidence(confidence: float, *, label: str) -> None:
    if not 0.0 <= confidence <= 1.0:
        raise AnnotationSchemaError(f"{label} confidence must be in [0, 1]")


@dataclass(slots=True, frozen=True)
class AnnotationPoint:
    x: float
    y: float

    def __post_init__(self) -> None:
        if not isfinite(self.x) or not isfinite(self.y):
            raise AnnotationSchemaError("point coordinates must be finite")

    def to_point(self) -> Point:
        return Point(x=self.x, y=self.y)

    @classmethod
    def from_point(cls, point: Point) -> Self:
        return cls(x=point.x, y=point.y)

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> Self:
        return cls(
            x=_require_float(raw.get("x"), label="point.x"),
            y=_require_float(raw.get("y"), label="point.y"),
        )


@dataclass(slots=True, frozen=True)
class AnnotationBBox:
    x0: float
    y0: float
    x1: float
    y1: float

    def __post_init__(self) -> None:
        if not all(isfinite(value) for value in (self.x0, self.y0, self.x1, self.y1)):
            raise AnnotationSchemaError("bbox coordinates must be finite")
        if self.x1 <= self.x0 or self.y1 <= self.y0:
            raise AnnotationSchemaError("bbox must have positive extent")

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    def to_bbox(self) -> BBox:
        return BBox(x0=self.x0, y0=self.y0, x1=self.x1, y1=self.y1)

    def iou(self, other: "AnnotationBBox") -> float:
        return self.to_bbox().iou(other.to_bbox())

    @classmethod
    def from_bbox(cls, bbox: BBox) -> Self:
        return cls(x0=bbox.x0, y0=bbox.y0, x1=bbox.x1, y1=bbox.y1)

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> Self:
        return cls(
            x0=_require_float(raw.get("x0"), label="bbox.x0"),
            y0=_require_float(raw.get("y0"), label="bbox.y0"),
            x1=_require_float(raw.get("x1"), label="bbox.x1"),
            y1=_require_float(raw.get("y1"), label="bbox.y1"),
        )


@dataclass(slots=True, frozen=True)
class AnnotationImageSize:
    width: int
    height: int

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise AnnotationSchemaError("image size must be positive")

    def to_image_size(self) -> ImageSize:
        return ImageSize(width=self.width, height=self.height)

    @classmethod
    def from_image_size(cls, image_size: ImageSize) -> Self:
        return cls(width=image_size.width, height=image_size.height)

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> Self:
        return cls(
            width=_require_int(raw.get("width"), label="image_size.width"),
            height=_require_int(raw.get("height"), label="image_size.height"),
        )


@dataclass(slots=True, frozen=True)
class AnnotationFamilyProposal:
    id: str
    family: DiagramFamily
    confidence: float
    focus_bbox: AnnotationBBox
    evidence: tuple[str, ...] = ()
    provenance: tuple[str, ...] = ("ml_annotation:family_proposal",)

    def __post_init__(self) -> None:
        _require_str(self.id, label="family_proposal.id")
        _validate_confidence(self.confidence, label=self.id)
        if not self.provenance:
            raise AnnotationSchemaError(f"{self.id} provenance must not be empty")

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> Self:
        return cls(
            id=_require_str(raw.get("id"), label="family_proposal.id"),
            family=_read_enum(raw.get("family"), label="family_proposal.family", enum_cls=DiagramFamily),
            confidence=_require_float(raw.get("confidence"), label="family_proposal.confidence"),
            focus_bbox=AnnotationBBox.from_dict(_require_mapping(raw.get("focus_bbox"), label="family_proposal.focus_bbox")),
            evidence=_read_string_tuple(raw.get("evidence"), label="family_proposal.evidence"),
            provenance=_read_string_tuple(raw.get("provenance"), label="family_proposal.provenance")
            or ("ml_annotation:family_proposal",),
        )


@dataclass(slots=True, frozen=True)
class AnnotationTextRegion:
    id: str
    bbox: AnnotationBBox
    confidence: float
    role: TextRegionRole = TextRegionRole.UNKNOWN
    text: str | None = None
    source: str = "ml_annotation"
    provenance: tuple[str, ...] = ("ml_annotation:text_region",)

    def __post_init__(self) -> None:
        _require_str(self.id, label="text_region.id")
        _validate_confidence(self.confidence, label=self.id)
        _require_str(self.source, label=f"{self.id}.source")
        if not self.provenance:
            raise AnnotationSchemaError(f"{self.id} provenance must not be empty")

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> Self:
        return cls(
            id=_require_str(raw.get("id"), label="text_region.id"),
            bbox=AnnotationBBox.from_dict(_require_mapping(raw.get("bbox"), label="text_region.bbox")),
            confidence=_require_float(raw.get("confidence"), label="text_region.confidence"),
            role=_read_enum(raw.get("role", TextRegionRole.UNKNOWN.value), label="text_region.role", enum_cls=TextRegionRole),
            text=_read_optional_str(raw.get("text"), label="text_region.text"),
            source=_require_str(raw.get("source", "ml_annotation"), label="text_region.source"),
            provenance=_read_string_tuple(raw.get("provenance"), label="text_region.provenance")
            or ("ml_annotation:text_region",),
        )


@dataclass(slots=True, frozen=True)
class AnnotationNode:
    id: str
    kind: NodeKind
    bbox: AnnotationBBox
    confidence: float
    label: str | None = None
    text_region_ids: tuple[str, ...] = ()
    source: str = "ml_annotation"
    provenance: tuple[str, ...] = ("ml_annotation:node",)

    def __post_init__(self) -> None:
        _require_str(self.id, label="node.id")
        _validate_confidence(self.confidence, label=self.id)
        _require_str(self.source, label=f"{self.id}.source")
        if not self.provenance:
            raise AnnotationSchemaError(f"{self.id} provenance must not be empty")

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> Self:
        return cls(
            id=_require_str(raw.get("id"), label="node.id"),
            kind=_read_enum(raw.get("kind"), label="node.kind", enum_cls=NodeKind),
            bbox=AnnotationBBox.from_dict(_require_mapping(raw.get("bbox"), label="node.bbox")),
            confidence=_require_float(raw.get("confidence"), label="node.confidence"),
            label=_read_optional_str(raw.get("label"), label="node.label"),
            text_region_ids=_read_string_tuple(raw.get("text_region_ids"), label="node.text_region_ids"),
            source=_require_str(raw.get("source", "ml_annotation"), label="node.source"),
            provenance=_read_string_tuple(raw.get("provenance"), label="node.provenance")
            or ("ml_annotation:node",),
        )


@dataclass(slots=True, frozen=True)
class AnnotationContainer:
    id: str
    kind: ContainerKind
    bbox: AnnotationBBox
    confidence: float
    member_node_ids: tuple[str, ...] = ()
    label: str | None = None
    source: str = "ml_annotation"
    provenance: tuple[str, ...] = ("ml_annotation:container",)

    def __post_init__(self) -> None:
        _require_str(self.id, label="container.id")
        _validate_confidence(self.confidence, label=self.id)
        _require_str(self.source, label=f"{self.id}.source")
        if not self.provenance:
            raise AnnotationSchemaError(f"{self.id} provenance must not be empty")

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> Self:
        return cls(
            id=_require_str(raw.get("id"), label="container.id"),
            kind=_read_enum(raw.get("kind"), label="container.kind", enum_cls=ContainerKind),
            bbox=AnnotationBBox.from_dict(_require_mapping(raw.get("bbox"), label="container.bbox")),
            confidence=_require_float(raw.get("confidence"), label="container.confidence"),
            member_node_ids=_read_string_tuple(raw.get("member_node_ids"), label="container.member_node_ids"),
            label=_read_optional_str(raw.get("label"), label="container.label"),
            source=_require_str(raw.get("source", "ml_annotation"), label="container.source"),
            provenance=_read_string_tuple(raw.get("provenance"), label="container.provenance")
            or ("ml_annotation:container",),
        )


@dataclass(slots=True, frozen=True)
class AnnotationDiagramInstance:
    id: str
    family: DiagramFamily
    confidence: float
    bbox: AnnotationBBox
    containers: tuple[AnnotationContainer, ...] = ()
    nodes: tuple[AnnotationNode, ...] = ()
    text_region_ids: tuple[str, ...] = ()
    source_proposal_ids: tuple[str, ...] = ()
    provenance: tuple[str, ...] = ("ml_annotation:diagram_instance",)

    def __post_init__(self) -> None:
        _require_str(self.id, label="diagram_instance.id")
        _validate_confidence(self.confidence, label=self.id)
        if not self.provenance:
            raise AnnotationSchemaError(f"{self.id} provenance must not be empty")

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> Self:
        return cls(
            id=_require_str(raw.get("id"), label="diagram_instance.id"),
            family=_read_enum(raw.get("family"), label="diagram_instance.family", enum_cls=DiagramFamily),
            confidence=_require_float(raw.get("confidence"), label="diagram_instance.confidence"),
            bbox=AnnotationBBox.from_dict(_require_mapping(raw.get("bbox"), label="diagram_instance.bbox")),
            containers=_read_nested_tuple(raw.get("containers"), label="diagram_instance.containers", loader=AnnotationContainer.from_dict),
            nodes=_read_nested_tuple(raw.get("nodes"), label="diagram_instance.nodes", loader=AnnotationNode.from_dict),
            text_region_ids=_read_string_tuple(raw.get("text_region_ids"), label="diagram_instance.text_region_ids"),
            source_proposal_ids=_read_string_tuple(raw.get("source_proposal_ids"), label="diagram_instance.source_proposal_ids"),
            provenance=_read_string_tuple(raw.get("provenance"), label="diagram_instance.provenance")
            or ("ml_annotation:diagram_instance",),
        )


@dataclass(slots=True, frozen=True)
class AnnotationPort:
    id: str
    owner_id: str
    owner_kind: PortOwnerKind
    side: PortSide
    point: AnnotationPoint
    confidence: float
    source: str = "ml_annotation"
    provenance: tuple[str, ...] = ("ml_annotation:port",)

    def __post_init__(self) -> None:
        _require_str(self.id, label="port.id")
        _require_str(self.owner_id, label="port.owner_id")
        _validate_confidence(self.confidence, label=self.id)
        _require_str(self.source, label=f"{self.id}.source")
        if not self.provenance:
            raise AnnotationSchemaError(f"{self.id} provenance must not be empty")

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> Self:
        return cls(
            id=_require_str(raw.get("id"), label="port.id"),
            owner_id=_require_str(raw.get("owner_id"), label="port.owner_id"),
            owner_kind=_read_enum(raw.get("owner_kind"), label="port.owner_kind", enum_cls=PortOwnerKind),
            side=_read_enum(raw.get("side"), label="port.side", enum_cls=PortSide),
            point=AnnotationPoint.from_dict(_require_mapping(raw.get("point"), label="port.point")),
            confidence=_require_float(raw.get("confidence"), label="port.confidence"),
            source=_require_str(raw.get("source", "ml_annotation"), label="port.source"),
            provenance=_read_string_tuple(raw.get("provenance"), label="port.provenance")
            or ("ml_annotation:port",),
        )


@dataclass(slots=True, frozen=True)
class AnnotationConnectorEndpoint:
    point: AnnotationPoint
    owner_id: str | None = None
    owner_kind: PortOwnerKind | None = None
    side: PortSide | None = None
    distance: float = 0.0
    confidence: float = 1.0

    def __post_init__(self) -> None:
        if self.distance < 0.0:
            raise AnnotationSchemaError("endpoint distance must be non-negative")
        owner_fields = (self.owner_id, self.owner_kind, self.side)
        if any(field is not None for field in owner_fields) and not all(field is not None for field in owner_fields):
            raise AnnotationSchemaError("endpoint owner_id, owner_kind, and side must be provided together")
        _validate_confidence(self.confidence, label="connector_endpoint")

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> Self:
        owner_kind_raw = raw.get("owner_kind")
        side_raw = raw.get("side")
        return cls(
            point=AnnotationPoint.from_dict(_require_mapping(raw.get("point"), label="connector_endpoint.point")),
            owner_id=_read_optional_str(raw.get("owner_id"), label="connector_endpoint.owner_id"),
            owner_kind=None
            if owner_kind_raw is None
            else _read_enum(owner_kind_raw, label="connector_endpoint.owner_kind", enum_cls=PortOwnerKind),
            side=None if side_raw is None else _read_enum(side_raw, label="connector_endpoint.side", enum_cls=PortSide),
            distance=_require_float(raw.get("distance", 0.0), label="connector_endpoint.distance"),
            confidence=_require_float(raw.get("confidence", 1.0), label="connector_endpoint.confidence"),
        )


@dataclass(slots=True, frozen=True)
class AnnotationPrimitiveText:
    id: str
    role: TextRegionRole
    bbox: AnnotationBBox
    confidence: float
    text: str | None = None
    owner_ids: tuple[str, ...] = ()
    source: str = "ml_annotation"
    provenance: tuple[str, ...] = ("ml_annotation:primitive_text",)

    def __post_init__(self) -> None:
        _require_str(self.id, label="primitive_text.id")
        _validate_confidence(self.confidence, label=self.id)
        _require_str(self.source, label=f"{self.id}.source")
        if not self.provenance:
            raise AnnotationSchemaError(f"{self.id} provenance must not be empty")

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> Self:
        return cls(
            id=_require_str(raw.get("id"), label="primitive_text.id"),
            role=_read_enum(raw.get("role", TextRegionRole.UNKNOWN.value), label="primitive_text.role", enum_cls=TextRegionRole),
            bbox=AnnotationBBox.from_dict(_require_mapping(raw.get("bbox"), label="primitive_text.bbox")),
            confidence=_require_float(raw.get("confidence"), label="primitive_text.confidence"),
            text=_read_optional_str(raw.get("text"), label="primitive_text.text"),
            owner_ids=_read_string_tuple(raw.get("owner_ids"), label="primitive_text.owner_ids"),
            source=_require_str(raw.get("source", "ml_annotation"), label="primitive_text.source"),
            provenance=_read_string_tuple(raw.get("provenance"), label="primitive_text.provenance")
            or ("ml_annotation:primitive_text",),
        )


@dataclass(slots=True, frozen=True)
class AnnotationConnectorCandidate:
    id: str
    kind: ConnectorKind
    bbox: AnnotationBBox
    confidence: float
    source_evidence_id: str
    path_points: tuple[AnnotationPoint, ...] = ()
    start_endpoint: AnnotationConnectorEndpoint | None = None
    end_endpoint: AnnotationConnectorEndpoint | None = None
    arrowhead_start: bool = False
    arrowhead_end: bool = False
    source: str = "ml_annotation"
    provenance: tuple[str, ...] = ("ml_annotation:connector_candidate",)
    # Rendered stroke width in px (synthetic GT only). Lets the connector
    # segmenter rasterize a line mask matching the rendered thickness instead of a
    # fixed width, so thin-arrow domain-randomized samples are supervised against
    # masks the same width as their pixels. None -> fall back to the default width.
    stroke_width: int | None = None

    def __post_init__(self) -> None:
        _require_str(self.id, label="connector_candidate.id")
        _require_str(self.source_evidence_id, label="connector_candidate.source_evidence_id")
        _validate_confidence(self.confidence, label=self.id)
        _require_str(self.source, label=f"{self.id}.source")
        if len(self.path_points) == 1:
            raise AnnotationSchemaError(f"{self.id} path_points must contain at least two points")
        if not self.path_points and (self.start_endpoint is None or self.end_endpoint is None):
            raise AnnotationSchemaError(f"{self.id} requires either path_points or both endpoints")
        if not self.provenance:
            raise AnnotationSchemaError(f"{self.id} provenance must not be empty")

    def effective_path_points(self) -> tuple[AnnotationPoint, ...]:
        if self.path_points:
            return self.path_points
        assert self.start_endpoint is not None
        assert self.end_endpoint is not None
        return (self.start_endpoint.point, self.end_endpoint.point)

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> Self:
        start_endpoint_raw = raw.get("start_endpoint")
        end_endpoint_raw = raw.get("end_endpoint")
        return cls(
            id=_require_str(raw.get("id"), label="connector_candidate.id"),
            kind=_read_enum(raw.get("kind"), label="connector_candidate.kind", enum_cls=ConnectorKind),
            bbox=AnnotationBBox.from_dict(_require_mapping(raw.get("bbox"), label="connector_candidate.bbox")),
            confidence=_require_float(raw.get("confidence"), label="connector_candidate.confidence"),
            source_evidence_id=_require_str(raw.get("source_evidence_id"), label="connector_candidate.source_evidence_id"),
            path_points=_read_nested_tuple(raw.get("path_points"), label="connector_candidate.path_points", loader=AnnotationPoint.from_dict),
            start_endpoint=None
            if start_endpoint_raw is None
            else AnnotationConnectorEndpoint.from_dict(
                _require_mapping(start_endpoint_raw, label="connector_candidate.start_endpoint")
            ),
            end_endpoint=None
            if end_endpoint_raw is None
            else AnnotationConnectorEndpoint.from_dict(
                _require_mapping(end_endpoint_raw, label="connector_candidate.end_endpoint")
            ),
            arrowhead_start=_read_bool(raw.get("arrowhead_start"), label="connector_candidate.arrowhead_start"),
            arrowhead_end=_read_bool(raw.get("arrowhead_end"), label="connector_candidate.arrowhead_end"),
            source=_require_str(raw.get("source", "ml_annotation"), label="connector_candidate.source"),
            provenance=_read_string_tuple(raw.get("provenance"), label="connector_candidate.provenance")
            or ("ml_annotation:connector_candidate",),
            stroke_width=None if raw.get("stroke_width") is None else int(raw["stroke_width"]),
        )


@dataclass(slots=True, frozen=True)
class AnnotationUnattachedConnectorEvidence:
    id: str
    evidence_id: str
    reason: str
    confidence: float
    candidate_port_ids: tuple[str, ...] = ()
    source: str = "ml_annotation"
    provenance: tuple[str, ...] = ("ml_annotation:unattached_connector_evidence",)

    def __post_init__(self) -> None:
        _require_str(self.id, label="unattached_connector_evidence.id")
        _require_str(self.evidence_id, label="unattached_connector_evidence.evidence_id")
        _require_str(self.reason, label="unattached_connector_evidence.reason")
        _validate_confidence(self.confidence, label=self.id)
        _require_str(self.source, label=f"{self.id}.source")
        if not self.provenance:
            raise AnnotationSchemaError(f"{self.id} provenance must not be empty")

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> Self:
        return cls(
            id=_require_str(raw.get("id"), label="unattached_connector_evidence.id"),
            evidence_id=_require_str(raw.get("evidence_id"), label="unattached_connector_evidence.evidence_id"),
            reason=_require_str(raw.get("reason"), label="unattached_connector_evidence.reason"),
            confidence=_require_float(raw.get("confidence"), label="unattached_connector_evidence.confidence"),
            candidate_port_ids=_read_string_tuple(
                raw.get("candidate_port_ids"),
                label="unattached_connector_evidence.candidate_port_ids",
            ),
            source=_require_str(raw.get("source", "ml_annotation"), label="unattached_connector_evidence.source"),
            provenance=_read_string_tuple(
                raw.get("provenance"),
                label="unattached_connector_evidence.provenance",
            )
            or ("ml_annotation:unattached_connector_evidence",),
        )


@dataclass(slots=True, frozen=True)
class AnnotationResidual:
    id: str
    kind: ResidualKind
    bbox: AnnotationBBox
    confidence: float
    reason: str
    source: str = "ml_annotation"
    provenance: tuple[str, ...] = ("ml_annotation:residual",)

    def __post_init__(self) -> None:
        _require_str(self.id, label="residual.id")
        _require_str(self.reason, label="residual.reason")
        _validate_confidence(self.confidence, label=self.id)
        _require_str(self.source, label=f"{self.id}.source")
        if not self.provenance:
            raise AnnotationSchemaError(f"{self.id} provenance must not be empty")

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> Self:
        return cls(
            id=_require_str(raw.get("id"), label="residual.id"),
            kind=_read_enum(raw.get("kind"), label="residual.kind", enum_cls=ResidualKind),
            bbox=AnnotationBBox.from_dict(_require_mapping(raw.get("bbox"), label="residual.bbox")),
            confidence=_require_float(raw.get("confidence"), label="residual.confidence"),
            reason=_require_str(raw.get("reason"), label="residual.reason"),
            source=_require_str(raw.get("source", "ml_annotation"), label="residual.source"),
            provenance=_read_string_tuple(raw.get("provenance"), label="residual.provenance")
            or ("ml_annotation:residual",),
        )


@dataclass(slots=True, frozen=True)
class AnnotationPrimitiveScene:
    nodes: tuple[AnnotationNode, ...] = ()
    containers: tuple[AnnotationContainer, ...] = ()
    texts: tuple[AnnotationPrimitiveText, ...] = ()
    ports: tuple[AnnotationPort, ...] = ()
    connector_candidates: tuple[AnnotationConnectorCandidate, ...] = ()
    unattached_connector_evidence: tuple[AnnotationUnattachedConnectorEvidence, ...] = ()
    residuals: tuple[AnnotationResidual, ...] = ()

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> Self:
        return cls(
            nodes=_read_nested_tuple(raw.get("nodes"), label="primitive_scene.nodes", loader=AnnotationNode.from_dict),
            containers=_read_nested_tuple(
                raw.get("containers"),
                label="primitive_scene.containers",
                loader=AnnotationContainer.from_dict,
            ),
            texts=_read_nested_tuple(
                raw.get("texts"),
                label="primitive_scene.texts",
                loader=AnnotationPrimitiveText.from_dict,
            ),
            ports=_read_nested_tuple(raw.get("ports"), label="primitive_scene.ports", loader=AnnotationPort.from_dict),
            connector_candidates=_read_nested_tuple(
                raw.get("connector_candidates"),
                label="primitive_scene.connector_candidates",
                loader=AnnotationConnectorCandidate.from_dict,
            ),
            unattached_connector_evidence=_read_nested_tuple(
                raw.get("unattached_connector_evidence"),
                label="primitive_scene.unattached_connector_evidence",
                loader=AnnotationUnattachedConnectorEvidence.from_dict,
            ),
            residuals=_read_nested_tuple(
                raw.get("residuals"),
                label="primitive_scene.residuals",
                loader=AnnotationResidual.from_dict,
            ),
        )


@dataclass(slots=True, frozen=True)
class DetectorAnnotationDocument:
    image_id: str
    image_size: AnnotationImageSize
    schema_version: str = SCHEMA_VERSION
    image_path: str | None = None
    split: str | None = None
    family_proposals: tuple[AnnotationFamilyProposal, ...] = ()
    text_regions: tuple[AnnotationTextRegion, ...] = ()
    diagram_instances: tuple[AnnotationDiagramInstance, ...] = ()
    primitive_scene: AnnotationPrimitiveScene | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_str(self.image_id, label="document.image_id")
        _require_str(self.schema_version, label="document.schema_version")

    def to_dict(self) -> dict[str, JsonValue]:
        payload = annotation_to_json(self)
        assert isinstance(payload, dict)
        return payload

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> Self:
        primitive_scene_raw = raw.get("primitive_scene")
        metadata_raw = raw.get("metadata", {})
        metadata = dict(_require_mapping(metadata_raw, label="document.metadata"))
        return cls(
            image_id=_require_str(raw.get("image_id"), label="document.image_id"),
            image_size=AnnotationImageSize.from_dict(_require_mapping(raw.get("image_size"), label="document.image_size")),
            schema_version=_require_str(raw.get("schema_version", SCHEMA_VERSION), label="document.schema_version"),
            image_path=_read_optional_str(raw.get("image_path"), label="document.image_path"),
            split=_read_optional_str(raw.get("split"), label="document.split"),
            family_proposals=_read_nested_tuple(
                raw.get("family_proposals"),
                label="document.family_proposals",
                loader=AnnotationFamilyProposal.from_dict,
            ),
            text_regions=_read_nested_tuple(
                raw.get("text_regions"),
                label="document.text_regions",
                loader=AnnotationTextRegion.from_dict,
            ),
            diagram_instances=_read_nested_tuple(
                raw.get("diagram_instances"),
                label="document.diagram_instances",
                loader=AnnotationDiagramInstance.from_dict,
            ),
            primitive_scene=None
            if primitive_scene_raw is None
            else AnnotationPrimitiveScene.from_dict(
                _require_mapping(primitive_scene_raw, label="document.primitive_scene")
            ),
            metadata=metadata,
        )
