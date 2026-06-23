from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RectF:
    """Half-open rectangle in image or view coordinates."""

    x0: float
    y0: float
    x1: float
    y1: float

    def __post_init__(self) -> None:
        self.validate()

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def center_x(self) -> float:
        return (self.x0 + self.x1) / 2.0

    @property
    def center_y(self) -> float:
        return (self.y0 + self.y1) / 2.0

    def translated(self, dx: float, dy: float) -> "RectF":
        return RectF(self.x0 + dx, self.y0 + dy, self.x1 + dx, self.y1 + dy)

    @classmethod
    def with_size_around(
        cls, center_x: float, center_y: float, width: float, height: float
    ) -> "RectF":
        return cls(
            center_x - width / 2.0,
            center_y - height / 2.0,
            center_x + width / 2.0,
            center_y + height / 2.0,
        )

    def validate(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError(f"Invalid RectF size: {self}")
