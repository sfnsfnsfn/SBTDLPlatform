"""MaskBrushTool — pixel-level mask painting for polygon shapes.

Supports brush (add) and eraser (remove) modes with adjustable size,
per-stroke undo, and a circular cursor that reflects the actual brush size.
"""

from __future__ import annotations

import logging

from PyQt6 import QtCore, QtGui, QtWidgets

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_BRUSH_SIZE = 30
MIN_BRUSH_SIZE = 1
MAX_BRUSH_SIZE = 200
MAX_UNDO_DEPTH = 20


class MaskBrushTool:
    """Pixel-level mask painting tool for polygon/segmentation shapes.

    Operates on a QImage mask bitmap stored in ``Shape.other_data["mask_bitmap"]``.
    Each stroke is recorded so it can be undone independently.

    Usage::

        tool = MaskBrushTool(canvas)
        tool.begin_stroke(QPointF(100, 200))
        tool.continue_stroke(QPointF(110, 205))
        tool.end_stroke()  # commits the stroke to the undo stack
    """

    MODE_BRUSH = "brush"
    MODE_ERASER = "eraser"

    def __init__(self, canvas) -> None:
        """*canvas* is the :class:`Canvas` widget this tool operates on."""
        self._canvas = canvas
        self._brush_size: int = DEFAULT_BRUSH_SIZE
        self._mode: str = self.MODE_BRUSH
        self._mask_image: QtGui.QImage | None = None
        self._stroke_points: list[QtCore.QPoint] = []
        self._undo_stack: list[QtGui.QImage] = []
        self._is_stroking: bool = False
        self._active_shape = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def brush_size(self) -> int:
        """Current brush diameter in pixels (display coordinates)."""
        return self._brush_size

    @brush_size.setter
    def brush_size(self, value: int) -> None:
        self._brush_size = max(MIN_BRUSH_SIZE, min(MAX_BRUSH_SIZE, int(value)))

    @property
    def mode(self) -> str:
        """Current mode: ``"brush"`` or ``"eraser"``."""
        return self._mode

    @mode.setter
    def mode(self, value: str) -> None:
        if value not in (self.MODE_BRUSH, self.MODE_ERASER):
            raise ValueError(f"Invalid mode: {value}")
        self._mode = value

    @property
    def is_stroking(self) -> bool:
        """True while the user is actively painting a stroke."""
        return self._is_stroking

    def cursor_for_size(self) -> QtGui.QCursor:
        """Return a circular cursor matching the current brush size."""
        diameter = max(1, self._brush_size)
        pixmap = QtGui.QPixmap(diameter, diameter)
        pixmap.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        pen = QtGui.QPen(QtCore.Qt.GlobalColor.white, 1)
        painter.setPen(pen)
        painter.drawEllipse(1, 1, diameter - 2, diameter - 2)
        painter.end()
        return QtGui.QCursor(pixmap, hotX=diameter // 2, hotY=diameter // 2)

    # ------------------------------------------------------------------
    # Mask lifecycle
    # ------------------------------------------------------------------

    def attach_to_shape(self, shape) -> None:
        """Bind the tool to *shape* and load or create its mask bitmap.

        The mask is stored in ``shape.other_data["mask_bitmap"]`` as a
        ``QImage`` that is ``image_width x image_height`` pixels.
        """
        self._active_shape = shape
        self._stroke_points.clear()
        self._undo_stack.clear()

        other = getattr(shape, "other_data", None) or {}
        existing = other.get("mask_bitmap")
        if isinstance(existing, QtGui.QImage) and not existing.isNull():
            self._mask_image = existing.copy()
        else:
            self._mask_image = None
        self._is_stroking = False

    def detach(self) -> None:
        """Release the current shape and clear transient state."""
        self._active_shape = None
        self._mask_image = None
        self._stroke_points.clear()
        self._undo_stack.clear()
        self._is_stroking = False

    def _ensure_mask(self, width: int, height: int) -> None:
        """Create a blank mask image if none exists."""
        if self._mask_image is None or self._mask_image.isNull():
            self._mask_image = QtGui.QImage(
                width, height, QtGui.QImage.Format.Format_ARGB32
            )
            self._mask_image.fill(QtCore.Qt.GlobalColor.transparent)

    # ------------------------------------------------------------------
    # Stroke handling
    # ------------------------------------------------------------------

    def begin_stroke(self, canvas_pos: QtCore.QPointF) -> None:
        """Start a new paint stroke at *canvas_pos* (image coordinates)."""
        if self._active_shape is None:
            return
        self._is_stroking = True
        pt = QtCore.QPoint(int(canvas_pos.x()), int(canvas_pos.y()))
        self._stroke_points = [pt]

        # Snapshot current mask for undo
        if self._mask_image is not None and not self._mask_image.isNull():
            self._undo_stack.append(self._mask_image.copy())
            # Cap undo stack to prevent unbounded memory growth
            if len(self._undo_stack) > MAX_UNDO_DEPTH:
                self._undo_stack.pop(0)

        self._paint_at(pt)

    def continue_stroke(self, canvas_pos: QtCore.QPointF) -> None:
        """Continue the current stroke to *canvas_pos* (image coordinates)."""
        if not self._is_stroking or self._active_shape is None:
            return
        pt = QtCore.QPoint(int(canvas_pos.x()), int(canvas_pos.y()))
        # Interpolate to fill gaps when the mouse moves fast
        if self._stroke_points:
            last = self._stroke_points[-1]
            self._paint_line(last, pt)
        else:
            self._paint_at(pt)
        self._stroke_points.append(pt)

    def end_stroke(self) -> None:
        """Finish the current stroke and persist the mask to the shape."""
        self._is_stroking = False
        if self._active_shape is not None and self._mask_image is not None:
            other = getattr(self._active_shape, "other_data", None)
            if other is None:
                other = {}
                self._active_shape.other_data = other
            other["mask_bitmap"] = self._mask_image.copy()
        self._stroke_points.clear()

    def undo_stroke(self) -> None:
        """Revert the most recent stroke."""
        if not self._undo_stack:
            return
        prev = self._undo_stack.pop()
        self._mask_image = prev
        if self._active_shape is not None:
            other = getattr(self._active_shape, "other_data", None)
            if other is None:
                other = {}
                self._active_shape.other_data = other
            other["mask_bitmap"] = prev.copy()
        self._canvas.update()

    @property
    def can_undo(self) -> bool:
        """True when at least one stroke can be undone."""
        return len(self._undo_stack) > 0

    # ------------------------------------------------------------------
    # Internal painting
    # ------------------------------------------------------------------

    def _paint_at(self, center: QtCore.QPoint) -> None:
        """Paint a circular brush stamp at *center*."""
        if self._mask_image is None:
            return
        painter = QtGui.QPainter(self._mask_image)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        if self._mode == self.MODE_ERASER:
            painter.setCompositionMode(
                QtGui.QPainter.CompositionMode.CompositionMode_Clear
            )
        else:
            painter.setCompositionMode(
                QtGui.QPainter.CompositionMode.CompositionMode_Source
            )
            painter.setBrush(QtCore.Qt.GlobalColor.white)
            painter.setPen(QtCore.Qt.PenStyle.NoPen)

        r = max(1, self._brush_size // 2)
        painter.drawEllipse(center, r, r)
        painter.end()

    def _paint_line(self, start: QtCore.QPoint, end: QtCore.QPoint) -> None:
        """Paint a line of brush stamps between *start* and *end*."""
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        dist = (dx * dx + dy * dy) ** 0.5
        step = max(1, self._brush_size // 4)  # spacing between stamps

        if dist < 1:
            self._paint_at(end)
            return

        steps = max(1, int(dist / step))
        for i in range(steps + 1):
            t = i / max(steps, 1)
            x = int(start.x() + dx * t)
            y = int(start.y() + dy * t)
            self._paint_at(QtCore.QPoint(x, y))

    # ------------------------------------------------------------------
    # Overlay rendering
    # ------------------------------------------------------------------

    def render_overlay(self, painter: QtGui.QPainter) -> None:
        """Render the current mask as a semi-transparent overlay.

        Call this from the canvas ``paintEvent`` when the mask brush is
        active to give real-time visual feedback.
        """
        if self._mask_image is None or self._mask_image.isNull():
            return
        # Render with a colored tint
        color = (
            QtGui.QColor(0, 120, 255, 100)
            if self._mode == self.MODE_BRUSH
            else QtGui.QColor(255, 80, 80, 100)
        )
        painter.save()
        painter.setOpacity(0.4)
        # Convert mask to composited color image
        tinted = QtGui.QPixmap(self._mask_image.size())
        tinted.fill(QtCore.Qt.GlobalColor.transparent)
        tint_painter = QtGui.QPainter(tinted)
        tint_painter.setCompositionMode(
            QtGui.QPainter.CompositionMode.CompositionMode_Source
        )
        tint_painter.fillRect(tinted.rect(), QtCore.Qt.GlobalColor.transparent)
        tint_painter.setCompositionMode(
            QtGui.QPainter.CompositionMode.CompositionMode_SourceOver
        )
        tint_painter.drawImage(0, 0, self._mask_image)
        tint_painter.setCompositionMode(
            QtGui.QPainter.CompositionMode.CompositionMode_SourceIn
        )
        tint_painter.fillRect(tinted.rect(), color)
        tint_painter.end()
        painter.drawPixmap(0, 0, tinted)
        painter.restore()
