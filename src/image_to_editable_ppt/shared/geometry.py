from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class Point:
    x: float
    y: float


@dataclass(slots=True, frozen=True)
class ImageSize:
    width: int
    height: int

    def as_tuple(self) -> tuple[int, int]:
        return (self.width, self.height)


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
        return self.x0 < other.x1 and self.x1 > other.x0 and self.y0 < other.y1 and self.y1 > other.y0

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

    @classmethod
    def from_image_size(cls, image_size: ImageSize) -> "BBox":
        return cls(0.0, 0.0, float(image_size.width), float(image_size.height))

    def to_dict(self) -> dict[str, float]:
        return {"x0": self.x0, "y0": self.y0, "x1": self.x1, "y1": self.y1}
