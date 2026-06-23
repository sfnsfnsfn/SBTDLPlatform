from __future__ import annotations

from dataclasses import dataclass

from .rect import RectF


@dataclass(frozen=True)
class CoordinateMap:
    """Bidirectional mapping between image/world and viewport coordinates."""

    visible: RectF
    viewport_width: int
    viewport_height: int

    def __post_init__(self) -> None:
        if self.viewport_width <= 0 or self.viewport_height <= 0:
            raise ValueError(
                "Viewport width and height must be positive: "
                f"{self.viewport_width}x{self.viewport_height}"
            )

        scale_x = self.viewport_width / self.visible.width
        scale_y = self.viewport_height / self.visible.height
        # 1e-6 tolerance: at extreme zoom (>10,000%) the visible rect
        # may be only a few pixels wide; floating-point rounding of
        # width/height produces sub-pixel differences harmless in practice.
        if abs(scale_x - scale_y) > 1e-6:
            raise ValueError(
                "Visible rect aspect must match viewport aspect for "
                f"uniform mapping: {self.visible} vs "
                f"{self.viewport_width}x{self.viewport_height}"
            )

    @property
    def scale(self) -> float:
        return self.viewport_width / self.visible.width

    def image_to_view(self, x: float, y: float) -> tuple[float, float]:
        view_x = (x - self.visible.x0) * self.scale
        view_y = (y - self.visible.y0) * self.scale
        return view_x, view_y

    def view_to_image(self, view_x: float, view_y: float) -> tuple[float, float]:
        x = view_x / self.scale + self.visible.x0
        y = view_y / self.scale + self.visible.y0
        return x, y

    def image_rect_to_view(self, rect: RectF) -> RectF:
        x0, y0 = self.image_to_view(rect.x0, rect.y0)
        x1, y1 = self.image_to_view(rect.x1, rect.y1)
        return RectF(x0, y0, x1, y1)

    def view_rect_to_image(self, rect: RectF) -> RectF:
        x0, y0 = self.view_to_image(rect.x0, rect.y0)
        x1, y1 = self.view_to_image(rect.x1, rect.y1)
        return RectF(x0, y0, x1, y1)

    def image_to_view_qtransform(self):
        try:
            from PyQt6.QtGui import QTransform
        except ImportError as exc:
            raise RuntimeError("PyQt6 is required to build QTransform") from exc

        transform = QTransform()
        transform.translate(
            -self.visible.x0 * self.scale,
            -self.visible.y0 * self.scale,
        )
        transform.scale(self.scale, self.scale)
        return transform
