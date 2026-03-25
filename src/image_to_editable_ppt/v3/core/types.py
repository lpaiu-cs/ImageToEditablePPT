from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias


RGBColor: TypeAlias = tuple[int, int, int]


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

    @classmethod
    def from_image_size(cls, image_size: ImageSize) -> "BBox":
        return cls(0.0, 0.0, float(image_size.width), float(image_size.height))
