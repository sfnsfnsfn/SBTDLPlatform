"""TilePreviewWidget — QGraphicsView-based tile grid overlay on source image.

Displays a downsampled source image with a semi-transparent tile grid
overlay.  Tiles are colour-coded: green (has labels), grey (empty),
orange (contains truncated labels).  Clicking a tile emits a signal.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PyQt6 import QtCore, QtGui, QtWidgets

from anylabeling.platform.domain.tile import TilePlan, TileRecord

logger = logging.getLogger(__name__)

_MAX_PREVIEW_SIZE = 800  # px — source image downsampled to fit


class TilePreviewWidget(QtWidgets.QGraphicsView):
    """Interactive tile grid preview on top of a downsampled source image.

    Signals:
        tile_selected(tile_id: str): Emitted when the user clicks a tile.
    """

    tile_selected = QtCore.pyqtSignal(str)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._scene = QtWidgets.QGraphicsScene(self)
        self.setScene(self._scene)

        self._source_path: str = ""
        self._pixmap_item: QtWidgets.QGraphicsPixmapItem | None = None
        self._tile_rects: list[tuple[str, QtWidgets.QGraphicsRectItem]] = []
        self._tile_plan: TilePlan | None = None
        self._tile_label_counts: dict[str, int] = {}
        self._tile_truncated_counts: dict[str, int] = {}
        self._scale_factor: float = 1.0

        self._setup_view()
        self._apply_theme()

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_view(self) -> None:
        """Configure the QGraphicsView appearance and behaviour."""
        self.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.setVerticalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        self.setDragMode(QtWidgets.QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(
            QtWidgets.QGraphicsView.ViewportAnchor.AnchorUnderMouse
        )
        self.setResizeAnchor(
            QtWidgets.QGraphicsView.ViewportAnchor.AnchorUnderMouse
        )
        self.setMinimumSize(300, 300)

    def _apply_theme(self) -> None:
        """Apply theme-aware styling."""
        from anylabeling.views.labeling.utils.theme import get_theme

        t = get_theme()
        self.setStyleSheet(
            f"QGraphicsView {{ border: 1px solid {t['border']}; "
            f"border-radius: 4px; background-color: {t['surface']}; }}"
        )
        self._scene.setBackgroundBrush(QtGui.QColor(t["background"]))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_source_image(self, image_path: str) -> None:
        """Load and display a downsampled source image as background.

        The image is scaled to fit within ``_MAX_PREVIEW_SIZE`` while
        preserving the aspect ratio.
        """
        self._source_path = image_path
        self._scene.clear()
        self._tile_rects.clear()

        path = Path(image_path)
        if not path.exists():
            logger.warning("Source image not found: %s", image_path)
            return

        pixmap = QtGui.QPixmap(image_path)
        if pixmap.isNull():
            logger.warning("Failed to load image: %s", image_path)
            return

        # Downsample to fit preview area
        w, h = pixmap.width(), pixmap.height()
        max_dim = max(w, h)
        if max_dim > _MAX_PREVIEW_SIZE:
            self._scale_factor = _MAX_PREVIEW_SIZE / max_dim
            new_w = int(w * self._scale_factor)
            new_h = int(h * self._scale_factor)
            pixmap = pixmap.scaled(
                new_w,
                new_h,
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation,
            )
        else:
            self._scale_factor = 1.0

        self._pixmap_item = self._scene.addPixmap(pixmap)
        self._pixmap_item.setZValue(0)
        self._scene.setSceneRect(self._pixmap_item.boundingRect())
        self.fitInView(
            self._pixmap_item,
            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
        )

    def set_tile_plan(self, plan: TilePlan) -> None:
        """Set the tile plan used to compute the grid layout."""
        self._tile_plan = plan
        self._redraw_grid()

    def set_tile_data(
        self,
        records: list[TileRecord],
        label_counts: dict[str, int],
        truncated_counts: dict[str, int],
    ) -> None:
        """Supply tile metadata for colour coding.

        Parameters
        ----------
        records:
            TileRecord instances for the current source image.
        label_counts:
            Mapping of ``tile_id`` → number of label objects in tile.
        truncated_counts:
            Mapping of ``tile_id`` → number of truncated objects.
        """
        self._tile_label_counts = label_counts
        self._tile_truncated_counts = truncated_counts
        self._tile_records = records
        self._redraw_grid()

    def highlight_tile(self, tile_id: str) -> None:
        """Visually highlight a tile (e.g. bold border)."""
        for tid, rect_item in self._tile_rects:
            if tid == tile_id:
                rect_item.setPen(
                    QtGui.QPen(QtGui.QColor("#FFD700"), 3)
                )
            else:
                self._style_rect_item(rect_item, tid)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _redraw_grid(self) -> None:
        """Rebuild the tile grid overlay."""
        if self._tile_plan is None or self._pixmap_item is None:
            return

        # Remove old grid items
        for _, rect_item in self._tile_rects:
            self._scene.removeItem(rect_item)
        self._tile_rects.clear()

        if not hasattr(self, "_tile_records") or not self._tile_records:
            return

        for rec in self._tile_records:
            # Scale L0 coordinates to preview coordinates
            x = rec.x0 * self._scale_factor
            y = rec.y0 * self._scale_factor
            w = rec.width * self._scale_factor
            h = rec.height * self._scale_factor

            rect_item = self._scene.addRect(
                x, y, w, h,
                QtGui.QPen(QtGui.QColor(0, 0, 0, 0)),
                QtGui.QBrush(QtGui.QColor(128, 128, 128, 30)),
            )
            rect_item.setZValue(1)
            rect_item.setData(0, rec.tile_id)
            self._style_rect_item(rect_item, rec.tile_id)
            self._tile_rects.append((rec.tile_id, rect_item))

    def _style_rect_item(
        self, item: QtWidgets.QGraphicsRectItem, tile_id: str
    ) -> None:
        """Apply colour coding to a tile rectangle."""
        label_count = self._tile_label_counts.get(tile_id, 0)
        truncated_count = self._tile_truncated_counts.get(tile_id, 0)

        if truncated_count > 0:
            colour = QtGui.QColor(255, 165, 0, 80)  # orange, semi-transparent
            pen_colour = QtGui.QColor(255, 140, 0, 180)
        elif label_count > 0:
            colour = QtGui.QColor(0, 180, 80, 60)  # green, semi-transparent
            pen_colour = QtGui.QColor(0, 160, 60, 160)
        else:
            colour = QtGui.QColor(128, 128, 128, 30)  # grey, very subtle
            pen_colour = QtGui.QColor(160, 160, 160, 60)

        item.setBrush(QtGui.QBrush(colour))
        item.setPen(QtGui.QPen(pen_colour, 1))

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        """Handle tile click — detect which tile was clicked and emit signal."""
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            scene_pos = self.mapToScene(event.pos())
            for tile_id, rect_item in self._tile_rects:
                if rect_item.contains(scene_pos):
                    self.tile_selected.emit(tile_id)
                    return
        super().mousePressEvent(event)


__all__ = ["TilePreviewWidget"]
