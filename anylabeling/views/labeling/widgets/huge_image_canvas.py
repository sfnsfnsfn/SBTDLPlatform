# FUTURE: pyqtgraph-based canvas. Tested, not wired to main Canvas.
"""
HugeImageCanvas — pyqtgraph-based huge image viewer for X-AnyLabeling.

Replaces the old QPainter + QPixmap rendering stack with a ViewBox + ImageItem
pipeline that supports level-of-detail downsampling (L0=full, L1=1/2, L2=1/4),
hysteresis-based level switching, a cosmetic pixel grid at high zoom, and
ring-buffer performance instrumentation.

Classes (in order):
    PerformanceMonitor  – ring-buffer perf tracker for render pipeline stages
    PixelGridItem       – dynamic pixel grid visible at >= 8x zoom
    HugeImageCanvas     – main QGraphicsView with pyqtgraph scene
"""

import collections
import time

import numpy as np
import pyqtgraph as pg
from PyQt6 import QtCore, QtGui, QtWidgets

# ---------------------------------------------------------------------------
# Module-level pyqtgraph configuration
# ---------------------------------------------------------------------------
pg.setConfigOption("imageAxisOrder", "row-major")
pg.setConfigOption("antialias", False)


# ===================================================================
# PerformanceMonitor
# ===================================================================
class PerformanceMonitor:
    """Ring-buffer performance tracker for render pipeline stages."""

    def __init__(self, max_samples: int = 120):
        self._samples = collections.defaultdict(
            lambda: collections.deque(maxlen=max_samples)
        )
        self._timers: dict[str, int] = {}

    # -- timer API -----------------------------------------------------------
    def start(self, stage: str) -> None:
        """Begin timing *stage* (nanosecond precision)."""
        self._timers[stage] = time.perf_counter_ns()

    def stop(self, stage: str) -> None:
        """Finish timing *stage* and record elapsed nanoseconds."""
        t0 = self._timers.pop(stage, None)
        if t0 is not None:
            self._samples[stage].append(time.perf_counter_ns() - t0)

    # -- query API -----------------------------------------------------------
    def stats(self, stage: str) -> dict:
        """Return ``{avg_ms, p95_ms, max_ms}`` for *stage*."""
        data = list(self._samples.get(stage, []))
        if not data:
            return {"avg_ms": 0, "p95_ms": 0, "max_ms": 0}
        data_sorted = sorted(data)
        n = len(data_sorted)
        avg = sum(data_sorted) / n / 1e6
        p95 = data_sorted[int(n * 0.95)] / 1e6
        mx = data_sorted[-1] / 1e6
        return {"avg_ms": avg, "p95_ms": p95, "max_ms": mx}

    def summary(self) -> str:
        """One-line human-readable summary of all tracked stages."""
        parts = []
        for stage in sorted(self._samples.keys()):
            s = self.stats(stage)
            parts.append(
                f"{stage}: avg={s['avg_ms']:.1f}ms p95={s['p95_ms']:.1f}ms"
            )
        return " | ".join(parts)


# ===================================================================
# PixelGridItem
# ===================================================================
class PixelGridItem(pg.GraphicsObject):
    """Dynamic pixel grid at integer image-coordinate boundaries.

    Only visible when one image pixel maps to **>= 8** screen pixels.
    Uses a cosmetic pen (1 px regardless of zoom) so lines stay hairline.
    """

    def __init__(self):
        super().__init__()
        self._pen = pg.mkPen((255, 255, 255, 60), width=1, cosmetic=True)
        self._visible = False

    # -- visibility toggle ---------------------------------------------------
    def set_visible(self, visible: bool) -> None:
        if self._visible != visible:
            self._visible = visible
            self.update()

    # -- paint ---------------------------------------------------------------
    def paint(self, painter, option, widget):
        if not self._visible:
            return
        painter.setPen(self._pen)
        view = self.getViewBox()
        if view is None:
            return
        vr = view.viewRect()
        x0, x1 = int(vr.left()), int(vr.right()) + 1
        y0, y1 = int(vr.top()), int(vr.bottom()) + 1

        # Guard: don't draw when the view spans too many pixels
        if x1 - x0 > 200 or y1 - y0 > 200:
            return

        for x in range(x0, x1 + 1):
            painter.drawLine(QtCore.QPointF(x, y0), QtCore.QPointF(x, y1))
        for y in range(y0, y1 + 1):
            painter.drawLine(QtCore.QPointF(x0, y), QtCore.QPointF(x1, y))

    # -- bounding rect -------------------------------------------------------
    def boundingRect(self):
        return QtCore.QRectF()


# ===================================================================
# HugeImageCanvas
# ===================================================================
class HugeImageCanvas(QtWidgets.QGraphicsView):
    """QGraphicsView wrapping a pyqtgraph ViewBox + ImageItem for huge images.

    Signals
    -------
    zoom_changed : float
        Emitted with the current scale factor (screen-pixels / image-pixel).
    pixel_hovered : int, int, object
        Emitted with ``(row, col, value)`` when the mouse moves over a pixel.
    """

    # -- hysteresis thresholds -----------------------------------------------
    # When the target level is *higher* than the current level (i.e. we would
    # switch to a coarser LOD), we only switch once scale drops *below* the
    # listed threshold.
    _HYSTERESIS_UPPER: dict[int, float] = {0: 0.6, 1: 0.15}
    # When the target level is *lower* than current (switch to finer LOD),
    # only switch once scale rises *above* the listed threshold.
    _HYSTERESIS_LOWER: dict[int, float] = {1: 1.0, 2: 0.3}

    # Qt signals -------------------------------------------------------------
    zoom_changed = QtCore.pyqtSignal(float)
    pixel_hovered = QtCore.pyqtSignal(int, int, object)

    # -- constructor ---------------------------------------------------------
    def __init__(
        self,
        parent=None,
        use_opengl: bool = False,
        show_pixel_grid: bool = False,
    ):
        super().__init__(parent)

        # Apply OpenGL setting before constructing pyqtgraph items
        pg.setConfigOption("useOpenGL", use_opengl)

        # ---- scene ---------------------------------------------------------
        self._scene = QtWidgets.QGraphicsScene()
        self.setScene(self._scene)

        # ---- view box ------------------------------------------------------
        self.view_box = pg.ViewBox(
            lockAspect=True,
            invertY=True,
            enableMenu=False,
            enableMouse=False,
        )
        self._scene.addItem(self.view_box)

        # ---- image item ----------------------------------------------------
        self.image_item = pg.ImageItem(
            axisOrder="row-major",
            autoDownsample=True,
            autoLevels=False,
        )
        self.view_box.addItem(self.image_item)

        # ---- pixel grid ----------------------------------------------------
        self.pixel_grid = PixelGridItem()
        self.view_box.addItem(self.pixel_grid)

        # ---- view appearance -----------------------------------------------
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setDragMode(QtWidgets.QGraphicsView.DragMode.ScrollHandDrag)
        self.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform, False)

        # ---- internal state ------------------------------------------------
        self._image: np.ndarray | None = None           # L0 — full-resolution
        self._image_width: int = 0
        self._image_height: int = 0
        self._levels: dict[int, np.ndarray] = {}
        self._current_level: int = 2
        self._show_pixel_grid = bool(show_pixel_grid)

        self.perf = PerformanceMonitor()

        # Connect view-range changes emitted by the ViewBox
        self.view_box.sigRangeChanged.connect(self._on_view_changed)

    # -- public API ----------------------------------------------------------
    def set_image(self, image: np.ndarray) -> None:
        """Set the image data and rebuild the level-of-detail pyramid.

        Parameters
        ----------
        image : np.ndarray
            2-D (grayscale) or 3-D (H x W x C) array.
        """
        if image.ndim not in (2, 3):
            raise ValueError(
                f"image must be 2-D or 3-D, got ndim={image.ndim}"
            )

        self._image = np.ascontiguousarray(image)
        h, w = self._image.shape[:2]
        self._image_width = w
        self._image_height = h

        # Build LOD pyramid: L0 = full, L1 = 1/2, L2 = 1/4
        self._levels[0] = self._image
        if w >= 2 and h >= 2:
            self._levels[1] = self._downsample_area(self._image, 2)
        else:
            self._levels[1] = self._image.copy()
        if w >= 4 and h >= 4:
            self._levels[2] = self._downsample_area(self._image, 4)
        else:
            self._levels[2] = self._levels[1]

        self._set_image_level(2)
        self.view_box.setRange(
            xRange=(0, w),
            yRange=(0, h),
            padding=0,
        )

    # -- downsampling --------------------------------------------------------
    @staticmethod
    def _downsample_area(arr: np.ndarray, factor: int) -> np.ndarray:
        """Area-average downsampling by integer *factor*.

        Supports both 2-D (H, W) and 3-D (H, W, C) arrays.
        """
        if arr.ndim == 2:
            h, w = arr.shape
            h2, w2 = h // factor, w // factor
            return (
                arr[: h2 * factor, : w2 * factor]
                .reshape(h2, factor, w2, factor)
                .mean(axis=(1, 3))
                .astype(arr.dtype)
            )
        else:
            h, w = arr.shape[:2]
            h2, w2 = h // factor, w // factor
            out = np.zeros((h2, w2, arr.shape[2]), dtype=arr.dtype)
            for c in range(arr.shape[2]):
                out[:, :, c] = (
                    arr[: h2 * factor, : w2 * factor, c]
                    .reshape(h2, factor, w2, factor)
                    .mean(axis=(1, 3))
                )
            return out

    # -- level selection -----------------------------------------------------
    @staticmethod
    def _select_level(scale: float) -> int:
        """Return a target LOD level for a given scale factor.

        scale < 0.2  -> 2  (coarsest)
        scale < 0.8  -> 1
        else          -> 0  (full resolution)
        """
        if scale < 0.2:
            return 2
        if scale < 0.8:
            return 1
        return 0

    def _set_image_level(self, level: int) -> None:
        if self._image is None:
            return
        src = self._image if level == 0 else self._levels[level]
        self.image_item.setImage(src)
        self.image_item.setRect(
            QtCore.QRectF(0, 0, self._image_width, self._image_height)
        )
        self._current_level = level

    def _update_level(self, scale: float) -> None:
        """Switch the displayed image level using hysteresis to avoid
        flickering back and forth near boundary thresholds."""
        target = self._select_level(scale)
        if target == self._current_level:
            return

        # ---- hysteresis guard ----------------------------------------------
        if target > self._current_level:
            # Switching to coarser level: wait until scale drops below threshold
            threshold = self._HYSTERESIS_UPPER.get(target, 0)
            if scale >= threshold:
                return
        else:
            # Switching to finer level: wait until scale rises above threshold
            threshold = self._HYSTERESIS_LOWER.get(self._current_level, 0)
            if scale <= threshold:
                return

        self._set_image_level(target)

    # -- Qt event overrides --------------------------------------------------
    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        """Zoom centered on cursor position."""
        self.perf.start("wheel")
        delta = event.angleDelta().y()
        factor = 1.1 if delta > 0 else 1.0 / 1.1

        pos = event.position().toPoint()
        scene_pos = self.mapToScene(pos)

        self.view_box.scaleBy((factor, factor), center=scene_pos)
        self.perf.stop("wheel")

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        """Track pixel under cursor and emit ``pixel_hovered``."""
        super().mouseMoveEvent(event)

        if self._image is None:
            return

        pos = event.position().toPoint()
        scene_pos = self.mapToScene(pos)
        col = int(scene_pos.x())
        row = int(scene_pos.y())

        h, w = self._image.shape[:2]
        if 0 <= col < w and 0 <= row < h:
            value = self._image[row, col]
            self.pixel_hovered.emit(row, col, value)

    # -- view-change handler -------------------------------------------------
    def _on_view_changed(self) -> None:
        """React to ViewBox range changes: update LOD and pixel-grid
        visibility, then emit ``zoom_changed``."""
        vr = self.view_box.viewRect()
        if self._image is None:
            return

        view_w = vr.width()
        if view_w <= 0:
            return

        screen_w = max(1, self.viewport().width())
        scale = screen_w / view_w
        self._update_level(scale)

        # Pixel grid is a debug aid; keep it disabled during normal zooming.
        self.pixel_grid.set_visible(self._show_pixel_grid and scale >= 8.0)

        self.zoom_changed.emit(scale)
