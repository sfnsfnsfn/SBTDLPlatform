# PyQtGraph Canvas Design for X-AnyLabeling

Date: 2026-06-05 | Status: draft | Branch: feat_virtual_canvas

## 1. Goal

Replace the current custom QPainter + QPixmap + pyramid rendering stack with pyqtgraph ImageItem + ViewBox, while preserving Camera2D/CoordinateMap as the coordinate authority.

## 2. Architecture

```
label_widget (QMainWindow)
  └── HugeImageCanvas (QGraphicsView)           ← new, replaces QWidget Canvas
        ├── pyqtgraph ViewBox                    ← zoom/pan via setRange
        │     ├── MultiResolutionImageItem       ← L0/L1/L2 numpy arrays
        │     ├── PixelGridItem (QGraphicsItem)  ← dynamic pixel grid
        │     └── ShapeItems (QGraphicsItem)     ← annotation layer (Phase 2)
        └── transparent overlay (future)         ← for crosshair/pending items

  + Camera2D + CoordinateMap                     ← coordinate authority, unchanged
```

## 3. What Gets Replaced

| Old | New | Reason |
|-----|-----|--------|
| `Canvas` (QWidget, ~3500 lines) | `HugeImageCanvas` (QGraphicsView, ~200 lines) | pyqtgraph handles rendering |
| `paintEvent` with QPainter | ImageItem auto-paint | autoDownsample, GPU texture management |
| `QScrollArea` | ViewBox pan/zoom | native graphics view navigation |
| Pyramid QPixmap cache | MultiResolutionImageItem numpy arrays | ImageItem.setImage() takes numpy directly |
| Manual `drawPixmap` with QTransform | ViewBox.setRange() | declarative view control |
| Shape QPainter code | QGraphicsItem subclasses | incremental migration; first phase preserves QPainter shapes as-is |

## 4. Retained

- Camera2D / CoordinateMap — coordinate authority
- LabelFile / Shape JSON format — unchanged
- `_try_create_image_provider()` → renamed `_create_pyramid_levels()` — produces L0/L1/L2 numpy arrays
- label_widget business logic (load_file, save, etc.)
- Shape data structures (will be wrapped as QGraphicsItem in Phase 2)

## 5. Component Details

### 5.1 HugeImageCanvas (QGraphicsView)

Wraps a pyqtgraph GraphicsLayoutWidget with a single ViewBox + ImageItem.

```python
class HugeImageCanvas(QGraphicsView):
    def __init__(self, parent=None):
        self.view_box = pg.ViewBox(lockAspect=True, invertY=True, ...)
        self.image_item = pg.ImageItem(axisOrder="row-major", autoDownsample=True, ...)
        self.l0, self.l1, self.l2 = None, None, None  # numpy arrays
        self.camera = None  # Camera2D, kept in sync
```

Key behaviors:
- Zoom: wheelEvent → ViewBox.scaleBy(factor, center=scene_coord) → read viewRange → update Camera2D.visible
- Pan: ViewBox handles natively; on viewRange change → update Camera2D.visible
- Fit: set ViewBox range to image rect
- Pixel-grid mode: PixelGridItem shown when scale >= 8×
- Coordinate sync: Camera2D ↔ ViewBox viewRange bidirectional

### 5.2 MultiResolutionImageItem

Maintains L0/L1/L2 as numpy arrays. Uses pyqtgraph ImageItem.setImage().

```python
class MultiResolutionImageItem:
    def __init__(self, image_item, l0):
        self.l0 = l0                    # original, ~6.4 GB for 40000×40000 uint16
        self.l1 = downsample_area(l0)   # 1/4, ~400 MB
        self.l2 = downsample_area(l1)   # 1/16, ~25 MB
        self.image_item = image_item
        self.image_item.setImage(self.l2)  # start with L2 (fit window)

    def on_zoom_changed(self, scale):
        # scale = screen_pixels / image_pixels
        target = self._select_level(scale)
        if target != self.current_level:
            self.image_item.setImage(target)
            self.current_level = target

    def _select_level(self, scale):
        if scale < 0.2:   return self.l2
        elif scale < 0.8: return self.l1
        else:             return self.l0
```

Important: `setImage()` just replaces the data reference — no copy, no resize. pyqtgraph handles texture upload internally.

### 5.3 PixelGridItem (QGraphicsObject)

Drawn only when `scale >= 8.0` (one image pixel ≥ 8 screen pixels).

```python
class PixelGridItem(QGraphicsObject):
    def paint(self, painter, option, widget):
        # Get visible image rect from ViewBox
        # For each integer pixel boundary in visible range:
        #   draw 1px-wide line (pen width = 1/cosmetic)
        # O(visible_pixels) lines max, typically < 100
```

### 5.4 PerformanceMonitor

Simple ring buffer of perf_counter_ns deltas for key stages:
- wheelEvent CPU time
- ViewBox.setRange time
- paint time (via QGraphicsView.paintEvent wrapper)
- Memory (via tracemalloc or psutil)

Displayed: avg / p95 / max in status bar, refreshed every 500ms.

## 6. Coordinate Sync Strategy

**Camera2D drives ViewBox** (not the other way):
```
wheelEvent → Camera2D.zoom_at_view_point()
           → visible changes
           → map visible rect to ViewBox viewRange
           → ViewBox.setRange(xrange, yrange, padding=0)
           → ImageItem auto-repaints
```

This ensures Camera2D remains the single coordinate authority.

Mapping: `visible` is in image coordinates (0..width, 0..height). ViewBox viewRange maps directly — `setRange(xRange=(visible.x0, visible.x1), yRange=(visible.y0, visible.y1))`.

## 7. Shape Annotation Migration (Phase 2)

First phase: keep existing Shape QPainter drawing on a transparent overlay widget. This minimizes risk — shapes work exactly as before.

Second phase: migrate shape types incrementally to QGraphicsItem:
- Rectangle → QGraphicsRectItem (adjusted for rotation)
- Polygon → QGraphicsPolygonItem
- Points → QGraphicsEllipseItem
- Labels → QGraphicsTextItem

All use L0 image coordinates. The ViewBox transform handles screen mapping automatically.

## 8. OpenGL Strategy

Default: raster mode (`pg.setConfigOption("useOpenGL", False)`).
Option: `useOpenGL=True` via command-line flag or config.

pyqtgraph with OpenGL enables GPU texture upload and GPU-based downsampling. But platform/driver compatibility varies. Provide a benchmark script to compare.

## 9. Implementation Phases

### Phase A: Standalone prototype
- New file `anylabeling/views/labeling/widgets/huge_image_canvas.py`
- Standalone test script `scripts/test_pyqtgraph_canvas.py`
- Load 40000×40000 numpy array → display in HugeImageCanvas
- Verify zoom/pan performance < 10ms
- Compare OpenGL vs raster

### Phase B: Integrate into label_widget
- Replace `Canvas` with `HugeImageCanvas` in label_widget
- Wire Camera2D ↔ ViewBox sync
- Pyramid levels: reuse existing QImageReader decode, convert to numpy
- Preserve shape overlay (transparent widget on top)
- Disable old provider/tile_cache code paths

### Phase C: Shape migration to QGraphicsItem
- Rectangle, polygon, point, line items
- Label text items
- Crosshair item
- Delete old QPainter shape code

### Phase D: Performance tuning
- Benchmark script
- OpenGL vs raster comparison
- Profile and fix remaining bottlenecks
- Remove old viewport pyramid/tile_cache code

## 10. Files Changed

**New:**
- `anylabeling/views/labeling/widgets/huge_image_canvas.py` — HugeImageCanvas, MultiResolutionImageItem, PixelGridItem, PerformanceMonitor
- `scripts/test_pyqtgraph_canvas.py` — standalone benchmark

**Modified:**
- `anylabeling/views/labeling/widgets/__init__.py` — export HugeImageCanvas
- `anylabeling/views/labeling/label_widget.py` — swap Canvas → HugeImageCanvas
- `pyproject.toml` — add pyqtgraph dependency
- `anylabeling/app.py` — add `--use-opengl` flag

**Removed (Phase D):**
- `anylabeling/views/labeling/viewport/tile_cache.py`
- `anylabeling/views/labeling/viewport/tile_grid.py`
- `anylabeling/views/labeling/viewport/image_provider.py` (QImageRegionProvider part)
- `anylabeling/views/labeling/widgets/canvas.py` (legacy paint code)

## 11. Supported Image Formats

- TIFF (tiled/striped, multi-page → first page only) — via `tifffile` or Pillow
- PNG, JPEG, BMP, GIF — via Pillow / OpenCV
- All loading converts to numpy ndarray (C-contiguous) for pyqtgraph ImageItem

## 12. Verification

1. `python scripts/test_pyqtgraph_canvas.py` — load 40000×40000 array, verify < 10ms wheel latency
2. `python -m pytest tests/views/labeling -q` — existing tests pass (Camera2D/CoordinateMap unchanged)
3. Manual: open real 32000×32000 image in X-AnyLabeling, verify zoom/pan smoothness
4. Manual: verify pixel values at max zoom match original numpy array
5. Manual: verify shape creation/editing works
6. `python scripts/test_pyqtgraph_canvas.py --opengl` — compare OpenGL vs raster
