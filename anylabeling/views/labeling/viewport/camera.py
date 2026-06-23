from __future__ import annotations

from dataclasses import dataclass

from .coordinate_map import CoordinateMap
from .rect import RectF


@dataclass
class Camera2D:
    """HALCON-style DisplayPart camera over finite image coordinates."""

    image_width: int
    image_height: int
    viewport_width: int
    viewport_height: int
    visible: RectF | None = None
    max_zoom: float = 1000.0
    max_margin_factor: float = 4.0

    def __post_init__(self) -> None:
        self._validate_image_size()
        self._validate_viewport_size(self.viewport_width, self.viewport_height)
        if self.visible is None:
            self.fit_to_window()
        else:
            self.set_visible_rect(self.visible)

    def fit_to_window(self) -> None:
        image_aspect = self.image_width / self.image_height
        view_aspect = self.viewport_width / self.viewport_height

        if view_aspect >= image_aspect:
            part_height = float(self.image_height)
            part_width = part_height * view_aspect
        else:
            part_width = float(self.image_width)
            part_height = part_width / view_aspect

        center_x = self.image_width / 2.0
        center_y = self.image_height / 2.0
        self.visible = RectF.with_size_around(
            center_x, center_y, part_width, part_height
        )

    def fit_width(self) -> None:
        visible_height = (
            self.image_width * self.viewport_height / self.viewport_width
        )
        self.set_visible_rect(
            RectF(
                0.0,
                self.image_height / 2.0 - visible_height / 2.0,
                float(self.image_width),
                self.image_height / 2.0 + visible_height / 2.0,
            )
        )

    def zoom_at_view_point(
        self, view_x: float, view_y: float, factor: float
    ) -> None:
        if factor <= 0:
            raise ValueError(f"Zoom factor must be positive: {factor}")

        coordinate_map = self.coordinate_map()
        anchor_x, anchor_y = coordinate_map.view_to_image(view_x, view_y)
        ratio_x = view_x / self.viewport_width
        ratio_y = view_y / self.viewport_height

        old_visible = self._require_visible()
        new_width = self._clamp_width(old_visible.width / factor)
        new_height = self._height_for_width(new_width)

        x0 = anchor_x - ratio_x * new_width
        y0 = anchor_y - ratio_y * new_height
        self.visible = self._constrain_to_recoverable_view(
            RectF(x0, y0, x0 + new_width, y0 + new_height)
        )

    def set_scale_at_view_point(
        self, view_x: float, view_y: float, scale: float
    ) -> None:
        if scale <= 0:
            raise ValueError(f"Scale must be positive: {scale}")
        current_scale = self.coordinate_map().scale
        self.zoom_at_view_point(view_x, view_y, scale / current_scale)

    def set_scale_around_center(self, scale: float) -> None:
        self.set_scale_at_view_point(
            self.viewport_width / 2.0,
            self.viewport_height / 2.0,
            scale,
        )

    def pan_by_view_delta(self, dx: float, dy: float) -> None:
        scale = self.coordinate_map().scale
        dx_image = -dx / scale
        dy_image = -dy / scale
        self.visible = self._constrain_to_recoverable_view(
            self._require_visible().translated(dx_image, dy_image)
        )

    def resize_viewport(
        self, width: int, height: int, keep_center: bool = True
    ) -> None:
        self._validate_viewport_size(width, height)
        old_visible = self._require_visible()
        self.viewport_width = width
        self.viewport_height = height

        if keep_center:
            self.set_visible_rect(old_visible)
        else:
            self.fit_to_window()

    def set_visible_rect(self, rect: RectF) -> None:
        rect.validate()
        view_aspect = self.viewport_width / self.viewport_height
        rect_aspect = rect.width / rect.height

        if abs(rect_aspect - view_aspect) <= 1e-12:
            self.visible = self._constrain_to_recoverable_view(rect)
            return

        if rect_aspect > view_aspect:
            width = rect.width
            height = width / view_aspect
        else:
            height = rect.height
            width = height * view_aspect

        self.visible = self._constrain_to_recoverable_view(
            RectF.with_size_around(rect.center_x, rect.center_y, width, height)
        )

    def coordinate_map(self) -> CoordinateMap:
        return CoordinateMap(
            self._require_visible(), self.viewport_width, self.viewport_height
        )

    def _require_visible(self) -> RectF:
        if self.visible is None:
            raise RuntimeError("Camera visible rect is not initialized")
        return self.visible

    def _clamp_width(self, width: float) -> float:
        view_aspect = self.viewport_width / self.viewport_height
        # Ensure both visible sides are at least 2 image pixels to
        # prevent coordinate-map aspect-ratio failures and white-out
        # at extreme magnifications.
        min_width = max(
            self.viewport_width / self.max_zoom,  # default: 1200/1000 = 1.2
            2.0,                                    # ensures width ≥ 2 in portrait
            2.0 * view_aspect,                      # ensures height ≥ 2 in landscape
        )
        max_width = min(
            self.image_width * self.max_margin_factor,
            self.image_height * self.max_margin_factor * view_aspect,
        )
        return min(max(width, min_width), max_width)

    def _height_for_width(self, width: float) -> float:
        return width * self.viewport_height / self.viewport_width

    def _constrain_to_recoverable_view(self, rect: RectF) -> RectF:
        """Keep the visible rect from panning completely away from the image."""
        dx = 0.0
        dy = 0.0
        if rect.x1 < 0.0:
            dx = -rect.x1
        elif rect.x0 > self.image_width:
            dx = self.image_width - rect.x0

        if rect.y1 < 0.0:
            dy = -rect.y1
        elif rect.y0 > self.image_height:
            dy = self.image_height - rect.y0

        if dx or dy:
            return rect.translated(dx, dy)
        return rect

    def _validate_image_size(self) -> None:
        if self.image_width <= 0 or self.image_height <= 0:
            raise ValueError(
                "Image width and height must be positive: "
                f"{self.image_width}x{self.image_height}"
            )

    @staticmethod
    def _validate_viewport_size(width: int, height: int) -> None:
        if width <= 0 or height <= 0:
            raise ValueError(
                f"Viewport width and height must be positive: {width}x{height}"
            )
