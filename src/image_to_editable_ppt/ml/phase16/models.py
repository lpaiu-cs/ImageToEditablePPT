"""Data contracts for the isolated Phase 16 experiment."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from math import isfinite
from typing import Any, Mapping, Sequence


ANNOTATION_SCHEMA_VERSION = "phase16_annotation_v2"
MANIFEST_SCHEMA_VERSION = "phase16_benchmark_manifest_v1"


class Phase16ModelError(ValueError):
    """Raised when a Phase 16 data contract is malformed."""


class SampleKind(StrEnum):
    DIAGRAM = "diagram"
    NON_DIAGRAM = "non_diagram"


class ObjectRole(StrEnum):
    NODE = "node"
    CONTAINER = "container"


class ShapeKind(StrEnum):
    RECTANGLE = "rectangle"
    ROUNDED_RECTANGLE = "rounded_rectangle"
    ELLIPSE = "ellipse"


class Importance(StrEnum):
    CORE = "core"
    SECONDARY = "secondary"
    EXCLUDED = "excluded"


class Direction(StrEnum):
    DIRECTED = "directed"
    UNDIRECTED = "undirected"
    AMBIGUOUS = "ambiguous"


class PathClass(StrEnum):
    DIRECT_ORTHOGONAL = "direct_orthogonal"
    ELBOW_ORTHOGONAL = "elbow_orthogonal"
    MULTI_SEGMENT_ORTHOGONAL = "multi_segment_orthogonal"
    DOTTED_ORTHOGONAL = "dotted_orthogonal"
    CURVE = "curve"
    FREE = "free"


class ExcludedRegionKind(StrEnum):
    ICON = "icon"
    LOGO = "logo"
    PHOTO = "photo"
    ILLUSTRATION = "illustration"
    DECORATION = "decoration"
    TEXTURE = "texture"
    PLOT = "plot"
    TABLE = "table"
    APPLICATION_SCREENSHOT = "application_screenshot"
    OTHER = "other"


def _mapping(raw: object, label: str) -> Mapping[str, object]:
    if not isinstance(raw, Mapping):
        raise Phase16ModelError(f"{label} must be an object")
    return raw


def _sequence(raw: object, label: str) -> Sequence[object]:
    if not isinstance(raw, list):
        raise Phase16ModelError(f"{label} must be a list")
    return raw


def _string(raw: object, label: str, *, allow_empty: bool = False) -> str:
    if not isinstance(raw, str) or (not allow_empty and not raw):
        raise Phase16ModelError(f"{label} must be a non-empty string")
    return raw


def _optional_string(raw: object, label: str) -> str | None:
    if raw is None:
        return None
    return _string(raw, label)


def _number(raw: object, label: str) -> float:
    if not isinstance(raw, (int, float)) or isinstance(raw, bool):
        raise Phase16ModelError(f"{label} must be numeric")
    value = float(raw)
    if not isfinite(value):
        raise Phase16ModelError(f"{label} must be finite")
    return value


def _integer(raw: object, label: str) -> int:
    if not isinstance(raw, int) or isinstance(raw, bool):
        raise Phase16ModelError(f"{label} must be an integer")
    return raw


def _boolean(raw: object, label: str) -> bool:
    if not isinstance(raw, bool):
        raise Phase16ModelError(f"{label} must be boolean")
    return raw


def _enum[T: StrEnum](raw: object, label: str, enum_type: type[T]) -> T:
    if isinstance(raw, enum_type):
        return raw
    if not isinstance(raw, str):
        raise Phase16ModelError(f"{label} must be one of {[item.value for item in enum_type]}")
    try:
        return enum_type(raw)
    except ValueError as error:
        raise Phase16ModelError(
            f"{label} must be one of {[item.value for item in enum_type]}"
        ) from error


@dataclass(slots=True, frozen=True)
class Point:
    x: float
    y: float

    def __post_init__(self) -> None:
        if not isfinite(self.x) or not isfinite(self.y):
            raise Phase16ModelError("point coordinates must be finite")

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> "Point":
        return cls(x=_number(raw.get("x"), "point.x"), y=_number(raw.get("y"), "point.y"))


@dataclass(slots=True, frozen=True)
class BBox:
    x0: float
    y0: float
    x1: float
    y1: float

    def __post_init__(self) -> None:
        if not all(isfinite(value) for value in (self.x0, self.y0, self.x1, self.y1)):
            raise Phase16ModelError("bbox coordinates must be finite")
        if self.x1 <= self.x0 or self.y1 <= self.y0:
            raise Phase16ModelError("bbox must have positive extent")

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def area(self) -> float:
        return self.width * self.height

    def contains_bbox(self, other: "BBox", *, tolerance: float = 0.0) -> bool:
        return (
            other.x0 >= self.x0 - tolerance
            and other.y0 >= self.y0 - tolerance
            and other.x1 <= self.x1 + tolerance
            and other.y1 <= self.y1 + tolerance
        )

    def contains_point(self, point: Point, *, tolerance: float = 0.0) -> bool:
        return (
            self.x0 - tolerance <= point.x <= self.x1 + tolerance
            and self.y0 - tolerance <= point.y <= self.y1 + tolerance
        )

    def iou(self, other: "BBox") -> float:
        ix0 = max(self.x0, other.x0)
        iy0 = max(self.y0, other.y0)
        ix1 = min(self.x1, other.x1)
        iy1 = min(self.y1, other.y1)
        intersection = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
        union = self.area + other.area - intersection
        return intersection / union if union > 0.0 else 0.0

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> "BBox":
        return cls(
            x0=_number(raw.get("x0"), "bbox.x0"),
            y0=_number(raw.get("y0"), "bbox.y0"),
            x1=_number(raw.get("x1"), "bbox.x1"),
            y1=_number(raw.get("y1"), "bbox.y1"),
        )


@dataclass(slots=True, frozen=True)
class LabelAnnotation:
    text: str
    legible: bool
    editable_required: bool

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> "LabelAnnotation":
        return cls(
            text=_string(raw.get("text"), "label.text", allow_empty=True),
            legible=_boolean(raw.get("legible"), "label.legible"),
            editable_required=_boolean(raw.get("editable_required"), "label.editable_required"),
        )


@dataclass(slots=True, frozen=True)
class StructuralObjectAnnotation:
    id: str
    role: ObjectRole
    shape_kind: ShapeKind
    bbox: BBox
    parent_id: str | None
    importance: Importance
    label: LabelAnnotation | None = None
    ambiguity_note: str | None = None

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> "StructuralObjectAnnotation":
        label_raw = raw.get("label")
        return cls(
            id=_string(raw.get("id"), "object.id"),
            role=_enum(raw.get("role"), "object.role", ObjectRole),
            shape_kind=_enum(raw.get("shape_kind"), "object.shape_kind", ShapeKind),
            bbox=BBox.from_dict(_mapping(raw.get("bbox"), "object.bbox")),
            parent_id=_optional_string(raw.get("parent_id"), "object.parent_id"),
            importance=_enum(raw.get("importance"), "object.importance", Importance),
            label=None if label_raw is None else LabelAnnotation.from_dict(_mapping(label_raw, "object.label")),
            ambiguity_note=_optional_string(raw.get("ambiguity_note"), "object.ambiguity_note"),
        )


@dataclass(slots=True, frozen=True)
class ConnectorAnnotation:
    id: str
    source_id: str
    target_id: str
    direction: Direction
    path_class: PathClass
    importance: Importance
    path_points: tuple[Point, ...]
    ambiguity_note: str | None = None

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> "ConnectorAnnotation":
        return cls(
            id=_string(raw.get("id"), "connector.id"),
            source_id=_string(raw.get("source_id"), "connector.source_id"),
            target_id=_string(raw.get("target_id"), "connector.target_id"),
            direction=_enum(raw.get("direction"), "connector.direction", Direction),
            path_class=_enum(raw.get("path_class"), "connector.path_class", PathClass),
            importance=_enum(raw.get("importance"), "connector.importance", Importance),
            path_points=tuple(
                Point.from_dict(_mapping(item, f"connector.path_points[{index}]"))
                for index, item in enumerate(_sequence(raw.get("path_points"), "connector.path_points"))
            ),
            ambiguity_note=_optional_string(raw.get("ambiguity_note"), "connector.ambiguity_note"),
        )


@dataclass(slots=True, frozen=True)
class ExcludedRegionAnnotation:
    id: str
    kind: ExcludedRegionKind
    bbox: BBox
    note: str

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> "ExcludedRegionAnnotation":
        return cls(
            id=_string(raw.get("id"), "excluded_region.id"),
            kind=_enum(raw.get("kind"), "excluded_region.kind", ExcludedRegionKind),
            bbox=BBox.from_dict(_mapping(raw.get("bbox"), "excluded_region.bbox")),
            note=_string(raw.get("note"), "excluded_region.note"),
        )


@dataclass(slots=True, frozen=True)
class ReviewPass:
    pass_id: str
    reviewer: str
    completed_at: str
    focus: tuple[str, ...]

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> "ReviewPass":
        return cls(
            pass_id=_string(raw.get("pass_id"), "review_pass.pass_id"),
            reviewer=_string(raw.get("reviewer"), "review_pass.reviewer"),
            completed_at=_string(raw.get("completed_at"), "review_pass.completed_at"),
            focus=tuple(
                _string(item, f"review_pass.focus[{index}]")
                for index, item in enumerate(_sequence(raw.get("focus"), "review_pass.focus"))
            ),
        )


@dataclass(slots=True, frozen=True)
class AnnotationDocument:
    sample_id: str
    image_path: str
    image_sha256: str
    image_width: int
    image_height: int
    kind: SampleKind
    objects: tuple[StructuralObjectAnnotation, ...]
    connectors: tuple[ConnectorAnnotation, ...]
    excluded_regions: tuple[ExcludedRegionAnnotation, ...]
    allowed_omissions: tuple[str, ...]
    ambiguity_notes: tuple[str, ...]
    review_status: str
    review_passes: tuple[ReviewPass, ...]
    schema_version: str = ANNOTATION_SCHEMA_VERSION

    @property
    def image_bbox(self) -> BBox:
        return BBox(0.0, 0.0, float(self.image_width), float(self.image_height))

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> "AnnotationDocument":
        image = _mapping(raw.get("image"), "annotation.image")
        review = _mapping(raw.get("review"), "annotation.review")
        return cls(
            sample_id=_string(raw.get("sample_id"), "annotation.sample_id"),
            image_path=_string(image.get("path"), "annotation.image.path"),
            image_sha256=_string(image.get("sha256"), "annotation.image.sha256"),
            image_width=_integer(image.get("width"), "annotation.image.width"),
            image_height=_integer(image.get("height"), "annotation.image.height"),
            kind=_enum(raw.get("kind"), "annotation.kind", SampleKind),
            objects=tuple(
                StructuralObjectAnnotation.from_dict(_mapping(item, f"annotation.objects[{index}]"))
                for index, item in enumerate(_sequence(raw.get("objects"), "annotation.objects"))
            ),
            connectors=tuple(
                ConnectorAnnotation.from_dict(_mapping(item, f"annotation.connectors[{index}]"))
                for index, item in enumerate(_sequence(raw.get("connectors"), "annotation.connectors"))
            ),
            excluded_regions=tuple(
                ExcludedRegionAnnotation.from_dict(
                    _mapping(item, f"annotation.excluded_regions[{index}]")
                )
                for index, item in enumerate(
                    _sequence(raw.get("excluded_regions"), "annotation.excluded_regions")
                )
            ),
            allowed_omissions=tuple(
                _string(item, f"annotation.allowed_omissions[{index}]")
                for index, item in enumerate(
                    _sequence(raw.get("allowed_omissions"), "annotation.allowed_omissions")
                )
            ),
            ambiguity_notes=tuple(
                _string(item, f"annotation.ambiguity_notes[{index}]")
                for index, item in enumerate(
                    _sequence(raw.get("ambiguity_notes"), "annotation.ambiguity_notes")
                )
            ),
            review_status=_string(review.get("status"), "annotation.review.status"),
            review_passes=tuple(
                ReviewPass.from_dict(_mapping(item, f"annotation.review.passes[{index}]"))
                for index, item in enumerate(_sequence(review.get("passes"), "annotation.review.passes"))
            ),
            schema_version=_string(
                raw.get("schema_version", ANNOTATION_SCHEMA_VERSION),
                "annotation.schema_version",
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["kind"] = self.kind.value
        for item in payload["objects"]:
            item["role"] = str(item["role"])
            item["shape_kind"] = str(item["shape_kind"])
            item["importance"] = str(item["importance"])
        for item in payload["connectors"]:
            item["direction"] = str(item["direction"])
            item["path_class"] = str(item["path_class"])
            item["importance"] = str(item["importance"])
        for item in payload["excluded_regions"]:
            item["kind"] = str(item["kind"])
        return payload


@dataclass(slots=True, frozen=True)
class RegionHypothesis:
    """Raw source-supported shape proposal in original-image coordinates."""

    id: str
    bbox_original: BBox
    shape_kind: ShapeKind
    observed_scales: tuple[int, ...]
    border_support: Mapping[str, float]
    border_continuity: Mapping[str, float]
    corner_support: float
    inner_outer_color_delta: float
    detrended_inner_texture: float
    text_overlap: float
    raster_overlap: float
    detector_overlap: float
    repetition_group_id: str | None
    parent_candidate_ids: tuple[str, ...]
    evidence_families: tuple[str, ...]
    confidence: float
    provenance: tuple[str, ...]
    accepted_reason: tuple[str, ...] = ()
    rejected_reason: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id:
            raise Phase16ModelError("region hypothesis id must not be empty")
        if not self.provenance:
            raise Phase16ModelError(f"{self.id} provenance must not be empty")
        if not 0.0 <= self.confidence <= 1.0:
            raise Phase16ModelError(f"{self.id} confidence must be in [0, 1]")
        for label, value in (
            ("text_overlap", self.text_overlap),
            ("raster_overlap", self.raster_overlap),
            ("detector_overlap", self.detector_overlap),
        ):
            if not 0.0 <= value <= 1.0:
                raise Phase16ModelError(f"{self.id} {label} must be in [0, 1]")

