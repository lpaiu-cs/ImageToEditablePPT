from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ElementKind = Literal[
    "rect",
    "rounded_rect",
    "line",
    "orthogonal_connector",
    "arrow",
    "text",
]
DashStyle = Literal["solid", "dash"]
TextAlignment = Literal["left", "center", "right"]


@dataclass(slots=True, frozen=True)
class Point:
    x: float
    y: float

    def to_dict(self) -> dict[str, float]:
        return {"x": self.x, "y": self.y}


@dataclass(slots=True, frozen=True)
class BBox:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return max(0.0, self.x1 - self.x0)

    @property
    def height(self) -> float:
        return max(0.0, self.y1 - self.y0)

    @property
    def area(self) -> float:
        return self.width * self.height

    @property
    def center(self) -> Point:
        return Point(self.x0 + self.width / 2.0, self.y0 + self.height / 2.0)

    def inset(self, delta: float) -> "BBox":
        if self.width <= 2 * delta or self.height <= 2 * delta:
            return self
        return BBox(self.x0 + delta, self.y0 + delta, self.x1 - delta, self.y1 - delta)

    def expand(self, delta: float) -> "BBox":
        return BBox(self.x0 - delta, self.y0 - delta, self.x1 + delta, self.y1 + delta)

    def contains_point(self, point: Point) -> bool:
        return self.x0 <= point.x <= self.x1 and self.y0 <= point.y <= self.y1

    def overlaps(self, other: "BBox") -> bool:
        return (
            self.x0 < other.x1
            and self.x1 > other.x0
            and self.y0 < other.y1
            and self.y1 > other.y0
        )

    def iou(self, other: "BBox") -> float:
        x0 = max(self.x0, other.x0)
        y0 = max(self.y0, other.y0)
        x1 = min(self.x1, other.x1)
        y1 = min(self.y1, other.y1)
        if x1 <= x0 or y1 <= y0:
            return 0.0
        inter = (x1 - x0) * (y1 - y0)
        union = self.area + other.area - inter
        if union <= 0:
            return 0.0
        return inter / union

    def to_dict(self) -> dict[str, float]:
        return {"x0": self.x0, "y0": self.y0, "x1": self.x1, "y1": self.y1}


@dataclass(slots=True, frozen=True)
class StrokeStyle:
    color: tuple[int, int, int]
    width: float
    dash_style: DashStyle = "solid"


@dataclass(slots=True, frozen=True)
class FillStyle:
    enabled: bool
    color: tuple[int, int, int] | None = None


@dataclass(slots=True, frozen=True)
class TextPayload:
    content: str
    alignment: TextAlignment = "center"
    confidence: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "content": self.content,
            "alignment": self.alignment,
            "confidence": self.confidence,
        }


@dataclass(slots=True, frozen=True)
class BoxGeometry:
    bbox: BBox
    corner_radius: float = 0.0


@dataclass(slots=True, frozen=True)
class PolylineGeometry:
    points: tuple[Point, ...]

    @property
    def bbox(self) -> BBox:
        xs = [point.x for point in self.points]
        ys = [point.y for point in self.points]
        return BBox(min(xs), min(ys), max(xs), max(ys))


@dataclass(slots=True)
class Element:
    id: str
    kind: ElementKind
    geometry: BoxGeometry | PolylineGeometry
    stroke: StrokeStyle
    fill: FillStyle
    text: TextPayload | None
    confidence: float
    source_region: BBox
    inferred: bool = False

    @property
    def bbox(self) -> BBox:
        if isinstance(self.geometry, BoxGeometry):
            return self.geometry.bbox
        return self.geometry.bbox

    def to_dict(self) -> dict:
        geometry: dict[str, object]
        if isinstance(self.geometry, BoxGeometry):
            geometry = {
                "bbox": self.geometry.bbox.to_dict(),
                "corner_radius": self.geometry.corner_radius,
            }
        else:
            geometry = {
                "points": [point.to_dict() for point in self.geometry.points],
            }
        return {
            "id": self.id,
            "kind": self.kind,
            "geometry": geometry,
            "stroke": {
                "color": self.stroke.color,
                "width": self.stroke.width,
                "dash_style": self.stroke.dash_style,
            },
            "fill": {
                "enabled": self.fill.enabled,
                "color": self.fill.color,
            },
            "text": None if self.text is None else self.text.to_dict(),
            "confidence": self.confidence,
            "source_region": self.source_region.to_dict(),
            "inferred": self.inferred,
        }
