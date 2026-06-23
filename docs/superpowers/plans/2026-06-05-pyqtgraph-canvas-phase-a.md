# PyQtGraph Canvas Phase A Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build standalone pyqtgraph-based huge image viewer prototype and verify <10ms zoom latency on 42000×42000 images.

**Architecture:** HugeImageCanvas wraps pyqtgraph ViewBox + ImageItem. MultiResolutionImageItem manages L0/L1/L2 memory pyramid. PixelGridItem draws pixel grid at high zoom. PerformanceMonitor tracks frame latency.

**Tech Stack:** PyQt6 6.x, pyqtgraph 0.14.0, numpy 2.4.6, tifffile (new)

**Dependencies before start:** `pip install tifffile` (pyqtgraph already installed)

---

### Task 1: Install tifffile dependency

**Files:** None (environment change)

- [ ] **Step 1: Install tifffile**

```bash
pip install tifffile
```

- [ ] **Step 2: Verify import**

```bash
python -c "import tifffile; print(tifffile.__version__)"
```
Expected: version string printed, no errors.

---

### Task 2: Create HugeImageCanvas (minimal prototype)

**Files:**
- Create: `anylabeling/views/labeling/widgets/huge_image_canvas.py`

- [ ] **Step 1: Write initial module — ViewBox + ImageItem in a QGraphicsView**

```python
"""HugeImageCanvas: pyqtgraph-based viewer for 42000×42000 images."""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt6 import QtCore, QtGui, QtWidgets

# Global pyqtgraph config
pg.setConfigOption("imageAxisOrder", "row-major")
pg.setConfigOption("antialias", False)


class HugeImageCanvas(QtWidgets.QGraphicsView):
    """QGraphicsView wrapping a pyqtgraph ViewBox + ImageItem for huge images.

    Signals:
        zoom_changed(float)  -- current scale (screen_px / image_px)
        pixel_hovered(row, col, value)  -- mouse over image pixel
    """

    zoom_changed = QtCore.pyqtSignal(float)
    pixel_hovered = QtCore.pyqtSignal(int, int, object)

    def __init__(self, parent=None, use_opengl=False):
        super().__init__(parent)
        pg.setConfigOption("useOpenGL", use_opengl)

        # Graphics scene
        self._scene = QtWidgets.QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform, False)
        self.setDragMode(QtWidgets.QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(
            QtWidgets.QGraphicsView.ViewportAnchor.NoAnchor
        )
        self.setResizeAnchor(QtWidgets.QGraphicsView.ViewportAnchor.NoAnchor)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # ViewBox
        self.view_box = pg.ViewBox(
            lockAspect=True,
            invertY=True,
            enableMenu=False,
            enableMouse=False,  # we handle wheel/pan ourselves
        )
        self._scene.addItem(self.view_box)

        # ImageItem
        self.image_item = pg.ImageItem(
            axisOrder="row-major",
            autoDownsample=True,
            autoLevels=False,
        )
        self.view_box.addItem(self.image_item)

        # State
        self._image = None  # numpy array
        self._levels = {}  # {0: L0, 1: L1, 2: L2}
        self._current_level = 2  # start with coarsest
        self.setMouseTracking(True)

    def set_image(self, image: np.ndarray) -> None:
        """Set L0 image and generate L1/L2 pyramid levels."""
        if image.ndim not in (2, 3):
            raise ValueError(f"Expected 2D or 3D array, got shape {image.shape}")
        self._image = np.ascontiguousarray(image)
        h, w = image.shape[:2]

        # L1: 1/2
        self._levels[1] = self._downsample_area(image, 2)
        # L2: 1/4
        self._levels[2] = self._downsample_area(self._levels[1], 2)

        self._current_level = 2
        self.image_item.setImage(self._levels[2])
        self.view_box.setRange(
            xRange=(0, w),
            yRange=(0, h),
            padding=0,
        )

    @staticmethod
    def _downsample_area(arr: np.ndarray, factor: int) -> np.ndarray:
        """Area-averaging downsample by integer factor."""
        if arr.ndim == 2:
            h, w = arr.shape
            h2, w2 = h // factor, w // factor
            return arr[:h2 * factor, :w2 * factor].reshape(
                h2, factor, w2, factor
            ).mean(axis=(1, 3)).astype(arr.dtype)
        else:
            h, w = arr.shape[:2]
            h2, w2 = h // factor, w // factor
            out = np.zeros((h2, w2, arr.shape[2]), dtype=arr.dtype)
            for c in range(arr.shape[2]):
                out[:, :, c] = arr[:h2 * factor, :w2 * factor, c].reshape(
                    h2, factor, w2, factor
                ).mean(axis=(1, 3))
            return out

    @property
    def image(self) -> np.ndarray | None:
        return self._image

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        """Mouse-wheel zoom centered on cursor."""
        factor = 1.1 if event.angleDelta().y() > 0 else 1.0 / 1.1
        pos = self.mapToScene(event.position().toPoint())
        self.view_box.scaleBy((factor, factor), center=pos)
        self._on_view_changed()
        event.accept()

    def _on_view_changed(self) -> None:
        """Sync state after ViewBox range changes."""
        vr = self.view_box.viewRange()
        x_range = vr[0]
        y_range = vr[1]
        if x_range[1] <= x_range[0] or y_range[1] <= y_range[0]:
            return
        view_w = self.viewport().width()
        view_h = self.viewport().height()
        if view_w <= 0 or view_h <= 0:
            return
        img_w = x_range[1] - x_range[0]
        scale = view_w / img_w
        self.zoom_changed.emit(scale)
```

- [ ] **Step 2: Compile check**

```bash
python -m py_compile anylabeling/views/labeling/widgets/huge_image_canvas.py
```
Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add anylabeling/views/labeling/widgets/huge_image_canvas.py
git commit -m "feat: add HugeImageCanvas — pyqtgraph-based huge image viewer"
```

---

### Task 3: Add multi-resolution level switching

**Files:**
- Modify: `anylabeling/views/labeling/widgets/huge_image_canvas.py`

- [ ] **Step 1: Add level selection and hysteresis to HugeImageCanvas**

Add after `_on_view_changed`:

```python
    def _select_level(self, scale: float) -> int:
        """Select pyramid level based on screen-to-image pixel ratio."""
        if scale < 0.2:
            return 2  # L2: 1/4
        elif scale < 0.8:
            return 1  # L1: 1/2
        else:
            return 0  # L0: full

    def _update_level(self, scale: float) -> None:
        """Switch ImageItem data if level changed, with hysteresis."""
        target = self._select_level(scale)
        if target == self._current_level:
            return

        # Hysteresis: only switch if scale has moved well past the boundary
        if target > self._current_level and scale < self._hysteresis_upper(target):
            return
        if target < self._current_level and scale > self._hysteresis_lower(target):
            return

        src = self._image if target == 0 else self._levels.get(target)
        if src is not None:
            self.image_item.setImage(src)
            self._current_level = target

    def _hysteresis_upper(self, level: int) -> float:
        return {0: 0.6, 1: 0.15}.get(level, 0.0)

    def _hysteresis_lower(self, level: int) -> float:
        return {1: 1.0, 2: 0.3}.get(level, 0.0)
```

Update `_on_view_changed` to call `_update_level`:

```python
    def _on_view_changed(self) -> None:
        vr = self.view_box.viewRange()
        x_range = vr[0]
        y_range = vr[1]
        if x_range[1] <= x_range[0] or y_range[1] <= y_range[0]:
            return
        view_w = self.viewport().width()
        view_h = self.viewport().height()
        if view_w <= 0 or view_h <= 0:
            return
        img_w = x_range[1] - x_range[0]
        scale = view_w / img_w
        self._update_level(scale)
        self.zoom_changed.emit(scale)
```

Update `set_image()` to also store L0:

```python
    def set_image(self, image: np.ndarray) -> None:
        ...
        self._levels[0] = self._image  # L0: original
```

- [ ] **Step 2: Compile check**

```bash
python -m py_compile anylabeling/views/labeling/widgets/huge_image_canvas.py
```

- [ ] **Step 3: Commit**

```bash
git add anylabeling/views/labeling/widgets/huge_image_canvas.py
git commit -m "feat: add multi-resolution level switching with hysteresis"
```

---

### Task 4: Add pixel hover information

**Files:**
- Modify: `anylabeling/views/labeling/widgets/huge_image_canvas.py`

- [ ] **Step 1: Add mouseMoveEvent with pixel lookup**

```python
    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        """Track mouse position and emit pixel_hovered signal."""
        super().mouseMoveEvent(event)
        pos = self.mapToScene(event.position().toPoint())
        col = int(pos.x())
        row = int(pos.y())
        if self._image is not None and 0 <= col < self._image.shape[1] and 0 <= row < self._image.shape[0]:
            value = self._image[row, col]
            self.pixel_hovered.emit(row, col, value)
```

- [ ] **Step 2: Compile check and commit**

```bash
python -m py_compile anylabeling/views/labeling/widgets/huge_image_canvas.py
git add anylabeling/views/labeling/widgets/huge_image_canvas.py
git commit -m "feat: add pixel hover coordinate/value tracking"
```

---

### Task 5: Add PixelGridItem

**Files:**
- Modify: `anylabeling/views/labeling/widgets/huge_image_canvas.py`

- [ ] **Step 1: Add PixelGridItem class (before HugeImageCanvas)**

```python
class PixelGridItem(pg.GraphicsObject):
    """Dynamic pixel grid drawn at integer image-coordinate boundaries.

    Only visible when one image pixel spans >= 8 screen pixels.
    Uses cosmetic pen (1px wide regardless of zoom).
    """

    def __init__(self):
        super().__init__()
        self._pen = pg.mkPen((255, 255, 255, 60), width=1, cosmetic=True)
        self._visible = False

    def set_visible(self, visible: bool) -> None:
        if self._visible != visible:
            self._visible = visible
            self.update()

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
        for x in range(x0, x1 + 1):
            painter.drawLine(QtCore.QPointF(x, y0), QtCore.QPointF(x, y1))
        for y in range(y0, y1 + 1):
            painter.drawLine(QtCore.QPointF(x0, y), QtCore.QPointF(x1, y))

    def boundingRect(self):
        return QtCore.QRectF()
```

Add to HugeImageCanvas `__init__`:

```python
        self.pixel_grid = PixelGridItem()
        self.view_box.addItem(self.pixel_grid)
```

Update `_on_view_changed` to toggle grid:

```python
        # Show pixel grid when scale >= 8
        self.pixel_grid.set_visible(scale >= 8.0)
```

- [ ] **Step 2: Compile check and commit**

```bash
python -m py_compile anylabeling/views/labeling/widgets/huge_image_canvas.py
git add anylabeling/views/labeling/widgets/huge_image_canvas.py
git commit -m "feat: add PixelGridItem for high-zoom pixel grid"
```

---

### Task 6: Add PerformanceMonitor

**Files:**
- Modify: `anylabeling/views/labeling/widgets/huge_image_canvas.py`

- [ ] **Step 1: Add PerformanceMonitor class**

```python
import collections
import time

class PerformanceMonitor:
    """Ring-buffer performance tracker for render pipeline stages."""

    def __init__(self, max_samples=120):
        self._samples = collections.defaultdict(lambda: collections.deque(maxlen=max_samples))
        self._timers = {}

    def start(self, stage: str) -> None:
        self._timers[stage] = time.perf_counter_ns()

    def stop(self, stage: str) -> None:
        t0 = self._timers.pop(stage, None)
        if t0 is not None:
            self._samples[stage].append(time.perf_counter_ns() - t0)

    def stats(self, stage: str) -> dict:
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
        parts = []
        for stage in sorted(self._samples.keys()):
            s = self.stats(stage)
            parts.append(f"{stage}: avg={s['avg_ms']:.1f}ms p95={s['p95_ms']:.1f}ms")
        return " | ".join(parts)
```

Add to HugeImageCanvas `__init__`:

```python
        self.perf = PerformanceMonitor()
```

- [ ] **Step 2: Compile check and commit**

```bash
python -m py_compile anylabeling/views/labeling/widgets/huge_image_canvas.py
git add anylabeling/views/labeling/widgets/huge_image_canvas.py
git commit -m "feat: add PerformanceMonitor for render pipeline timing"
```

---

### Task 7: Create standalone test script

**Files:**
- Create: `scripts/test_pyqtgraph_canvas.py`

- [ ] **Step 1: Write test script**

```python
#!/usr/bin/env python
"""Standalone test for HugeImageCanvas with synthetic 42000×42000 image."""
import argparse
import sys
import numpy as np
from PyQt6 import QtCore, QtWidgets

sys.path.insert(0, ".")
from anylabeling.views.labeling.widgets.huge_image_canvas import HugeImageCanvas


class TestWindow(QtWidgets.QMainWindow):
    def __init__(self, use_opengl=False, image_size=42000):
        super().__init__()
        self.setWindowTitle(f"HugeImageCanvas Test — {image_size}×{image_size}")
        self.resize(1400, 900)

        self.canvas = HugeImageCanvas(use_opengl=use_opengl)
        self.setCentralWidget(self.canvas)

        self.statusBar().showMessage("Generating test image...")
        QtCore.QTimer.singleShot(100, lambda: self._load_image(image_size))

    def _load_image(self, size):
        # Generate synthetic image with grid pattern
        rng = np.random.default_rng(42)
        img = rng.integers(0, 256, (size, size), dtype=np.uint8)
        # Add grid lines and a test pattern
        img[::1000, :] = 200
        img[:, ::1000] = 200
        img[size//2-5:size//2+5, size//2-5:size//2+5] = 255
        self.canvas.set_image(img)
        self.canvas.zoom_changed.connect(self._on_zoom)
        self.canvas.pixel_hovered.connect(self._on_pixel)
        self.statusBar().showMessage(f"Loaded {size}×{size} uint8 — {img.nbytes/1e6:.0f} MB")

    def _on_zoom(self, scale):
        self.statusBar().showMessage(
            f"Scale: {scale:.4f} | {self.canvas.perf.summary()}"
        )

    def _on_pixel(self, row, col, value):
        pass  # logged to status bar by _on_zoom


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--opengl", action="store_true")
    parser.add_argument("--size", type=int, default=42000)
    args = parser.parse_args()

    app = QtWidgets.QApplication(sys.argv)
    win = TestWindow(use_opengl=args.opengl, image_size=args.size)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Test the script**

```bash
python scripts/test_pyqtgraph_canvas.py --size 2000 --opengl &
python scripts/test_pyqtgraph_canvas.py --size 2000 &
```
Verify: window opens, image displayed, zoom works.

- [ ] **Step 3: Full-size test (42000×42000)**

```bash
python scripts/test_pyqtgraph_canvas.py --size 42000
```
Verify: zoom/pan smooth, status bar shows perf stats.

- [ ] **Step 4: Commit**

```bash
git add scripts/test_pyqtgraph_canvas.py
git commit -m "test: add standalone pyqtgraph canvas benchmark script"
```

---

### Task 8: Run full verification

- [ ] **Step 1: Run existing test suite**

```bash
python -m pytest tests/views/labeling -q --tb=short
```
Expected: 76 passed, 19 skipped, 13 subtests passed (no regressions).

- [ ] **Step 2: Compile check all new files**

```bash
python -m py_compile anylabeling/views/labeling/widgets/huge_image_canvas.py scripts/test_pyqtgraph_canvas.py
```

- [ ] **Step 3: Record performance baseline**

Run `scripts/test_pyqtgraph_canvas.py --size 42000` and note:
- Wheel event latency at fit-window, 1:1, and 8× zoom
- Memory usage (check Task Manager)
- Pixel grid rendering at 8×+

---

